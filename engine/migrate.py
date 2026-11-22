"""Pasa un proyecto viejo (plan.py, código) al formato nuevo (edit.json, datos).

    python engine/migrate.py projects/<nombre>            prueba: dice si el edit.json daría exactamente el mismo edit
    python engine/migrate.py projects/<nombre> --write    lo escribe (plan.py queda como plan_viejo.py)
    python engine/migrate.py --all                        prueba todos los proyectos

Ejecuta el plan.py, toma sus datos (plays, tiempos de la canción, cámara, títulos) y comprueba que planner.py arme con
ellos el mismo timeline, cuadro por cuadro. Si un plan.py tiene lógica propia que el planificador no conoce, lo dice y
no escribe nada: ese proyecto sigue funcionando con su plan.py.
"""
import json, os, sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)
import planner
from project import load_plan, save_edit, edit_path, plan_path

COMPARE = ('segments', 'kills', 'kill_play', 'kill_id', 'kill_flash', 'captions', 'boundaries', 'TOTAL', 'FPS', 'WORDS',
           'PHRASES', 'INTER', 'O_DROP2', 'REV0', 'OUTRO0', 'SONG_A0', 'song_map', 'KILL_FX', 'SYNC', 'CAM', 'SLOWMO_SRC',
           'OPEN_CLIP', 'END_CLIP', 'ACE_CLIP', 'END_LEN', 'OUTRO_LEN', 'REVEAL', 'SONG_TITLE') + planner.AUDIO_KEYS


def norm(x):
    import numpy as np
    if isinstance(x, (np.floating, float)): return round(float(x), 6)
    if isinstance(x, np.integer): return int(x)
    if isinstance(x, np.ndarray): return [norm(v) for v in x.tolist()]
    if isinstance(x, dict): return {str(k): norm(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (set, frozenset)): return sorted(norm(v) for v in x)
    if isinstance(x, (list, tuple)): return [norm(v) for v in x]
    return x


def to_edit(m):
    """Los datos de un plan.py ya ejecutado, como edit.json."""
    g = lambda k, d=None: getattr(m, k, d)
    edit = {
        'version': planner.VERSION,
        'preset': 'default',
        'fps': int(m.FPS),
        'song': {'title': g('SONG_TITLE', ''), 'start': float(m.SONG_A0), 'drop1': float(m.grid[m.IDX_DROP]),
                 'drop2': float(m.grid[m.I_DROP2]), 'sync': planner._plain(g('SYNC', []))},
        'open': {'clip': int(m.OPEN_CLIP), 'end': float(m.OPEN_END)},
        'close': {'clip': int(m.END_CLIP), 'len': float(m.END_LEN)},
        'outro_len': float(m.OUTRO_LEN),
        'ace_clip': g('ACE_CLIP'),
        'cam': planner._plain(g('CAM', {})),
        'reveal': bool(g('REVEAL', False)),
        'act1': [planner.play_to_json(P) for P in m.ACT1],
        'act2': [planner.play_to_json(P) for P in m.ACT2],
        'transitions': list(m.BT),
    }
    if g('FRANTIC'): edit['song']['frantic'] = planner._plain(m.FRANTIC)
    if g('REV_SHIFT'): edit['rev_shift'] = float(m.REV_SHIFT)
    if g('VOC', 0.03) != 0.03: edit['voc'] = float(m.VOC)
    if g('LEAD_PLUS'): edit['lead_plus'] = float(m.LEAD_PLUS)
    if g('TAIL_MAX') is not None: edit['tail_fill'] = {'max': m.TAIL_MAX, 'max_in': g('TAIL_MAX_IN', m.TAIL_MAX)}
    if g('SLOWMO_SRC'): edit['slowmo_src'] = planner._plain(m.SLOWMO_SRC)
    if g('WORDS'):
        edit['words'] = planner._plain(m.WORDS); edit['vanish'] = planner._plain(m.VANISH)
    if g('KILL_FX_BASE') is not None:
        edit['kill_fx'] = list(m.KILL_FX_BASE); edit['kill_fx_bright'] = True
    else:
        edit['kill_fx'] = list(m.KILL_FX); edit['kill_fx_bright'] = False
    audio = {k: planner._plain(getattr(m, k)) for k in planner.AUDIO_KEYS if hasattr(m, k)}
    if audio: edit['audio'] = audio
    return edit


def diff(a, b):
    """Nombres del plan que no coinciden entre el plan.py (a) y el planificador (b)."""
    bad = []
    for k in COMPARE:
        if hasattr(a, k) and norm(getattr(a, k)) != norm(getattr(b, k, None)):
            bad.append(k)
    return bad


def migrate(project):
    """(edit, diferencias). diferencias == [] -> el edit.json reproduce el plan.py exactamente."""
    m = load_plan(project, source='py', quiet=True)
    edit = to_edit(m)
    ns = planner.build(edit, project)
    if norm(ns.KILL_FX) != norm(m.KILL_FX) and len(m.KILL_FX) >= len(m.kills):     # regla propia: efectos uno por uno
        edit['kill_fx_explicit'] = list(m.KILL_FX)
        ns = planner.build(edit, project)
    return edit, diff(m, ns)


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--all' in sys.argv:
        pj = os.path.join(ROOT, 'projects')
        args = [os.path.join(pj, p) for p in sorted(os.listdir(pj)) if os.path.exists(plan_path(os.path.join(pj, p)))]
    if not args:
        raise SystemExit(__doc__)
    fail = 0
    for project in args:
        project = os.path.abspath(project); name = os.path.basename(project)
        try:
            edit, bad = migrate(project)
        except Exception as e:
            print(f'{name}: no se pudo migrar ({type(e).__name__}: {e})'); fail += 1; continue
        if bad:
            print(f'{name}: el plan.py tiene lógica propia; con edit.json cambiaría: {", ".join(bad)}. Sigue con plan.py.')
            fail += 1; continue
        if '--write' in sys.argv:
            save_edit(project, edit)
            os.replace(plan_path(project), os.path.join(project, 'plan_viejo.py'))
            print(f'{name}: escrito {edit_path(project)} (el plan.py quedó como plan_viejo.py)')
        else:
            print(f'{name}: OK, edit.json daría el mismo edit ({len(edit["act1"]) + len(edit["act2"])} plays)')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
