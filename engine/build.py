"""Pipeline completo de un proyecto, usando todo el hardware local.

    python engine/build.py projects/<nombre>                 -> video final en output/<nombre>/video/<nombre>.mp4
    python engine/build.py projects/<nombre> --preview 12.5,40,113   -> solo JPG en projects/<nombre>/previews/
    python engine/build.py projects/<nombre> --only 100-130   -> re-renderiza solo ese tramo (segundos) y reusa el resto
    python engine/build.py projects/<nombre> --draft          -> borrador 960x540 a 30 fps en projects/<nombre>/borrador.mp4

Opciones: --workers N (por defecto: núcleos lógicos - 2), --name archivo.mp4, --bitrate 30, --no-check
Al terminar un render completo corre check_render.py y guarda el reporte en projects/<nombre>/check_render.txt.

Cómo reparte el trabajo: N procesos de render.py quedan vivos (cargan clips, fuentes y GPU una sola vez) y van tomando
pedazos de 2 s de una cola, los más pesados primero (transiciones, kills, textos), así ningún núcleo queda parado al final.
Cada pedazo sale ya con la calidad final y se unen sin recodificar el video.
"""
import argparse, os, sys, subprocess, time, json, hashlib, shutil, importlib.util, threading, queue
from concurrent.futures import ThreadPoolExecutor

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)
from encoders import video_encoder_args, pick
import paths

