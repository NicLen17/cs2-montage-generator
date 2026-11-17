"""Pipeline completo de un proyecto, usando todo el hardware local.

    python engine/build.py projects/<nombre>                 -> video final en output/
    python engine/build.py projects/<nombre> --preview 12.5,40,113   -> solo JPG en projects/<nombre>/previews/
    python engine/build.py projects/<nombre> --only 100-130   -> re-renderiza solo ese tramo (segundos) y reusa el resto

Opciones: --workers N (por defecto: núcleos lógicos - 2), --name archivo.mp4, --bitrate 30, --no-check
Al terminar un render completo corre check_render.py y guarda el reporte en projects/<nombre>/check_render.txt.
"""
import argparse, os, sys, subprocess, time, json, hashlib, shutil, importlib.util
from concurrent.futures import ThreadPoolExecutor

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)
from encoders import video_encoder_args, pick

PY = sys.executable
CHUNK_SEC = 6.0          # tamaño de cada pedazo de render (en segundos de video)


def load_plan(project):
    spec = importlib.util.spec_from_file_location('plan', os.path.join(project, 'plan.py'))
    cwd = os.getcwd(); os.chdir(project); sys.path.insert(0, project)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    os.chdir(cwd)
    return m


def run(cmd, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode != 0:
        raise SystemExit(f'Falló: {" ".join(map(str, cmd))}')
    return r


def ensure_slowmo(project, plan):
    """Genera las cámaras lentas interpoladas (240 fps) que pide el plan y que todavía no existen."""
    jobs = []
    for clip, (fname, t0) in getattr(plan, 'SLOWMO_SRC', {}).items():
        out = os.path.join(project, fname)
        if os.path.exists(out):
            continue
        dur = 1.0
        for s in plan.segments:
            if s['kind'] == 'slowmo' and s['clip'] == clip:
                dur = max(dur, s['s1'] - t0 + 0.3)
        jobs.append(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t0:.3f}', '-t', f'{dur:.3f}', '-i', os.path.join(project, 'clips', f'c{clip}.mp4'),
                     '-an', '-vf', 'minterpolate=fps=240:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1',
                     *video_encoder_args('intermediate'), out])
    if jobs:
        print(f'Cámaras lentas: generando {len(jobs)}...')
        with ThreadPoolExecutor(len(jobs)) as ex:
            list(ex.map(run, jobs))


