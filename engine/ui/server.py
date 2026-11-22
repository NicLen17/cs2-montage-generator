"""Editor web local: una interfaz para armar, ajustar y renderizar edits sin tocar archivos a mano.

    python engine/ui/server.py            abre http://127.0.0.1:8765 en el navegador
    python engine/ui/server.py --port 9000 --no-browser

Es opcional: usa el mismo motor y los mismos archivos que la línea de comandos (edit.json, presets, status.json), así
que lo que se hace acá se puede seguir desde la terminal y al revés. Solo escucha en esta computadora (127.0.0.1) y no
necesita instalar nada más: servidor de la librería estándar de Python y una página sin dependencias.
"""
import json, mimetypes, os, re, subprocess, sys, threading, time, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UI = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(UI)
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)
import paths, planner, preset, project as proj

PROJECTS = os.path.join(ROOT, 'projects')
STATIC = os.path.join(UI, 'static')
PY = sys.executable
NAME = re.compile(r'^[a-z0-9][a-z0-9_]{0,48}$')
JOBS = {}                 # proyecto -> dict(proc, task, t0, log)
TASKS = {
    'auto': lambda p, a: ['auto.py', p, '--plan-only'] + (['--force'] if a.get('force') else []) + (['--reactions'] if a.get('reactions') else []),
    'shots': lambda p, a: ['analyze_clips.py', p, '--shots'],
    'draft': lambda p, a: ['build.py', p, '--draft'],
    'final': lambda p, a: ['build.py', p],
    'preview': lambda p, a: ['build.py', p, '--preview', ','.join(f'{float(t):.2f}' for t in a.get('times', [])[:8])],
    'shorts': lambda p, a: ['short.py', p, '--count', 'auto', '--dur', '35'],
    'thumb': lambda p, a: ['ui/chain.py', json.dumps([['publish.py', p, 'frames'], ['publish.py', p, 'thumb', '--frame', str(int(a.get('frame', 0))),
                                                       '--text', str(a.get('text') or 'ACE')[:40], '--sub', str(a.get('sub') or '')[:40]]])],
    'pack': lambda p, a: ['ui/chain.py', json.dumps([['publish.py', p, 'info'], ['pack.py', p]])],
}


class ApiError(Exception):
    def __init__(self, msg, code=400): super().__init__(msg); self.code = code


def pdir(name):
    if not NAME.match(name or ''): raise ApiError('Nombre de proyecto inválido (minúsculas, números y guion bajo).')
    return os.path.join(PROJECTS, name)


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as fh: return json.load(fh)
    except (OSError, ValueError):
        return default


def job_state(name):
    j = JOBS.get(name)
    if not j: return None
    rc = j['proc'].poll()
    tail = ''
    try:
        with open(j['log'], encoding='utf-8', errors='replace') as fh: tail = fh.read()[-3000:]
    except OSError: pass
    return dict(task=j['task'], running=rc is None, code=rc, elapsed=round((j.get('t1') or time.time()) - j['t0'], 1), log=tail)


def start_job(name, task, args):
    if task not in TASKS: raise ApiError(f'Tarea desconocida: {task}')
    cur = JOBS.get(name)
    if cur and cur['proc'].poll() is None: raise ApiError(f'Ya hay una tarea en curso en este proyecto ({cur["task"]}).', 409)
    p = pdir(name)
    if task == 'auto' and not os.path.isdir(os.path.join(p, 'clips')):
        src = os.path.join(p, '_entrada')
        if not os.path.isdir(src): raise ApiError('Subí primero los clips y la canción.')
        cmd = [PY, os.path.join(ENGINE, 'auto.py'), src, '--name', name, '--plan-only']
    else:
        a = TASKS[task](p, args or {}); cmd = [PY, os.path.join(ENGINE, a[0]), *a[1:]]
    if task in ('draft', 'final'):
        try: os.remove(os.path.join(p, 'status.json'))
        except OSError: pass
    log = os.path.join(p, 'ui_job.log')
    fh = open(log, 'w', encoding='utf-8')
    proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    j = JOBS[name] = dict(proc=proc, task=task, t0=time.time(), log=log)
    threading.Thread(target=lambda: (proc.wait(), fh.close(), j.__setitem__('t1', time.time())), daemon=True).start()
    return job_state(name)


