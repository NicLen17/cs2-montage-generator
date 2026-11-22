import json, os
import pytest
import preset


def test_default_tiene_todos_los_grupos():
    st = preset.load('default')
    for k in ('channel', 'colors', 'look', 'captions', 'camera', 'transitions', 'kill_fx', 'cuts', 'audio', 'output'):
        assert k in st
    assert set(st['transitions']['rotation']) <= set(st['transitions']['durations']) | {'mega'}


def test_style_pisa_solo_lo_que_nombra():
    base = preset.load('default')
    st = preset.load('default', {'look': {'saturation': 1.4}, 'channel': {'name': 'X'}})
    assert st['look']['saturation'] == 1.4 and st['look']['bloom'] == base['look']['bloom']
    assert st['channel']['name'] == 'X' and st['channel']['tagline'] == base['channel']['tagline']
    assert preset.load('default')['look']['saturation'] == base['look']['saturation']      # no ensucia el default


@pytest.mark.parametrize('style,msg', [
    ({'look': {'saturacion': 2}}, 'look.saturacion'),
    ({'colores': {}}, 'colores'),
    ({'transitions': {'durations': {'wipe': 1}}}, 'wipe'),
])
def test_clave_mal_escrita_avisa(style, msg):
    with pytest.raises(preset.PresetError) as ei:
        preset.load('default', style)
    assert msg in str(ei.value)


def test_preset_inexistente():
    with pytest.raises(preset.PresetError):
        preset.load('no_existe_este_preset')


def test_color():
    assert preset.bgr('#9146FF') == (255, 70, 145)
    assert preset.bgr([1, 2, 3]) == (3, 2, 1)


def test_logo_cae_al_generico():
    st = preset.load('default')
    assert os.path.exists(preset.logo_path(st))


def test_presets_del_repo_cargan():
    for n in preset.names():
        st = preset.load(n)
        json.dumps({k: v for k, v in st.items() if k != '_dir'})
