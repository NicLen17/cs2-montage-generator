import os, subprocess, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFS = os.path.join(ROOT, 'tests', 'ref')
NAMES = [d for d in (sorted(os.listdir(REFS)) if os.path.isdir(REFS) else [])
         if os.path.exists(os.path.join(REFS, d, 'times.json'))]


@pytest.mark.slow
@pytest.mark.parametrize('device', ['cpu', 'gpu'])
@pytest.mark.parametrize('name', NAMES)
def test_imagen_sin_cambios(name, device):
    project = os.path.join(ROOT, 'projects', name)
    if not os.path.isdir(os.path.join(project, 'clips')):
        pytest.skip('sin los clips del proyecto en esta máquina')
    if device == 'gpu':
        try:
            import gpu; gpu.init(64, 64)
        except Exception:
            pytest.skip('sin GPU con OpenGL 4.3')
    # CPU contra la referencia (hecha en CPU): tiene que dar casi idéntico. GPU: el margen de siempre (45 dB).
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'engine', 'regress.py'), project, '--device', device,
                        '--min-psnr', '60' if device == 'cpu' else '45'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