def chunk_key(plan, a, b):
    """Huella de un pedazo: si no cambió nada que afecte esos cuadros, se reusa."""
    t0, t1 = a / plan.FPS - 1.0, b / plan.FPS + 1.0
    segs = [s for s in plan.segments if s['o1'] > t0 and s['o0'] < t1]
    kills = [k for k in plan.kills if t0 - 1 <= k <= t1]
    caps = [c for c in plan.captions if t0 - 2 <= c[0] <= t1]
    payload = json.dumps([segs, kills, caps, [b_ for b_ in plan.boundaries if t0 <= b_[0] <= t1],
                          getattr(plan, 'WORDS', []), _file_hash(os.path.join(ENGINE, 'render.py'))], default=str, sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def _file_hash(p):
    return hashlib.sha1(open(p, 'rb').read()).hexdigest()[:12]


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    ap = argparse.ArgumentParser()
    ap.add_argument('project'); ap.add_argument('--preview'); ap.add_argument('--workers', type=int)
    ap.add_argument('--name'); ap.add_argument('--bitrate', type=int, default=30); ap.add_argument('--only')
    ap.add_argument('--no-check', action='store_true', help='no correr check_render.py al terminar')
    args = ap.parse_args()
    project = os.path.abspath(args.project)
    plan = load_plan(project)

    if args.preview:
        ensure_slowmo(project, plan)
        times = args.preview.split(',')
        workers = args.workers or max(1, (os.cpu_count() or 4) - 2)
        groups = [','.join(times[i::workers]) for i in range(min(workers, len(times)))]
        with ThreadPoolExecutor(len(groups)) as ex:
            list(ex.map(lambda g: run([PY, os.path.join(ENGINE, 'render.py'), project, 'preview', g]), groups))
        print('Previews en', os.path.join(project, 'previews'))
        return

    t_start = time.time()
    print('Codificador de video:', pick())
    ensure_slowmo(project, plan)
    audio_job = subprocess.Popen([PY, os.path.join(ENGINE, 'audio.py'), project])

    N = int(round(plan.TOTAL * plan.FPS)); step = int(CHUNK_SEC * plan.FPS)
    chunks = [(a, min(N, a + step)) for a in range(0, N, step)]
    cache = os.path.join(project, 'render_cache'); os.makedirs(cache, exist_ok=True)
    todo, files = [], []
    for a, b in chunks:
        f = os.path.join(cache, f'{a:07d}_{chunk_key(plan, a, b)}.mp4')
        files.append(f)
        if not os.path.exists(f):
            todo.append((a, b, f))
    if args.only:
        lo, hi = [float(x) for x in args.only.split('-')]
        todo = [(a, b, f) for (a, b, f) in todo if b / plan.FPS >= lo and a / plan.FPS <= hi] + \
               [(a, b, f) for (a, b, f) in todo if not (b / plan.FPS >= lo and a / plan.FPS <= hi) and not os.path.exists(f)]
    workers = args.workers or max(1, (os.cpu_count() or 4) - 2)
    print(f'{len(chunks)} pedazos, {len(todo)} para renderizar (el resto se reusa), {workers} en paralelo')

    def job(c):
        a, b, f = c
        tmp = f + '.part.mp4'
        run([PY, os.path.join(ENGINE, 'render.py'), project, 'part', str(a), str(b), tmp], stdout=subprocess.DEVNULL)
        os.replace(tmp, f)
        return f
    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for _ in ex.map(job, todo):
            done += 1
            print(f'  pedazo {done}/{len(todo)}  ({time.time() - t_start:.0f}s)', flush=True)

    audio_job.wait()
    if audio_job.returncode != 0:
        raise SystemExit('Falló el audio')
    lst = os.path.join(cache, 'list.txt')
    with open(lst, 'w') as fh:
        for f in files:
            fh.write(f"file '{f.replace(os.sep, '/')}'\n")
    os.makedirs(os.path.join(ROOT, 'output'), exist_ok=True)
    name = args.name or (os.path.basename(project) + '.mp4')
    out = os.path.join(ROOT, 'output', name)
    run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-i', os.path.join(project, 'work_audio.wav'),
         '-map', '0:v', '-map', '1:a', *video_encoder_args('final', args.bitrate), '-r', str(plan.FPS),
         '-c:a', 'aac', '-b:a', '320k', '-shortest', '-movflags', '+faststart', out])
    # limpiar pedazos viejos que ya no se usan
    keep = set(files)
    for f in os.listdir(cache):
        p = os.path.join(cache, f)
        if p.endswith('.mp4') and p not in keep:
            os.remove(p)
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out],
                               capture_output=True, text=True).stdout or 0)
    print(f'\nListo: {out}  ({dur:.1f}s de video, {os.path.getsize(out) / 2**20:.0f} MB) en {time.time() - t_start:.0f}s')
    if abs(dur - plan.TOTAL) > 0.5:
        print('ATENCIÓN: la duración no coincide con el plan', plan.TOTAL)
    if not args.no_check:
        # chequeo final automático (tirones, 60 fps, duración, volumen): queda en projects/<nombre>/check_render.txt
        print('\nChequeo del render (check_render.py)...', flush=True)
        r = subprocess.run([PY, os.path.join(ENGINE, 'check_render.py'), project, out], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        rep = (r.stdout or '') + (r.stderr or '')
        with open(os.path.join(project, 'check_render.txt'), 'w', encoding='utf-8') as fh:
            fh.write(f'{out}\n{rep}')
        print(rep.strip())
        print('Guardado en', os.path.join(project, 'check_render.txt'))


if __name__ == '__main__':
    main()
