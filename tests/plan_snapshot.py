"""Foto de lo que produce el plan de cada proyecto (tramos, kills, títulos, transiciones, duración).

    python tests/plan_snapshot.py --save      guarda tests/ref/plans/<proyecto>.json de todos los proyectos que cargan

test_plans.py compara contra esas fotos: cualquier cambio en cómo se arma el timeline (planner, cargador de proyectos)
que mueva un solo cuadro de un edit ya hecho hace fallar la prueba.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'engine'))
REF = os.path.join(ROOT, 'tests', 'ref', 'plans')
KEYS = ('segments', 'kills', 'kill_play', 'kill_id', 'kill_flash', 'captions', 'boundaries', 'TOTAL', 'FPS', 'WORDS',
        'PHRASES', 'INTER', 'O_DROP2', 'REV0', 'OUTRO0', 'SONG_A0', 'song_map', 'KILL_FX')


def norm(x):
    import numpy as np
    if isinstance(x, (np.floating, float)): return round(float(x), 6)
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, np.ndarray): return [norm(v) for v in x.tolist()]
    if isinstance(x, dict): return {str(k): norm(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (list, tuple, set)): return [norm(v) for v in (sorted(x) if isinstance(x, set) else x)]
    return x


def load(project):
    try:
        from project import load_plan          # cargador único (Fase 1)
    except ImportError:
        from build import load_plan
    return load_plan(project)


def snapshot(project):
    m = load(project)
    return {k: norm(getattr(m, k)) for k in KEYS if hasattr(m, k)}


def projects():
    pj = os.path.join(ROOT, 'projects')
    return sorted(p for p in os.listdir(pj) if os.path.exists(os.path.join(pj, p, 'plan.py')) or os.path.exists(os.path.join(pj, p, 'edit.json')))


if __name__ == '__main__':
    import contextlib, io
    os.makedirs(REF, exist_ok=True)
    for p in projects():
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                s = snapshot(os.path.join(ROOT, 'projects', p))
        except Exception as e:
            print(f'{p}: no carga ({type(e).__name__}: {e})'); continue
        json.dump(s, open(os.path.join(REF, p + '.json'), 'w', encoding='utf-8'), indent=0, sort_keys=True)
        print(f'{p}: {len(s["segments"])} tramos, {len(s["kills"])} kills, TOTAL {s["TOTAL"]:.2f}s')
