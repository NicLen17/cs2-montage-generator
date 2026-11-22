import os, re, subprocess, sys
import pytest
import eval_kills as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Línea base del 21/11/2026 (141 clips verificados, 419 kills, ±0.35 s): F1 89.2 % todos, 90.8 % solo seguros.
F1_MIN, F1_SURE_MIN = 0.887, 0.903


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
