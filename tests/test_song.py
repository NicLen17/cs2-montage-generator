import json, os
import numpy as np
import pytest

SR = 44100


def _kick(t):
    return np.sin(2 * np.pi * (50 + 90 * np.exp(-t * 30)) * t) * np.exp(-t * 14)


def _synth(path, parts):
    """parts: [(bpm, segundos)]. Bombo en cada beat, hi-hat en el contratiempo. Devuelve los tiempos reales de beat."""
    import soundfile as sf
    total = sum(d for _, d in parts); y = np.zeros(int(total * SR) + SR); beats = []; t0 = 0.5
    rng = np.random.default_rng(1); k = _kick(np.arange(int(0.25 * SR)) / SR)
    hat = rng.normal(0, 1, int(0.03 * SR)) * np.exp(-np.arange(int(0.03 * SR)) / SR * 150) * 0.25
    for bpm, d in parts:
        step = 60 / bpm; end = t0 + d
        while t0 < end:
            i = int(t0 * SR); y[i:i + len(k)] += k; j = int((t0 + step / 2) * SR); y[j:j + len(hat)] += hat
            beats.append(t0); t0 += step
    sf.write(path, (y / abs(y).max() * 0.8).astype(np.float32), SR)
    return np.array(beats)


def _err(grid, truth, skip=()):
    """Distancia de cada beat real al beat de la grilla más cercano (sin los beats pegados a un cambio de tempo)."""
    keep = [t for t in truth if 6 < t < truth[-1] - 6 and not any(abs(t - s) < 6 for s in skip)]
    return np.array([abs(grid - t).min() for t in keep])


@pytest.mark.slow
def test_tempo_fijo_una_sola_recta(tmp_path):
    import analyze_song
    truth = _synth(str(tmp_path / 'song.wav'), [(128, 70)])
    info = analyze_song.analyze(str(tmp_path), verbose=False)
    grid = np.load(tmp_path / 'grid.npy')
    assert info['tempo_fixed'] and abs(info['bpm'] - 128) < 0.3
    assert np.percentile(_err(grid, truth), 95) < 0.03


@pytest.mark.slow
def test_tempo_variable_la_grilla_sigue_los_golpes(tmp_path):
    import analyze_song
    truth = _synth(str(tmp_path / 'song.wav'), [(110, 50), (140, 50)])
    change = 0.5 + 50
    info = analyze_song.analyze(str(tmp_path), verbose=False)
    grid = np.load(tmp_path / 'grid.npy')
    assert not info['tempo_fixed'], info['tempo']
    bpms = sorted(round(s['bpm']) for s in info['tempo'])
    assert abs(bpms[0] - 110) <= 1 and abs(bpms[-1] - 140) <= 1, info['tempo']
    assert np.percentile(_err(grid, truth, skip=[change]), 90) < 0.03
    assert (np.diff(grid) > 0.2).all()
    for f in ('song.json', 'sync.json', 'vocal_hits.json'):
        json.load(open(tmp_path / f, encoding='utf-8'))


def test_pick_sync_va_al_beat_que_suena_con_todo():
    import analyze_song
    grid = np.arange(40) * 0.5
    lv = np.full(39, -30.0); bs = np.full(39, -40.0)
    lv[19] = -22; bs[19] = -28          # asoma el bajo un beat antes
    lv[20:] = -12; bs[20:] = -14        # el drop
    out = analyze_song.pick_sync([dict(t=9.5, fuerza=12.0, tipo='sube')], [0.0], grid, lv, bs)
    assert out == [10.0]
    assert analyze_song.pick_sync([dict(t=9.5, fuerza=3.0, tipo='voz')], [0.0], grid, lv, bs) == []


def test_golpes_de_voz():
    import words
    W = [dict(t0=1.0, t1=1.4, w='hey'), dict(t0=1.5, t1=1.9, w='you'),
         dict(t0=4.0, t1=4.3, w='Stop'),                                            # aislada: 2.1 s de silencio antes
         dict(t0=6.0, t1=6.2, w='go'), dict(t0=6.4, t1=6.6, w='Go,'), dict(t0=6.8, t1=7.0, w='go')]
    acc = words.accents(W)
    assert any(a['w'] == 'Stop' and a['why'] == 'palabra aislada' for a in acc)
    rep = [a for a in acc if a['why'].startswith('repetida')]
    assert rep and rep[0]['times'] == [6.0, 6.4, 6.8]


def test_sync_automatico_y_energia_en_el_plan(tmp_path):
    """Sin song.sync en edit.json, el planificador toma los momentos de song.json; con song.sync, manda el edit."""
    import shutil, migrate, planner
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, 'projects', 'my_jealousy_v3')
    if not os.path.exists(os.path.join(src, 'plan.py')):
        pytest.skip('sin el proyecto de ejemplo')
    for f in ('grid.npy', 'hits.npy', 'shots.json'):
        shutil.copy(os.path.join(src, f), tmp_path / f)
    edit = migrate.migrate(src)[0]
    grid = np.load(tmp_path / 'grid.npy')
    t_sync = float(grid[40]); n = len(grid) - 1
    json.dump(dict(sync=[t_sync, 1.0, 9999.0], energy_beats=[0.2] * 60 + [0.9] * (n - 60)), open(tmp_path / 'song.json', 'w'))
    edit['song'].pop('sync', None)
    p = planner.build(edit, str(tmp_path))
    assert p.SYNC == [t_sync] and p.SYNC_AUTO                    # fuera del video: no cuentan
    assert len(p.KILL_ENERGY) == len(p.kills) and min(p.KILL_ENERGY) == 0.2 and max(p.KILL_ENERGY) == 0.9
    edit['song']['sync_skip'] = [t_sync]
    assert planner.build(edit, str(tmp_path)).SYNC == []
    edit['song']['sync'] = [50.0]
    p = planner.build(edit, str(tmp_path))
    assert p.SYNC == [50.0] and not p.SYNC_AUTO
