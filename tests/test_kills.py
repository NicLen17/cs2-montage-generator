import os, re, subprocess, sys
import pytest
import eval_kills as E
import killfeed as K
import score as SC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Línea base del 21/11/2026 (141 clips verificados, 419 kills, ±0.35 s), después de la Fase 3 (audio como segunda
# señal), sin nick en el preset: F1 91.3 % todos, 91.0 % solo seguros, 48 dudosos. Con "channel.player" en el preset:
# 91.0 % / 92.2 % y 35 dudosos. Antes de la Fase 3: 89.2 % / 90.8 % y 62 dudosos.
F1_MIN, F1_SURE_MIN = 0.905, 0.905


def test_match_uno_a_uno():
    hit, extra, miss = E.match([1.0, 1.1, 5.0], [1.05, 9.0])
    assert len(hit) == 1 and extra == [1.1, 5.0]
    assert miss == [9.0]


def test_match_respeta_tolerancia():
    hit, extra, miss = E.match([2.0], [2.5], tol=0.35)
    assert not hit and extra == [2.0] and miss == [2.5]


@pytest.mark.slow
def test_detector_no_empeora():
    if not os.path.exists(os.path.join(ROOT, 'catalog', 'clips.json')):
        pytest.skip('sin catálogo verificado en esta máquina')
    out = subprocess.run([sys.executable, os.path.join(ROOT, 'engine', 'eval_kills.py')], capture_output=True, text=True,
                         encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}).stdout
    block = out.split('--- tolerancia ±0.7')[0]
    f1 = [float(x) / 100 for x in re.findall(r'F1\s+([\d.]+)%', block)]
    assert len(f1) >= 2, out[-800:]
    assert f1[0] >= F1_MIN, f'F1 del detector bajó a {f1[0]:.1%}'
    assert f1[1] >= F1_SURE_MIN, f'F1 de las kills seguras bajó a {f1[1]:.1%}'


def test_layout_16_9_es_el_recorte_de_siempre():
    L = K.layout(1920, 1080)
    assert (L['x'], L['y'], L['w'], L['h']) == K.CROP
    for W, H in ((1280, 720), (2560, 1440), (3840, 2160)):          # otras resoluciones 16:9: como antes de la Fase 3
        L = K.layout(W, H)
        assert [L['x'], L['y'], L['w'], L['h']] == [int(round(v * s)) for v, s in zip(K.CROP, (W / 1920, H / 1080) * 2)]


def test_layout_otros_formatos():
    L = K.layout(1680, 1050)                                        # 16:10: pegado a la derecha, a escala del alto
    assert L['x'] + L['w'] == 1680 and abs(L['w'] - 670 * 1050 / 1080) <= 1
    L = K.layout(1920, 1080, aspect='4:3s')                         # 4:3 estirado: el recorte se ensancha 4/3
    assert L['x'] + L['w'] == 1920 and abs(L['w'] - 670 * 4 / 3) <= 1 and L['h'] == 394
    L = K.layout(1920, 1080, bars=240)                              # 4:3 con barras: se mide desde donde termina el juego
    assert L['x'] + L['w'] == 1920 - 240 and L['w'] == 670
    L = K.layout(1920, 1080, hud=1.2)
    assert L['x'] + L['w'] == 1920 and abs(L['w'] - 670 * 1.2) <= 1 and abs(L['h'] - 394 * 1.2) <= 1


def test_unique_usa_los_fps_del_clip():
    import numpy as np
    sig = (np.random.RandomState(0).rand(23, 200) * 255).astype('uint8')
    trs = [dict(start=0, sig=sig), dict(start=30 * 25, sig=sig)]    # la misma entrada 25 s después, a 30 fps
    assert len(K._unique(trs, fps=30)) == 2                         # más de 20 s: son dos
    assert len(K._unique(trs, fps=60)) == 1                         # a 60 fps serían 12.5 s: la misma


def test_disparo_en_el_audio():
    import numpy as np
    env = np.full(10 * K.ENV_SR, 0.01, np.float32); env[4900:4960] = 1.0
    assert K.shot_rise(env, 5.0) > K.NO_SHOT > K.shot_rise(env, 8.0)
    assert K.shot_rise(None, 5.0) is None


def test_puntaje_de_plays():
    ace = SC.score(dict(kills=[10, 11, 12.5, 13, 14.2]))
    doble = SC.score(dict(kills=[10, 11]))
    lento = SC.score(dict(kills=[10, 16, 22, 28, 34]))
    assert ace['score'] > lento['score'] > doble['score'] and lento['muerto'] > 0
    assert SC.score(dict(kills=[10, 11], kill_types=[['headshot'], ['headshot', 'pared']]))['score'] > doble['score']
    assert SC.score(dict(kills=[10, 11], reaction=dict(group=True)))['score'] > doble['score']
    assert SC.score(dict(kills=[1, 2, 60, 61, 62]))['n'] == 3       # dos rondas en un clip: cuenta la racha más larga
    assert SC.score(dict(kills=None))['score'] == 0
