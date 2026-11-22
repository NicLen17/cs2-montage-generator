"""Presets: el estilo de un canal como datos.

    presets/default.json            el estilo base del motor (todas las claves, con su valor de fábrica)
    presets/<nombre>.json           un estilo: solo las claves que cambia
    presets/<nombre>/preset.json    lo mismo, con sus archivos al lado (logo.png, fuentes)

Qué preset usa un proyecto, de más a menos prioridad:
    1. "preset" en projects/<nombre>/edit.json (o PRESET en un plan.py)
    2. "preset" en config.json, en la raíz del repo: el preset del canal, para todos sus proyectos
    3. default
Encima de eso, "style" en edit.json (o STYLE en plan.py) pisa valores sueltos solo para ese proyecto.

    python engine/preset.py                       lista los presets
    python engine/preset.py <nombre>              muestra el preset ya mezclado con default
    python engine/preset.py --project projects/x  el estilo final de un proyecto
"""
import copy, json, os, sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
PRESETS = os.path.join(ROOT, 'presets')
CONFIG = os.path.join(ROOT, 'config.json')
META = ('name', 'description', 'author', 'based_on')


class PresetError(ValueError):
    pass


def _read(path):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise PresetError(f'{path}: no es JSON válido (línea {e.lineno}: {e.msg})') from None


def default():
    return _read(os.path.join(PRESETS, 'default.json'))


def find(name):
    """(archivo, carpeta de sus archivos) de un preset por nombre."""
    for f, d in ((os.path.join(PRESETS, name + '.json'), PRESETS),
                 (os.path.join(PRESETS, name, 'preset.json'), os.path.join(PRESETS, name))):
        if os.path.exists(f): return f, d
    raise PresetError(f'no existe el preset "{name}". Disponibles: {", ".join(names())}')


def names():
    out = []
    for f in sorted(os.listdir(PRESETS)) if os.path.isdir(PRESETS) else []:
        if f.endswith('.json'): out.append(f[:-5])
        elif os.path.exists(os.path.join(PRESETS, f, 'preset.json')): out.append(f)
    return out


def merge(base, over, where=''):
    """Pisa base con over, clave por clave. Una clave que default no tiene es un error (casi siempre, un typo)."""
    for k, v in over.items():
        if not where and k in META:
            base[k] = v; continue
        if k not in base:
            raise PresetError(f'"{where}{k}" no existe. Claves válidas en {where or "el preset"}: {", ".join(x for x in base if x not in META)}')
        if isinstance(base[k], dict) and isinstance(v, dict) and k not in ('durations', 'pre_min', 'post_min', 'pre_max', 'post_max'):
            merge(base[k], v, f'{where}{k}.')
        elif isinstance(base[k], dict) and isinstance(v, dict):
            bad = [x for x in v if x not in base[k]]
            if bad: raise PresetError(f'"{where}{k}.{bad[0]}" no existe. Claves válidas: {", ".join(base[k])}')
            base[k].update(v)
        else:
            base[k] = v
    return base


def config():
    return _read(CONFIG) if os.path.exists(CONFIG) else {}


def load(name=None, style=None):
    """El estilo completo: default <- preset <- style. Deja en '_dir' la carpeta del preset (para su logo)."""
    st = default()
    name = name or config().get('preset') or 'default'
    d = PRESETS
    if name != 'default':
        f, d = find(name)
        over = _read(f)
        parent = over.get('based_on')
        if parent and parent != 'default':
            merge(st, {k: v for k, v in _read(find(parent)[0]).items() if k not in META})
        merge(st, over)
    if style:
        merge(st, copy.deepcopy(style))
    st['name'] = name; st['_dir'] = d
    return st


def for_plan(plan):
    """El estilo de un plan ya cargado (edit.json: "preset" y "style"; plan.py: PRESET y STYLE)."""
    edit = getattr(plan, 'EDIT', None) or {}
    return load(edit.get('preset') or getattr(plan, 'PRESET', None), edit.get('style') or getattr(plan, 'STYLE', None))


def for_globals(g):
    """Lo mismo para los scripts que tienen el plan como globales (render.py, audio.py)."""
    edit = g.get('EDIT') or {}
    return load(edit.get('preset') or g.get('PRESET'), edit.get('style') or g.get('STYLE'))


def logo_path(st, project=None):
    """logo.png del proyecto > logo del preset > logo genérico del motor."""
    if project and os.path.exists(os.path.join(project, 'logo.png')):
        return os.path.join(project, 'logo.png')
    lg = st['channel'].get('logo')
    if lg:
        p = lg if os.path.isabs(lg) else os.path.join(st['_dir'], lg)
        if os.path.exists(p): return p
    return os.path.join(ENGINE, 'assets', 'logo.png')


def bgr(c):
    """'#RRGGBB' o [r, g, b] -> (b, g, r), como trabaja el render."""
    if isinstance(c, str):
        c = c.lstrip('#')
        if len(c) != 6: raise PresetError(f'color "{c}": se espera #RRGGBB')
        c = [int(c[i:i + 2], 16) for i in (0, 2, 4)]
    return (c[2], c[1], c[0])


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    a = sys.argv[1:]
    try:
        if not a:
            cur = config().get('preset') or 'default'
            for n in names():
                d = _read(find(n)[0]) if n != 'default' else default()
                print(f'{"*" if n == cur else " "} {n:18} {d.get("description", "")}')
            print('\n* = preset del canal (config.json)')
        elif a[0] == '--project':
            sys.path.insert(0, ENGINE)
            from project import load_plan
            st = for_plan(load_plan(os.path.abspath(a[1]), quiet=True))
            print(json.dumps({k: v for k, v in st.items() if k != '_dir'}, indent=1, ensure_ascii=False))
        else:
            st = load(a[0])
            print(json.dumps({k: v for k, v in st.items() if k != '_dir'}, indent=1, ensure_ascii=False))
    except PresetError as e:
        raise SystemExit(f'Preset: {e}')
