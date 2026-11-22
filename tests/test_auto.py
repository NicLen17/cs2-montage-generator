import os
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'projects', 'paparazzi_v2')


@pytest.mark.skipif(not (os.path.isdir(os.path.join(P, 'clips')) and os.path.exists(os.path.join(P, 'song.json'))),
                    reason='sin los clips y el análisis del proyecto de prueba en esta máquina')
def test_arma_un_edit_que_entra_en_la_cancion():
    import json, auto, planner
    edit, s = auto.make_edit(P)                      # no escribe nada en el proyecto
    ns = planner.build(edit, P)
    info = json.load(open(os.path.join(P, 'song.json'), encoding='utf-8'))
    assert ns.TOTAL + ns.SONG_A0 <= info['duration']           # el video no pasa el final de la canción
    assert 0 <= s['resid'] <= 2.5                               # el acto 1 termina justo antes de la revelación
    assert s['used'] >= 8 and s['kills'] >= 20
    clips = [p['clip'] for p in edit['act1'] + edit['act2']]
    assert len(clips) == len(set(clips))                        # ninguna play repetida
    assert edit['act2'][0]['clip'] == s['best'] and edit['close']['clip'] == edit['act2'][-1]['clip']
    # la primera kill de la apertura cae en el primer drop y la de la mejor play en el drop principal
    o1 = ns.so(ns.TGT[ns.IDX_DROP]); o2 = ns.O_DROP2
    assert min(abs(k - o1) for k in ns.kills) < 0.02 and min(abs(k - o2) for k in ns.kills) < 0.02