def list_projects():
    out = []
    for n in sorted(os.listdir(PROJECTS)) if os.path.isdir(PROJECTS) else []:
        p = os.path.join(PROJECTS, n)
        if not os.path.isdir(p) or not NAME.match(n): continue
        clips = os.path.join(p, 'clips')
        video = paths.find_video(n)
        out.append(dict(name=n, clips=len([f for f in os.listdir(clips) if f.endswith('.mp4')]) if os.path.isdir(clips) else 0,
                        kind='edit' if os.path.exists(proj.edit_path(p)) else ('plan' if os.path.exists(proj.plan_path(p)) else 'nuevo'),
                        draft=os.path.exists(os.path.join(p, 'borrador.mp4')), final=os.path.exists(video),
                        mtime=os.path.getmtime(proj.edit_path(p)) if os.path.exists(proj.edit_path(p)) else os.path.getmtime(p)))
    return sorted(out, key=lambda d: -d['mtime'])


def clips_info(p):
    """Cada clip con sus kills (lista final), lo que leyó el detector y su puntaje."""
    import score
    kf = read_json(os.path.join(p, 'kf.json'), {}); shots = read_json(os.path.join(p, 'shots.json'), {})
    conf = read_json(os.path.join(p, 'kf_conf.json'), {}); ver = set(map(str, read_json(os.path.join(p, 'verified.json'), [])))
    cd = os.path.join(p, 'clips'); out = []
    nums = sorted(int(f[1:-4]) for f in os.listdir(cd) if re.match(r'c\d+\.mp4$', f)) if os.path.isdir(cd) else []
    for c in nums:
        k = kf.get(str(c), []); evs = (conf.get(str(c)) or {}).get('kills', [])
        kills = []
        for t in k:
            near = min(evs, key=lambda e: abs(e['t'] - t), default=None)
            ok = near is not None and abs(near['t'] - t) <= 0.7
            kills.append(dict(t=t, conf=near['conf'] if ok else None, why=near.get('why', '') if ok else '', tipo=(near.get('tipo') or []) if ok else []))
        sc = score.score(dict(kills=shots.get(str(c), k), kill_types=[x['tipo'] for x in kills] if len(kills) == len(shots.get(str(c), k)) else None))
        out.append(dict(clip=c, kills=kills, shots=shots.get(str(c), []), verified=str(c) in ver or c in ver, score=sc['score'],
                        sin_killfeed=bool((conf.get(str(c)) or {}).get('sin_killfeed'))))
    return out


def project_data(name):
    p = pdir(name)
    if not os.path.isdir(p): raise ApiError('Ese proyecto no existe.', 404)
    d = dict(name=name, kind='nuevo', edit=None, timeline=None, error=None, song=None)
    song = read_json(os.path.join(p, 'song.json'))
    if song:
        d['song'] = {k: song.get(k) for k in ('duration', 'bpm', 'tempo', 'tempo_fixed', 'suggest', 'sync', 'sections')}
        d['song']['energy'] = song.get('energy_beats', [])
        try:
            import numpy as np
            d['song']['beats'] = [round(float(x), 3) for x in np.load(os.path.join(p, 'grid.npy'))]
        except Exception: d['song']['beats'] = []
    if os.path.exists(proj.edit_path(p)): d['kind'] = 'edit'; d['edit'] = proj.load_edit(p)
    elif os.path.exists(proj.plan_path(p)): d['kind'] = 'plan'
    if d['kind'] != 'nuevo':
        try:
            ns = proj.load_plan(p, quiet=True); d['timeline'] = planner.timeline(ns)
            st = preset.for_plan(ns)
        except (Exception, SystemExit) as e:
            d['error'] = str(e); st = preset.load()
    else:
        st = preset.load()
    d['style'] = {k: v for k, v in st.items() if k != '_dir'}
    d['clips'] = clips_info(p)
    d['uploads'] = sorted(os.listdir(os.path.join(p, '_entrada'))) if os.path.isdir(os.path.join(p, '_entrada')) else []
    d['files'] = dict(draft=os.path.exists(os.path.join(p, 'borrador.mp4')), final=os.path.exists(paths.find_video(name)),
                      doubt_sheet=os.path.exists(os.path.join(p, 'sheets', 'kf_dudosos.jpg')))
    pub = os.path.join(p, 'publish'); od = paths.project_dir(name)
    ls = lambda d_, ext: sorted(f for f in os.listdir(d_) if f.lower().endswith(ext)) if os.path.isdir(d_) else []
    d['delivery'] = dict(shorts=ls(os.path.join(od, 'shorts'), '.mp4'), thumbs=[f for f in ls(pub, '.jpg') if f.startswith('thumbnail')],
                         candidates=len(ls(os.path.join(pub, 'thumbs'), '.jpg')), info=read_json(os.path.join(pub, 'info.json')),
                         packed=os.path.exists(os.path.join(od, 'info', 'LEEME.md')), folder=od)
    d['check'] = (open(os.path.join(p, 'check_kills.txt'), encoding='utf-8').read() if os.path.exists(os.path.join(p, 'check_kills.txt')) else '')
    d['status'] = read_json(os.path.join(p, 'status.json')); d['job'] = job_state(name)
    return d


