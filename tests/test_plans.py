import contextlib, io, json, os
import pytest
import plan_snapshot as PS

NAMES = [f[:-5] for f in sorted(os.listdir(PS.REF))] if os.path.isdir(PS.REF) else []


@pytest.mark.parametrize('name', NAMES)
def test_plan_sin_cambios(name):
    project = os.path.join(PS.ROOT, 'projects', name)
    if not os.path.isdir(project):
        pytest.skip('el proyecto no está en esta máquina')
    ref = json.load(open(os.path.join(PS.REF, name + '.json'), encoding='utf-8'))
    with contextlib.redirect_stdout(io.StringIO()):
        cur = json.loads(json.dumps(PS.snapshot(project)))
    assert set(cur) >= set(ref), f'faltan datos del plan: {sorted(set(ref) - set(cur))}'
    for k in ref:
        assert cur[k] == ref[k], f'{name}: cambió {k}'
