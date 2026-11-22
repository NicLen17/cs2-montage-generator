import json, os, sys, threading, urllib.error, urllib.request
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'engine', 'ui'))


@pytest.fixture(scope='module')
def base():
    import server
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{srv.server_address[1]}'
    srv.shutdown()


def call(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def test_pagina_y_listados(base):
    with urllib.request.urlopen(base + '/') as r:
        assert b'Editor de montajes' in r.read()
    code, ps = call(base, 'GET', '/api/projects'); assert code == 200 and isinstance(ps, list)
    code, pr = call(base, 'GET', '/api/presets'); assert code == 200 and 'default' in pr['names'] and 'look' in pr['default']


def test_no_se_sale_de_la_carpeta_del_proyecto(base):
    assert call(base, 'GET', '/api/projects/..%2F..%2Fengine')[0] == 400
    assert call(base, 'GET', '/media/my_jealousy_v3/..%2F..%2FCLAUDE.md')[0] in (400, 404)
    assert call(base, 'POST', '/api/projects', {'name': '../fuera'})[0] == 400


def test_un_edit_roto_no_se_guarda(base):
    p = os.path.join(ROOT, 'projects', 'my_jealousy_v3')
    if not os.path.exists(os.path.join(p, 'edit.json')): pytest.skip('sin el proyecto de ejemplo')
    before = open(os.path.join(p, 'edit.json'), encoding='utf-8').read()
    code, d = call(base, 'GET', '/api/projects/my_jealousy_v3')
    assert code == 200 and d['kind'] == 'edit' and d['timeline']['TOTAL'] > 60
    bad = d['edit']; bad['act1'][0]['segs'][0]['kill'] = 99
    code, r = call(base, 'PUT', '/api/projects/my_jealousy_v3/edit', bad)
    assert code == 400 and 'kill 99' in r['error']
    assert open(os.path.join(p, 'edit.json'), encoding='utf-8').read() == before


def test_preset_con_clave_mal_escrita(base):
    code, r = call(base, 'PUT', '/api/presets/prueba_ui', {'look': {'saturacion': 2}})
    assert code == 400 and 'saturacion' in r['error']
    assert not os.path.exists(os.path.join(ROOT, 'presets', 'prueba_ui'))
