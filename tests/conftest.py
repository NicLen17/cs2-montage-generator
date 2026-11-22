import os, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'engine'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def pytest_addoption(parser):
    parser.addoption('--slow', action='store_true', help='correr también las pruebas lentas (render y detector de kills)')


def pytest_collection_modifyitems(config, items):
    if config.getoption('--slow'):
        return
    skip = pytest.mark.skip(reason='lenta: correr con --slow')
    for it in items:
        if 'slow' in it.keywords:
            it.add_marker(skip)