def save_edit(name, edit, dry=False):
    p = pdir(name)
    try:
        ns = planner.build(edit, p)                 # valida antes de guardar: un edit roto no pisa al que anda
    except (planner.EditError, preset.PresetError) as e:
        raise ApiError(str(e))
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise ApiError(f'El edit no se puede armar: falta o está mal {e}')
    if dry:                                         # solo calcular: para ver el resultado de arrastrar sin guardar
        return dict(timeline=planner.timeline(ns))
    proj.save_edit(p, edit)
    r = subprocess.run([PY, os.path.join(ENGINE, 'check_kills.py'), p], capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    open(os.path.join(p, 'check_kills.txt'), 'w', encoding='utf-8').write(r.stdout or '')
    return dict(timeline=planner.timeline(ns), check=r.stdout or '', style={k: v for k, v in preset.for_plan(ns).items() if k != '_dir'})


def save_kills(name, kills):
    """kills: {clip: [tiempos]}: la lista final, corregida a ojo. Marca esos clips como verificados y recalcula disparos."""
    p = pdir(name); f = os.path.join(p, 'kf.json')
    kf = read_json(f, {})
    for c, ts in kills.items():
        kf[str(int(c))] = sorted(round(float(t), 3) for t in ts)
    json.dump(kf, open(f, 'w'), indent=1)
    ver = set(map(str, read_json(os.path.join(p, 'verified.json'), []))) | {str(int(c)) for c in kills}
    json.dump(sorted(ver, key=int), open(os.path.join(p, 'verified.json'), 'w'))
    return start_job(name, 'shots', {})


def save_preset(name, body):
    if not NAME.match(name) or name == 'default': raise ApiError('Nombre de preset inválido (y "default" no se edita).')
    try:
        preset.merge(preset.default(), json.loads(json.dumps(body)))          # valida las claves
    except preset.PresetError as e:
        raise ApiError(str(e))
    d = os.path.join(preset.PRESETS, name); os.makedirs(d, exist_ok=True)
    json.dump(dict(body, name=name), open(os.path.join(d, 'preset.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    return dict(ok=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *a): pass

    def send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b))); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(b)

    def send_file(self, path):
        if not os.path.isfile(path): raise ApiError('No existe.', 404)
        size = os.path.getsize(path); a, b = 0, size - 1; code = 200
        m = re.match(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
        if m and (m.group(1) or m.group(2)):
            a = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2)))
            b = min(size - 1, int(m.group(2))) if m.group(1) and m.group(2) else size - 1
            code = 206
        self.send_response(code)
        self.send_header('Content-Type', mimetypes.guess_type(path)[0] or 'application/octet-stream')
        self.send_header('Accept-Ranges', 'bytes'); self.send_header('Content-Length', str(b - a + 1))
        if code == 206: self.send_header('Content-Range', f'bytes {a}-{b}/{size}')
        self.send_header('Cache-Control', 'no-cache'); self.end_headers()
        with open(path, 'rb') as fh:
            fh.seek(a); left = b - a + 1
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk: break
                try: self.wfile.write(chunk)
                except (ConnectionError, OSError): return
                left -= len(chunk)

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n).decode('utf-8')) if n else {}

    def route(self, method):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        parts = [urllib.parse.unquote(x) for x in u.path.strip('/').split('/') if x]
        if method == 'GET' and (not parts or parts[0] not in ('api', 'media')):
            f = os.path.normpath(os.path.join(STATIC, *parts)) if parts else os.path.join(STATIC, 'index.html')
            if not f.startswith(STATIC) or not os.path.isfile(f): f = os.path.join(STATIC, 'index.html')
            return self.send_file(f)
        if parts[0] == 'media':                       # /media/<proyecto>/<archivo dentro del proyecto> | /media/_fonts/x | /media/_out/<proyecto>
            if parts[1] == '_fonts': return self.send_file(os.path.join(ENGINE, 'assets', 'fonts', os.path.basename(parts[2])))
            if parts[1] == '_out': return self.send_file(paths.find_video(os.path.basename(pdir(parts[2]))))
            if parts[1] == '_dir':                      # /media/_dir/<proyecto>/<archivo dentro de output/<proyecto>/>
                base = paths.project_dir(os.path.basename(pdir(parts[2]))); f = os.path.normpath(os.path.join(base, *parts[3:]))
                if not f.startswith(base + os.sep): raise ApiError('Ruta inválida.')
                return self.send_file(f)
            base = pdir(parts[1]); f = os.path.normpath(os.path.join(base, *parts[2:]))
            if not f.startswith(base + os.sep): raise ApiError('Ruta inválida.')
            return self.send_file(f)
        p = parts[1:]
        if p == ['projects'] and method == 'GET': return self.send_json(list_projects())
        if p == ['projects'] and method == 'POST':
            name = self.body().get('name', ''); d = pdir(name)
            if os.path.exists(d): raise ApiError('Ya existe un proyecto con ese nombre.', 409)
            os.makedirs(os.path.join(d, '_entrada')); return self.send_json(dict(name=name))
        if p == ['presets'] and method == 'GET':
            return self.send_json(dict(names=preset.names(), channel=preset.config().get('preset') or 'default', default=preset.default()))
        if p == ['doctor']:
            r = subprocess.run([PY, os.path.join(ENGINE, 'doctor.py'), '--json'], capture_output=True, text=True, encoding='utf-8', errors='replace')
            return self.send_json(read_json_text(r.stdout))
        if len(p) >= 2 and p[0] == 'presets':
            if method == 'GET':
                f, _ = preset.find(p[1]) if p[1] != 'default' else (os.path.join(preset.PRESETS, 'default.json'), None)
                return self.send_json(dict(own=read_json(f, {}), merged={k: v for k, v in preset.load(p[1]).items() if k != '_dir'}))
            if method == 'PUT': return self.send_json(save_preset(p[1], self.body()))
        if p == ['config'] and method == 'PUT':
            b = self.body(); preset.load(b.get('preset'))
            json.dump(dict(preset.config(), preset=b.get('preset')), open(preset.CONFIG, 'w', encoding='utf-8'))
            return self.send_json(dict(ok=True))
        if len(p) >= 2 and p[0] == 'projects':
            name = p[1]; sub = p[2] if len(p) > 2 else ''
            if not sub and method == 'GET': return self.send_json(project_data(name))
            if sub == 'state' and method == 'GET':
                return self.send_json(dict(status=read_json(os.path.join(pdir(name), 'status.json')), job=job_state(name)))
            if sub == 'edit' and method == 'PUT': return self.send_json(save_edit(name, self.body(), dry='dry' in q))
            if sub == 'kills' and method == 'PUT': return self.send_json(save_kills(name, self.body()))
            if sub == 'run' and method == 'POST':
                b = self.body(); return self.send_json(start_job(name, b.get('task'), b.get('args')))
            if sub == 'stop' and method == 'POST':
                j = JOBS.get(name)
                if j and j['proc'].poll() is None: j['proc'].terminate()
                return self.send_json(dict(ok=True))
            if sub == 'migrate' and method == 'POST':
                import migrate
                edit, bad = migrate.migrate(pdir(name))
                if bad: raise ApiError('Este plan.py tiene lógica propia y no se puede pasar a edit.json sin cambiar el edit (' + ', '.join(bad) + ').')
                proj.save_edit(pdir(name), edit); return self.send_json(dict(ok=True))
            if sub == 'upload' and method == 'PUT':
                fn = os.path.basename((q.get('name') or [''])[0])
                if not fn.lower().endswith(('.mp4', '.mp3', '.wav', '.m4a', '.flac', '.png')): raise ApiError('Se aceptan clips .mp4, una canción (.mp3, .wav, .m4a, .flac) y logo.png.')
                d = pdir(name); dst = os.path.join(d, fn) if fn.lower() == 'logo.png' else os.path.join(d, '_entrada', fn)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                left = int(self.headers.get('Content-Length') or 0)
                with open(dst + '.part', 'wb') as fh:
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk: break
                        fh.write(chunk); left -= len(chunk)
                os.replace(dst + '.part', dst); return self.send_json(dict(ok=True, name=fn))
        raise ApiError('No existe.', 404)

    def handle_any(self, method):
        try:
            self.route(method)
        except ApiError as e:
            self.send_json(dict(error=str(e)), e.code)
        except (preset.PresetError, planner.EditError) as e:
            self.send_json(dict(error=str(e)), 400)
        except (ConnectionError, BrokenPipeError):
            pass
        except Exception as e:
            self.send_json(dict(error=f'{type(e).__name__}: {e}'), 500)

    def do_GET(self): self.handle_any('GET')
    def do_POST(self): self.handle_any('POST')
    def do_PUT(self): self.handle_any('PUT')


def read_json_text(s):
    try: return json.loads(s)
    except ValueError: return dict(error='No se pudo leer el diagnóstico.', raw=(s or '')[-800:])


def main():
    port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 8765
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://127.0.0.1:{port}'
    print(f'Editor en {url}  (Ctrl+C para cerrarlo)', flush=True)
    if '--no-browser' not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass


if __name__ == '__main__':
    main()
