import copy, os
import pytest
import migrate, planner, project

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PJ = os.path.join(ROOT, 'projects')
# Planes anteriores con lógica propia (se quedan con su plan.py): el planificador no tiene que reproducirlos.
OWN_LOGIC = {'bloody_tears', 'ejemplo_i_dont_like', 'my_jealousy_v2'}
NAMES = [p for p in sorted(os.listdir(PJ)) if os.path.exists(os.path.join(PJ, p, 'plan.py')) and p not in OWN_LOGIC
         and os.path.exists(os.path.join(PJ, p, 'shots.json'))]


@pytest.mark.parametrize('name', NAMES)
def test_edit_json_reproduce_plan_py(name):
    """Los datos de un plan.py, pasados a edit.json, dan exactamente el mismo timeline."""
    edit, bad = migrate.migrate(os.path.join(PJ, name))
    assert not bad, f'{name}: cambia {bad}'
    assert project.dumps_edit(edit)            # se puede guardar


def _edit():
    p = os.path.join(PJ, 'my_jealousy_v3')
    if not os.path.exists(os.path.join(p, 'plan.py')):
        pytest.skip('sin el proyecto de ejemplo')
    return p, migrate.migrate(p)[0]


def test_ida_y_vuelta_por_json():
    import json
    p, edit = _edit()
    again = json.loads(project.dumps_edit(edit))
    assert again == json.loads(json.dumps(edit))
    a, b = planner.build(edit, p), planner.build(again, p)
    assert migrate.diff(a, b) == []


def test_timeline_es_json():
    import json
    p, edit = _edit()
    t = json.loads(json.dumps(planner.timeline(planner.build(edit, p))))
    assert t['TOTAL'] > 60 and len(t['segments']) > 10 and t['beats']
    assert all(a[0] <= b[0] for a, b in zip(t['boundaries'], t['boundaries'][1:]))


@pytest.mark.parametrize('breaker,msg', [
    (lambda e: e['song'].pop('drop2'), 'drop2'),
    (lambda e: e['act1'][0].pop('segs'), 'segs'),
    (lambda e: e['act1'][0]['segs'][0].pop('end'), 'end'),
    (lambda e: e['act1'][0]['segs'][0].__setitem__('kill', 99), 'kill 99'),
    (lambda e: e.__setitem__('act2', []), 'act2'),
    (lambda e: e.__setitem__('audio', {'VOLUMEN': 3}), 'VOLUMEN'),
])
def test_errores_claros(breaker, msg):
    p, edit = _edit()
    edit = copy.deepcopy(edit); breaker(edit)
    with pytest.raises(planner.EditError) as ei:
        planner.build(edit, p)
    assert msg in str(ei.value)
