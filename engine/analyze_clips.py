"""Analiza los clips de un proyecto (projects/<nombre>/clips/c1.mp4, c2.mp4, ...).

    python engine/analyze_clips.py projects/<nombre>            -> todo
    python engine/analyze_clips.py projects/<nombre> --shots    -> solo recalcula disparos desde kf.json

Hace (en paralelo, un proceso por clip):
  1. Lee el killfeed cuadro por cuadro (engine/killfeed.py): cada entrada con borde rojo se sigue en el tiempo y se
     decide si es kill (el jugador a la izquierda), muerte (a la derecha) o asistencia (en el medio). El jugador se
     deduce de cada play: es el nombre que se repite en sus entradas rojas (no hay nicks fijos).
     cnt<N>.npy: cantidad de entradas con borde rojo por cuadro.
  2. kf_auto.json: {clip: [tiempos]} de las kills encontradas (seguras y dudosas). kf_conf.json: lo mismo con el
     puntaje de confianza (0-1) y el motivo, más las muertes y asistencias descartadas.
  3. sheets/kf_dudosos.jpg: SOLO lo que hay que mirar a ojo (kills dudosas y clips sin killfeed legible).
     sheets/kf_resumen.txt: resumen por clip. sheets/kf_*.jpg: todas las kills (verde = segura, rojo = dudosa).
     sheets/ctx_*.jpg: hojas de contexto (miniaturas a 1 fps).
  4. shots.json: el instante exacto del disparo de cada kill, a partir del audio del clip.
Revisá a ojo solo lo dudoso y corregí kf.json (lista final de kills por clip) antes de planificar."""
import os, sys, json, subprocess, unicodedata
from concurrent.futures import ProcessPoolExecutor
import numpy as np, cv2
from scipy.signal import butter, sosfiltfilt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import killfeed as K

clips = []   # se llena en __main__ (en Windows los procesos hijos heredan la carpeta del proyecto como cwd)


def kf_scan(c):
    """Etapa lenta del killfeed (un proceso por clip): las cajas rojas de cada cuadro."""
    fr = K.scan(f'clips/c{c}.mp4')
    np.save(f'cnt{c}.npy', np.array([len(K._clean(b)) for b in fr['boxes']]))
    return c, fr


def shots_for(args):
    c, ks = args
    SR = 48000; sos = butter(4, [1500, 9000], 'band', fs=SR, output='sos')
    a = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', f'clips/c{c}.mp4', '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                                     capture_output=True).stdout, np.float32).astype(float)
    if len(a) < SR:
        return c, [round(k - 0.12, 3) for k in ks]
    hh = sosfiltfilt(sos, a); env = np.sqrt(np.convolve(hh ** 2, np.ones(96) / 96, 'same')); res = []
    for k in ks:
        i0 = max(0, int((k - 0.45) * SR)); seg = env[i0:int((k + 0.06) * SR)]
        d = seg[480:] - seg[:-480]; j = int(np.argmax(d)) + 480; pk = seg[j]
        fl = np.percentile(seg[max(0, j - 4800):j], 20); b = j
        while b > 0 and seg[b] > fl + 0.3 * (pk - fl): b -= 1
        s = round((i0 + b) / SR, 3)
        if k - s > 0.46 or k - s < 0.05 or (res and abs(s - res[-1]) < 0.02): s = round(k - 0.12, 3)   # sospechoso -> revisar a mano
        res.append(s)
    return c, res


def _kf_tile(cap, n, t, label, color, note=None):
    cap.set(1, max(0, min(int((t + 0.5) * 60), n - 3))); ok, f = cap.read()
    if not ok: return None
    k = cv2.resize(f[25:265, 1300:1920], (465, 180))
    cv2.rectangle(k, (0, 0), (464, 179), color, 3)
    for txt, y, col in ((label, 172, color), (note, 20, (0, 255, 255))):
        if txt:
            txt = unicodedata.normalize('NFKD', txt).encode('ascii', 'ignore').decode()   # cv2 no dibuja tildes
            cv2.putText(k, txt[:46], (6, y), 0, 0.5, (0, 0, 0), 4); cv2.putText(k, txt[:46], (6, y), 0, 0.5, col, 1)
    return k


def _grid(rows, cols, name, per=10):
    if not rows: return
    while len(rows) % cols: rows.append(np.zeros_like(rows[0]))
    R = [np.hstack(rows[i:i + cols]) for i in range(0, len(rows), cols)]
    for j in range(0, len(R), per):
        cv2.imwrite(f'sheets/{name}_{j // per}.jpg' if len(R) > per else f'sheets/{name}.jpg', np.vstack(R[j:j + per]))


def sheets(conf):
    """conf = kf_conf.json. Todas las kills (verde segura / rojo dudosa) y una hoja aparte solo con lo dudoso."""
    os.makedirs('sheets', exist_ok=True)
    for f in os.listdir('sheets'):
        if f.startswith('kf') and f.endswith('.jpg'): os.remove(os.path.join('sheets', f))
    rows, doubt = [], []
    for c in clips:
        info = conf.get(str(c))
        if not info: continue
        cap = cv2.VideoCapture(f'clips/c{c}.mp4'); n = int(cap.get(7))
        for e in info['kills']:
            sure = e['conf'] >= K.DOUBT
            label = f'c{c} {e["t"]:.2f}  ' + (f'{e["conf"]:.2f}' if sure else f'DUDOSA {e["conf"]:.2f}')
            k = _kf_tile(cap, n, e['t'], label, (0, 200, 0) if sure else (0, 0, 255))
            if k is None: continue
            rows.append(k)
            if not sure: doubt.append(_kf_tile(cap, n, e['t'], label, (0, 0, 255), e['why']))
        if info.get('sin_killfeed'):                # cámara encima o HUD tapado: hay que mirar todo el clip
            for t in (n / 60 * 0.3, n / 60 * 0.6):
                k = _kf_tile(cap, n, t, f'c{c} SIN KILLFEED LEGIBLE', (0, 165, 255), 'revisar el clip entero a mano')
                if k is not None: doubt.append(k)
    _grid(rows, 5, 'kf')
    _grid([d for d in doubt if d is not None], 4, 'kf_dudosos')