PY = sys.executable
CHUNK_SEC = 2.0          # tamaño de cada pedazo de render (en segundos de video)
DRAFT_BITRATE = 8        # Mbps del borrador (960x540, 30 fps)
# procesos de render en modo GPU: en la RX 7900 XT 3 -> 73 s, 4 -> 62 s, 6 -> 55 s (ahí se llena el motor de video
# de la placa, que decodifica los clips y codifica la salida); más no suma
GPU_WORKERS = min(6, max(2, (os.cpu_count() or 4) // 2))
# ventanas de efecto (igual que TW en render.py): sirven solo para estimar cuánto pesa cada pedazo
TW = {'mega': 0.30, 'whip_lr': 0.13, 'whip_rl': 0.13, 'light': 0.17, 'zoom': 0.13, 'whip_short': 0.075, 'light_short': 0.085}


def load_plan(project):
    """edit.json (datos, lo arma planner.py) o, en proyectos anteriores, plan.py: ver engine/project.py."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import project as _project
    return _project.load_plan(project)


def run(cmd, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        raise SystemExit(f'Falló: {" ".join(map(str, cmd))}')
    return r


RIFE_DIR = os.path.join(ROOT, 'tools', 'rife')
RIFE_MODEL = 'rife-v4.6'


def rife_exe():
    """RIFE (rife-ncnn-vulkan, Vulkan: AMD, NVIDIA e Intel) si está instalado con engine/setup_rife.py; si no, None."""
    exe = os.path.join(RIFE_DIR, 'rife-ncnn-vulkan.exe' if os.name == 'nt' else 'rife-ncnn-vulkan')
    return exe if os.path.exists(exe) and os.path.isdir(os.path.join(RIFE_DIR, RIFE_MODEL)) else None


def slowmo_rife(exe, src, t0, dur, out):
    """Cámara lenta x4 (60 -> 240 fps) con RIFE en la GPU: ~7 s por segundo de video contra ~70 s de minterpolate.
    Cada 4.º cuadro es el original exacto (misma alineación que minterpolate: el cuadro 0 es el primero desde t0)."""
    tmp = out + '.tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, 'in')); os.makedirs(os.path.join(tmp, 'out'))
    try:
        run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t0:.3f}', '-t', f'{dur:.3f}', '-i', src, '-an',
             '-fps_mode', 'passthrough', os.path.join(tmp, 'in', '%08d.png')])
        n = len(os.listdir(os.path.join(tmp, 'in')))
        cmd = [exe, '-i', os.path.join(tmp, 'in'), '-o', os.path.join(tmp, 'out'), '-n', str(4 * n),
               '-m', os.path.join(RIFE_DIR, RIFE_MODEL), '-j', '2:4:4', '-f', '%08d.png']
        if os.environ.get('WAKO_RIFE_GPU'):         # por defecto RIFE elige la placa dedicada
            cmd += ['-g', os.environ['WAKO_RIFE_GPU']]
        run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run(['ffmpeg', '-v', 'error', '-y', '-framerate', '240', '-i', os.path.join(tmp, 'out', '%08d.png'),
             *video_encoder_args('intermediate'), out])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ensure_slowmo(project, plan):
    """Genera las cámaras lentas interpoladas (240 fps) que pide el plan y que todavía no existen.
    Con RIFE instalado (python engine/setup_rife.py) las hace en la GPU; si no, con minterpolate de ffmpeg (CPU, lento)."""
    jobs = []
    for clip, (fname, t0) in getattr(plan, 'SLOWMO_SRC', {}).items():
        out = os.path.join(project, fname)
        if os.path.exists(out):
            continue
        dur = 1.0
        for s in plan.segments:
            if s['kind'] == 'slowmo' and s['clip'] == clip:
                dur = max(dur, s['s1'] - t0 + 0.3)
        jobs.append((os.path.join(project, 'clips', f'c{clip}.mp4'), t0, dur, out))
    if not jobs:
        return
    exe = rife_exe()
    t = time.time()
    if exe:
        print(f'Cámaras lentas: generando {len(jobs)} con RIFE (GPU)...')
        for src, t0, dur, out in jobs:          # de a una: la GPU es una sola
            slowmo_rife(exe, src, t0, dur, out)
    else:
        print(f'Cámaras lentas: generando {len(jobs)} con minterpolate (CPU, ~70 s por segundo; '
              f'para hacerlas ~10 veces más rápido instalá RIFE: python engine/setup_rife.py)...')
        cmds = [['ffmpeg', '-v', 'error', '-y', '-ss', f'{t0:.3f}', '-t', f'{dur:.3f}', '-i', src, '-an', '-vf',
                 'minterpolate=fps=240:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1',
                 *video_encoder_args('intermediate'), out] for src, t0, dur, out in jobs]
        with ThreadPoolExecutor(len(cmds)) as ex:
            list(ex.map(run, cmds))
    print(f'Cámaras lentas listas en {time.time() - t:.0f}s')


STYLE_KEY = ''          # huella del estilo (preset + logo): si cambia, se vuelve a renderizar


def load_style(project, plan):
    """Carga el preset del proyecto y deja su huella para el caché de pedazos."""
    global STYLE_KEY
    import preset
    st = preset.for_plan(plan)
    TW.update(st['transitions']['durations'])
    logo = preset.logo_path(st, project)
    globals()['AUDIO_STYLE'] = json.dumps(st['audio'], sort_keys=True)
    STYLE_KEY = hashlib.sha1((json.dumps({k: v for k, v in st.items() if k not in ('_dir', 'audio', 'cuts')}, sort_keys=True)
                              + _file_hash(logo) + _file_hash(os.path.join(ENGINE, 'gpu.py'))).encode()).hexdigest()[:12]
    return st


def chunk_key(plan, a, b, enc=''):
    """Huella de un pedazo: si no cambió nada que afecte esos cuadros (ni el codificador/bitrate), se reusa."""
    t0, t1 = a / plan.FPS - 1.0, b / plan.FPS + 1.0
    segs = [s for s in plan.segments if s['o1'] > t0 and s['o0'] < t1]
    kills = [k for k in plan.kills if t0 - 1 <= k <= t1]
    caps = [c for c in plan.captions if t0 - 2 <= c[0] <= t1]
    payload = json.dumps([segs, kills, caps, [b_ for b_ in plan.boundaries if t0 <= b_[0] <= t1], STYLE_KEY,
                          getattr(plan, 'WORDS', []), _file_hash(os.path.join(ENGINE, 'render.py')),
                          _file_hash(os.path.join(ENGINE, 'encoders.py')), enc], default=str, sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def chunk_weight(plan, a, b):
    """Estimación de cuánto tarda un pedazo: los cuadros con transición, kill, texto o intro/cierre cuestan ~3 veces
    lo que un cuadro plano (que va entero a la GPU)."""
    fx = 0
    segs = plan.segments
    for n in range(a, b, 2):
        t = n / plan.FPS
        S = next((s for s in segs if s['o0'] <= t < s['o1']), segs[-1])
        if (S['kind'] != 'play' or any(-0.017 <= t - k <= 0.7 for k in plan.kills)
                or any((typ in TW and abs(t - ob) < TW[typ]) or (typ == 'black_in' and ob - 1.4 <= t < ob)
                       for ob, typ, _ in plan.boundaries)
                or any(-0.1 <= t - c[0] <= 1.7 for c in plan.captions)):
            fx += 2
    return (b - a) + 2 * fx


class Workers:
    """Procesos de render.py que quedan vivos y toman pedazos de una cola (modo 'serve')."""
    def __init__(self, project, n):
        self.procs = [subprocess.Popen([PY, os.path.join(ENGINE, 'render.py'), project, 'serve'], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1) for _ in range(n)]

    def run(self, jobs, on_done):
        """jobs: lista de (a, b, archivo_final, bitrate, paso) ya ordenada (los más pesados primero)."""
        q = queue.Queue()
        for j in jobs: q.put(j)
        errors = []

        def feed(p):
            while not errors:
                try: a, b, f, br, st = q.get_nowait()
                except queue.Empty: return
                tmp = f + '.part.mp4'
                p.stdin.write(f'{a}\t{b}\t{tmp}\t{br}\t{st}\n'); p.stdin.flush()
                while True:
                    line = p.stdout.readline()
                    if not line:
                        errors.append(f'el proceso de render se cortó en el pedazo {a}-{b}'); return
                    if line.startswith('@@done'): break
                os.replace(tmp, f); on_done(f)
        ts = [threading.Thread(target=feed, args=(p,)) for p in self.procs]
        for t in ts: t.start()
        for t in ts: t.join()
        if errors: raise SystemExit('Falló el render: ' + errors[0])

    def close(self):
        for p in self.procs:
            try: p.stdin.close()
            except Exception: pass
        for p in self.procs: p.wait()


def _file_hash(p):
    return hashlib.sha1(open(p, 'rb').read()).hexdigest()[:12]


AUDIO_STYLE = ''         # la parte de audio del preset: si cambia, se vuelve a mezclar
AUDIO_OUT = ('work_audio.wav', 'audio_balance.txt', 'render_log.txt', 'check_render.txt', 'borrador.mp4', 'audio.key',
             'status.json', 'timeline.json')


def _audio_key(project):
    """Huella de todo lo que usa audio.py: el plan y los datos del proyecto, los clips, las voces separadas, la canción
    y los scripts de audio. Si no cambió nada, se reusa work_audio.wav (la mezcla tarda ~40 s)."""
    h = hashlib.sha1()
    h.update(AUDIO_STYLE.encode())
    for name in ('audio.py', 'reactions.py'):
        p = os.path.join(ENGINE, name)
        if os.path.exists(p):
            h.update(open(p, 'rb').read())
    for k in sorted(os.environ):
        if k.startswith('WAKO_AUDIO'):
            h.update(f'{k}={os.environ[k]}'.encode())
    for f in sorted(os.listdir(project)):
        p = os.path.join(project, f)
        if os.path.isfile(p) and f not in AUDIO_OUT and not f.endswith('.mp4'):
            st = os.stat(p)
            h.update(f'{f}|{st.st_size}|{st.st_mtime_ns}'.encode())
    for sub in ('clips', 'clip_stems'):
        for root, _, files in os.walk(os.path.join(project, sub)):
            for f in sorted(files):
                st = os.stat(os.path.join(root, f))
                h.update(f'{os.path.relpath(os.path.join(root, f), project)}|{st.st_size}|{st.st_mtime_ns}'.encode())
    return h.hexdigest()


def start_audio(project):
    """Arranca audio.py en paralelo con el render, salvo que work_audio.wav ya esté hecho con los mismos datos."""
    key, wav = os.path.join(project, 'audio.key'), os.path.join(project, 'work_audio.wav')
    if os.path.exists(wav) and os.path.exists(key) and open(key).read().strip() == _audio_key(project):
        print('Audio: sin cambios, se reusa work_audio.wav')
        return None
    if os.path.exists(key):
        os.remove(key)
    return subprocess.Popen([PY, os.path.join(ENGINE, 'audio.py'), project])


def _write_audio_key(project):
    with open(os.path.join(project, 'audio.key'), 'w') as fh:
        fh.write(_audio_key(project))


def resolve_device(req):
    """'auto' -> GPU si hay OpenGL 4.3 y ModernGL (engine/gpu.py), si no CPU. 'gpu' sin GPU usable -> error claro."""
    if req == 'cpu':
        return 'cpu', None
    try:
        import gpu
        return 'gpu', gpu.init(64, 64)
    except Exception as e:
        if req == 'gpu':
            raise SystemExit(f'--device gpu: no se pudo usar la GPU ({e}). Instalá moderngl (pip install moderngl) '
                             f'y actualizá el driver de video, o usá --device cpu.')
        return 'cpu', None


def default_workers(device):
    """CPU: núcleos lógicos - 2 (igual rinde lo mismo desde ~5: el límite es la RAM). GPU: pocos procesos alcanzan
    para tener la placa ocupada mientras la CPU lee los clips y codifica."""
    if device == 'gpu':
        return GPU_WORKERS
    return max(1, (os.cpu_count() or 4) - 2)


STAGES = [('preparando', 'Leer el plan y el estilo'), ('camaras_lentas', 'Cámaras lentas'), ('render', 'Render de video'),
          ('audio', 'Mezcla de audio'), ('uniendo', 'Unir video y audio'), ('verificando', 'Verificar el resultado'),
          ('listo', 'Listo')]


class Status:
    """Estado del render en projects/<nombre>/status.json, para quien quiera mostrar el paso a paso (la interfaz web, un
    script): etapa actual, pedazos hechos / totales, tiempo transcurrido y estimado, dispositivo y archivo de salida."""
    def __init__(self, project, **kw):
        self.path = os.path.join(project, 'status.json'); self.t0 = time.time()
        self.d = dict(stage='preparando', done=0, total=0, started=self.t0, stages=[dict(id=a, label=b) for a, b in STAGES], **kw)
        self.write()

    def update(self, **kw):
        self.d.update(kw); self.write()

    def write(self):
        d = dict(self.d, elapsed=round(time.time() - self.t0, 1), updated=time.time(), pid=os.getpid())
        if d['stage'] == 'render' and d['done'] and d['total']:
            t = time.time() - d.get('render_t0', self.t0)
            d['eta'] = round(t / d['done'] * (d['total'] - d['done']), 1)
        try:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh: json.dump(d, fh, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass                      # el estado es informativo: nunca frena un render


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    try:
        _main()
    except SystemExit as e:
        if e.code not in (None, 0) and STATUS[0]: STATUS[0].update(stage='error', message=str(e.code))
        raise
    except Exception as e:
        if STATUS[0]: STATUS[0].update(stage='error', message=f'{type(e).__name__}: {e}')
        raise


STATUS = [None]


def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project'); ap.add_argument('--preview'); ap.add_argument('--workers', type=int)
    ap.add_argument('--name'); ap.add_argument('--bitrate', type=int, help='Mbps (por defecto, el del preset: 30)')
    ap.add_argument('--only')
    ap.add_argument('--no-check', action='store_true', help='no correr check_render.py al terminar')
    ap.add_argument('--draft', action='store_true', help='borrador rápido 960x540 a 30 fps en projects/<nombre>/borrador.mp4')
    ap.add_argument('--device', choices=['auto', 'gpu', 'cpu'], default=os.environ.get('WAKO_DEVICE', 'auto'),
                    help='dónde se procesan los cuadros: gpu (todo en la placa), cpu (todo en el procesador) o auto')
    args = ap.parse_args()
    project = os.path.abspath(args.project)
    plan = load_plan(project)
    style = load_style(project, plan)
    if args.bitrate is None: args.bitrate = int(style['output']['bitrate'])
    print('Estilo:', style['name'])
    device, gpu_name = resolve_device(args.device)
    os.environ['WAKO_DEVICE'] = device          # los procesos de render lo heredan
    print('Dispositivo:', f'GPU ({gpu_name})' if device == 'gpu' else 'CPU')

    if args.preview:
        ensure_slowmo(project, plan)
        times = args.preview.split(',')
        workers = args.workers or default_workers(device)
        groups = [','.join(times[i::workers]) for i in range(min(workers, len(times)))]
        with ThreadPoolExecutor(len(groups)) as ex:
            list(ex.map(lambda g: run([PY, os.path.join(ENGINE, 'render.py'), project, 'preview', g]), groups))
        print('Previews en', os.path.join(project, 'previews'))
        return

    t_start = time.time()
    os.environ['WAKO_ENCODER'] = pick()       # se detecta una vez; los procesos de render lo heredan
    print('Codificador de video:', os.environ['WAKO_ENCODER'])
    status = STATUS[0] = Status(project, draft=bool(args.draft), device=device, gpu=gpu_name, encoder=os.environ['WAKO_ENCODER'],
                                style=style['name'], total_seconds=round(float(plan.TOTAL), 2))
    if getattr(plan, 'SLOWMO_SRC', None): status.update(stage='camaras_lentas')
    ensure_slowmo(project, plan)
    audio_job = start_audio(project)

    draft = args.draft
    st, br = (2, DRAFT_BITRATE) if draft else (1, args.bitrate)
    enc_tag = f"{os.environ['WAKO_ENCODER']}|{br}|{st}|{device}"
    N = int(round(plan.TOTAL * plan.FPS)); step = int(CHUNK_SEC * plan.FPS)
    chunks = [(a, min(N, a + step)) for a in range(0, N, step)]
    cache = os.path.join(project, 'render_cache_draft' if draft else 'render_cache'); os.makedirs(cache, exist_ok=True)
    todo, files = [], []
    for a, b in chunks:
        f = os.path.join(cache, f'{a:07d}_{chunk_key(plan, a, b, enc_tag)}.mp4')
        files.append(f)
        if not os.path.exists(f):
            todo.append((a, b, f))
    # los más pesados primero; con --only, primero ese tramo
    todo.sort(key=lambda c: -chunk_weight(plan, c[0], c[1]))
    if args.only:
        lo, hi = [float(x) for x in args.only.split('-')]
        todo.sort(key=lambda c: not (c[1] / plan.FPS >= lo and c[0] / plan.FPS <= hi))
    workers = min(args.workers or default_workers(device), max(1, len(todo)))
    print(f'{len(chunks)} pedazos, {len(todo)} para renderizar (el resto se reusa), {workers} en paralelo'
          + ('  [BORRADOR 960x540 30 fps]' if draft else ''))

    done = [0]
    status.update(stage='render', done=0, total=len(todo), chunks=len(chunks), workers=workers, render_t0=time.time())
    def on_done(f):
        done[0] += 1
        status.update(done=done[0])
        if done[0] % 5 == 0 or done[0] == len(todo):
            print(f'  pedazo {done[0]}/{len(todo)}  ({time.time() - t_start:.0f}s)', flush=True)
    if todo:
        pool = Workers(project, workers)
        try: pool.run([(a, b, f, br, st) for a, b, f in todo], on_done)
        finally: pool.close()

    if audio_job is not None:
        status.update(stage='audio')
        audio_job.wait()
        if audio_job.returncode != 0:
            raise SystemExit('Falló el audio')
        _write_audio_key(project)
    status.update(stage='uniendo')
    lst = os.path.join(cache, 'list.txt')
    with open(lst, 'w') as fh:
        for f in files:
            fh.write(f"file '{f.replace(os.sep, '/')}'\n")
    if draft:
        out = os.path.join(project, args.name or 'borrador.mp4')
    else:
        out = paths.video_path(os.path.basename(project), args.name)      # output/<nombre>/video/
    # los pedazos ya tienen la calidad final: se unen sin recodificar el video (solo se codifica el audio)
    run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-i', os.path.join(project, 'work_audio.wav'),
         '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k' if draft else '320k',
         '-shortest', '-movflags', '+faststart', out])
    # limpiar pedazos viejos que ya no se usan
    keep = set(files)
    for f in os.listdir(cache):
        p = os.path.join(cache, f)
        if p.endswith('.mp4') and p not in keep:
            os.remove(p)
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out],
                               capture_output=True, text=True).stdout or 0)
    print(f'\nListo: {out}  ({dur:.1f}s de video, {os.path.getsize(out) / 2**20:.0f} MB) en {time.time() - t_start:.0f}s')
    if draft:
        print('Borrador: miralo entero y marcá los minutos a corregir (engine/locate.py). El render final es sin --draft.')
        status.update(stage='listo', out=out, duration=round(dur, 2)); return
    if abs(dur - plan.TOTAL) > 0.5:
        print('ATENCIÓN: la duración no coincide con el plan', plan.TOTAL)
    report = ''
    if not args.no_check:
        status.update(stage='verificando', out=out)
        # chequeo final automático (tirones, 60 fps, duración, volumen): queda en projects/<nombre>/check_render.txt
        print('\nChequeo del render (check_render.py)...', flush=True)
        r = subprocess.run([PY, os.path.join(ENGINE, 'check_render.py'), project, out], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        rep = (r.stdout or '') + (r.stderr or '')
        with open(os.path.join(project, 'check_render.txt'), 'w', encoding='utf-8') as fh:
            fh.write(f'{out}\n{rep}')
        print(rep.strip())
        print('Guardado en', os.path.join(project, 'check_render.txt'))
        report = rep.strip()
    status.update(stage='listo', out=out, duration=round(dur, 2), check=report)


if __name__ == '__main__':
    main()
