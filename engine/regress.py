"""Regresión de imagen: renderiza momentos fijos de un proyecto y los compara, cuadro a cuadro, contra una referencia.

    python engine/regress.py projects/<nombre> --save            guarda la referencia (tests/ref/<nombre>/, en CPU)
    python engine/regress.py projects/<nombre>                   compara el motor actual contra la referencia
    python engine/regress.py projects/<nombre> --device gpu      lo mismo, renderizando en la placa
    python engine/regress.py projects/<nombre> --cross           CPU contra GPU, sin referencia

Los momentos salen del plan (uno por transición, kill, título, intro, interludio y cierre; --max los limita) y quedan
anotados en la referencia, así un cambio en el plan no pasa por un cambio en el motor. Sale con código 1 si algún
cuadro queda por debajo de --min-psnr (45 dB por defecto: lo que separa CPU de GPU; un cambio real da 20-35 dB).
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import compat  # noqa: F401  (nombres viejos de las variables de entorno)
import argparse, json, os, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)
PY = sys.executable


def pick_times(plan, limit):
    """Momentos representativos: todos los tipos de cuadro que el motor sabe hacer."""
    ts = []
    for s in plan.segments:
        if s['kind'] != 'play':
            ts += [s['o0'] + 0.25 * (s['o1'] - s['o0']), s['o0'] + 0.7 * (s['o1'] - s['o0'])]
    seen = {}
    for ob, typ, _ in plan.boundaries:                 # dos de cada tipo de transición, en el medio
        if seen.setdefault(typ, 0) < 2:
            seen[typ] += 1; ts.append(ob + 0.01)
    fx = {}
    for i, k in enumerate(plan.kills):                 # dos de cada efecto de kill, en el pico
        tag = str(plan.kill_flash[i]) + '|' + str(i % max(1, len(getattr(plan, 'KILL_FX', [0]))))
        if fx.setdefault(tag, 0) < 2:
            fx[tag] += 1; ts.append(k + 0.05)
    ts += [c[0] + 0.5 for c in plan.captions[:3]]
    ts += [plan.TOTAL * x for x in (0.2, 0.4, 0.6, 0.8)]   # cuadros planos
    ts = sorted({round(min(max(t, 0.0), plan.TOTAL - 0.05), 2) for t in ts})
    if len(ts) > limit:
        ts = [ts[i] for i in np.linspace(0, len(ts) - 1, limit).round().astype(int)]
    return sorted(set(ts))


def render_raw(project, times, outdir, device, procs=3):
    os.makedirs(outdir, exist_ok=True)
    groups = [times[i::procs] for i in range(min(procs, len(times)))]
    env = {**os.environ, 'MONTAGE_DEVICE': device}

    def one(g):
        r = subprocess.run([PY, os.path.join(ENGINE, 'render.py'), project, 'raw', ','.join(f'{t:.2f}' for t in g), outdir],
                           env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r.returncode != 0:
            raise SystemExit(f'Falló el render ({device}):\n{r.stderr[-2000:]}')
    with ThreadPoolExecutor(len(groups)) as ex:
        list(ex.map(one, groups))
    return {t: np.load(os.path.join(outdir, f'{t:07.2f}.npy')) for t in times}


def psnr(a, b):
    mse = float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))
    return 99.0 if mse < 1e-9 else 10 * np.log10(255.0 ** 2 / mse)


def ref_dir(project):
    return os.path.join(ROOT, 'tests', 'ref', os.path.basename(os.path.abspath(project)))


def save_ref(project, frames):
    import cv2
    d = ref_dir(project); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    for t, f in frames.items():
        cv2.imwrite(os.path.join(d, f'{t:07.2f}.png'), f)
    json.dump(sorted(frames), open(os.path.join(d, 'times.json'), 'w'))
    return d


def load_ref(project):
    import cv2
    d = ref_dir(project)
    if not os.path.exists(os.path.join(d, 'times.json')):
        raise SystemExit(f'No hay referencia en {d}: corré primero con --save')
    times = json.load(open(os.path.join(d, 'times.json')))
    return {t: cv2.imread(os.path.join(d, f'{t:07.2f}.png')) for t in times}


def compare(a, b, min_psnr, label):
    rows = [(t, psnr(a[t], b[t])) for t in sorted(a)]
    bad = [(t, p) for t, p in rows if p < min_psnr]
    vals = [p for _, p in rows]
    print(f'{label}: {len(rows)} cuadros, PSNR mínimo {min(vals):.1f} dB, mediana {float(np.median(vals)):.1f} dB')
    for t, p in bad:
        print(f'  FALLA t={t:.2f}s  {p:.1f} dB (< {min_psnr})')
    return not bad


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project'); ap.add_argument('--save', action='store_true'); ap.add_argument('--cross', action='store_true')
    ap.add_argument('--device', choices=['cpu', 'gpu'], default='cpu'); ap.add_argument('--max', type=int, default=40)
    ap.add_argument('--min-psnr', type=float, default=45.0)
    args = ap.parse_args()
    project = os.path.abspath(args.project)
    tmp = tempfile.mkdtemp(prefix='regress_')
    try:
        if args.save or args.cross:
            from build import load_plan
            times = pick_times(load_plan(project), args.max)
        if args.save:
            d = save_ref(project, render_raw(project, times, os.path.join(tmp, 'cpu'), 'cpu'))
            print(f'Referencia guardada: {len(times)} cuadros en {d}')
            return 0
        if args.cross:
            a = render_raw(project, times, os.path.join(tmp, 'cpu'), 'cpu')
            b = render_raw(project, times, os.path.join(tmp, 'gpu'), 'gpu')
            return 0 if compare(a, b, args.min_psnr, 'CPU contra GPU') else 1
        ref = load_ref(project)
        cur = render_raw(project, sorted(ref), os.path.join(tmp, args.device), args.device)
        return 0 if compare(ref, cur, args.min_psnr, f'Referencia contra motor actual ({args.device})') else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