def sheets_ctx():
    th = []
    for c in clips:
        cap = cv2.VideoCapture(f'clips/c{c}.mp4'); n = int(cap.get(7)); t = 0.0
        while t * 60 < n - 30:
            cap.set(1, int(t * 60)); ok, f = cap.read()
            if not ok: break
            f = cv2.resize(f, (192, 108), interpolation=cv2.INTER_AREA); cv2.putText(f, f'{c} {int(t)}', (3, 15), 0, 0.45, (0, 255, 255), 1); th.append(f); t += 1.0
        while len(th) % 10: th.append(np.zeros_like(th[0]))
    R = [np.hstack(th[i:i + 10]) for i in range(0, len(th), 10)]
    for j in range(0, len(R), 14): cv2.imwrite(f'sheets/ctx_{j // 14}.jpg', np.vstack(R[j:j + 14]))


def killfeed(scan):
    """Lee el killfeed de los clips a revisar y escribe kf_auto.json, kf_conf.json y sheets/kf_resumen.txt."""
    with ProcessPoolExecutor() as ex:
        frs = dict(ex.map(kf_scan, scan))
    names = K.player_names(list(frs.values()))      # el jugador, deducido de las plays donde su nombre se repite
    conf, kf_auto, resumen = {}, {}, []
    for c in scan:
        fr = frs[c]; ev = K.detect(fr, names=names)
        nobox = not ev and not fr['otros']          # ni una entrada roja nueva: killfeed tapado o fuera de lugar
        conf[str(c)] = dict(kills=ev, otros=fr['otros'], jugador=fr['jugador']['src'], sin_killfeed=nobox)
        kf_auto[str(c)] = [e['t'] for e in ev]
        sure = [e['t'] for e in ev if e['conf'] >= K.DOUBT]; dud = [e['t'] for e in ev if e['conf'] < K.DOUBT]
        line = f'c{c}: {len(sure)} kill(s) segura(s) {sure}'
        if dud: line += f'  · {len(dud)} DUDOSA(S) {dud}'
        for o in fr['otros']: line += f'  · {o["kind"]} {o["t"]}'
        if nobox: line += '  · SIN KILLFEED LEGIBLE (¿cámara encima?): revisar el clip entero a mano'
        elif fr['jugador']['src'] is None and ev: line += '  · no se pudo deducir el nombre del jugador'
        resumen.append(line)
    json.dump(kf_auto, open('kf_auto.json', 'w'), indent=1)
    json.dump(conf, open('kf_conf.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    nk = sum(len(v['kills']) for v in conf.values()); nd = sum(e['conf'] < K.DOUBT for v in conf.values() for e in v['kills'])
    nb = [c for c, v in conf.items() if v['sin_killfeed']]
    resumen.append(f'\nTotal: {nk} kills, {nk - nd} seguras, {nd} dudosas para mirar a ojo'
                   + (f'; clips sin killfeed legible (revisar enteros): {", ".join("c" + c for c in nb)}' if nb else ''))
    os.makedirs('sheets', exist_ok=True)
    open('sheets/kf_resumen.txt', 'w', encoding='utf-8').write('\n'.join(resumen) + '\n')
    print('\n'.join(resumen))
    return kf_auto, conf


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    os.chdir(os.path.abspath(sys.argv[1]))
    clips = sorted([int(f[1:-4]) for f in os.listdir('clips') if f.startswith('c') and f.endswith('.mp4')])
    # clips verificados que trajo el catálogo (engine/catalog.py prefill): no se escanean ni se recalculan sus disparos
    verified = set(json.load(open('verified.json'))) if os.path.exists('verified.json') else set()
    if verified: print(f'Verificados del catálogo (se saltean): {sorted(verified)}')
    if '--shots' not in sys.argv:
        scan = [c for c in clips if c not in verified]
        kf_auto, conf = killfeed(scan)
        kf = json.load(open('kf.json')) if os.path.exists('kf.json') else {}
        for c, ev in kf_auto.items():
            kf.setdefault(c, ev)          # nunca pisa una lista ya corregida o traída del catálogo
        json.dump(kf, open('kf.json', 'w'), indent=1)
        clips = scan                      # las hojas de killfeed y contexto, solo de los clips a revisar
        sheets(conf); sheets_ctx()
        print('Hojas en sheets/: mirá kf_dudosos.jpg (solo lo dudoso). Corregí kf.json y corré con --shots.')
    kf = json.load(open('kf.json'))
    old = json.load(open('shots.json')) if os.path.exists('shots.json') else {}
    todo = [(int(c), v) for c, v in kf.items() if not (int(c) in verified and c in old)]
    with ProcessPoolExecutor() as ex:
        sh = dict(ex.map(shots_for, todo))
    out = {c: v for c, v in old.items() if int(c) in verified and c in kf}
    out.update({str(c): v for c, v in sh.items()})
    json.dump(out, open('shots.json', 'w'), indent=1)
    print('shots.json listo' + (f' ({len(verified)} clips con disparos del catálogo)' if verified else ''))
