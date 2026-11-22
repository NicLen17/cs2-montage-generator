"""Un solo lugar para cargar el plan de un proyecto.

    projects/<nombre>/edit.json   -> datos del edit; el timeline lo calcula engine/planner.py   (proyectos nuevos)
    projects/<nombre>/plan.py     -> plan escrito como código Python                           (proyectos anteriores)

Si están los dos, manda edit.json. Los dos caminos devuelven un objeto con los mismos nombres (segments, kills,
captions, boundaries, TOTAL, ACT1, ACT2, ...), así el resto del motor no sabe de dónde salió.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import compat  # noqa: F401  (nombres viejos de las variables de entorno)
import contextlib, importlib.util, io, json, os, sys

ENGINE = os.path.dirname(os.path.abspath(__file__))
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)


def edit_path(project): return os.path.join(project, 'edit.json')
def plan_path(project): return os.path.join(project, 'plan.py')


def has_plan(project):
    return os.path.exists(edit_path(project)) or os.path.exists(plan_path(project))


def load_edit(project):
    with open(edit_path(project), encoding='utf-8') as fh:
        return json.load(fh)


def dumps_edit(edit):
    """edit.json legible y fácil de comparar entre versiones: una clave por línea y una play por línea."""
    out = []
    for k, v in edit.items():
        if k in ('act1', 'act2') and v:
            body = ',\n'.join('  ' + json.dumps(p, ensure_ascii=False) for p in v)
            out.append(f' {json.dumps(k)}: [\n{body}\n ]')
        else:
            out.append(f' {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}')
    return '{\n' + ',\n'.join(out) + '\n}\n'


def save_edit(project, edit):
    tmp = edit_path(project) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(dumps_edit(edit))
    os.replace(tmp, edit_path(project))


def load_plan(project, source=None, quiet=False):
    """source: None (edit.json si existe, si no plan.py), 'edit' o 'py'. quiet: no imprimir lo que imprima un plan.py."""
    project = os.path.abspath(project)
    if source != 'py' and os.path.exists(edit_path(project)):
        import planner
        return planner.build(load_edit(project), project)
    if source == 'edit' or not os.path.exists(plan_path(project)):
        raise SystemExit(f'{project}: no hay edit.json ni plan.py. Para armar uno: python engine/auto.py {project}')
    spec = importlib.util.spec_from_file_location('plan', plan_path(project))
    cwd = os.getcwd(); os.chdir(project); sys.path.insert(0, project)
    try:
        m = importlib.util.module_from_spec(spec)
        with (contextlib.redirect_stdout(io.StringIO()) if quiet else contextlib.nullcontext()):
            spec.loader.exec_module(m)
    finally:
        os.chdir(cwd)
        if project in sys.path: sys.path.remove(project)
    return m


def plan_globals(project):
    """Los nombres públicos del plan, para los scripts que trabajan con ellos como globales (render.py, audio.py)."""
    m = load_plan(project)
    return {k: v for k, v in vars(m).items() if not k.startswith('_')}
