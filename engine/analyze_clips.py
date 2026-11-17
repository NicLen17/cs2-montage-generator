"""Analiza los clips de un proyecto (projects/<nombre>/clips/c1.mp4, c2.mp4, ...).

    python engine/analyze_clips.py projects/<nombre>            -> todo
    python engine/analyze_clips.py projects/<nombre> --shots    -> solo recalcula disparos desde kf.json

Hace (en paralelo, un proceso por clip):
  1. cnt<N>.npy: cantidad de líneas rojas del killfeed por cuadro (entradas propias, borde rojo).
  2. kf_auto.json: momentos en que aparece una entrada propia nueva (candidatos a kill).
  3. sheets/ctx_*.jpg: hojas de contexto (miniaturas) y sheets/kf_*.jpg: recortes del killfeed en cada evento.
  4. shots.json: el instante exacto del disparo de cada kill, a partir del audio del clip.
REVISÁ las hojas a ojo y corregí kf.json (lista final de kills por clip) antes de planificar.
Contá las entradas propias al final de la ronda: si faltan kills en la lista, buscalas."""
import os, sys, json, subprocess
from concurrent.futures import ProcessPoolExecutor
import numpy as np, cv2
from scipy.ndimage import median_filter
from scipy.signal import butter, sosfiltfilt

clips = []   # se llena en __main__ (en Windows los procesos hijos heredan la carpeta del proyecto como cwd)


def kf_count(c):
    w, h = 670, 394
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', f'clips/c{c}.mp4', '-vf', 'crop=670:394:1250:24', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'],
                         stdout=subprocess.PIPE)
    cnt = []
    while True:
        b = p.stdout.read(w * h * 3)
        if len(b) < w * h * 3: break
        reg = np.frombuffer(b, np.uint8).reshape(h, w, 3).astype(np.int16)
        m = (reg[..., 2] > 170) & (reg[..., 2] - np.maximum(reg[..., 1], reg[..., 0]) > 60)   # borde rojo (a veces rosado al aparecer)
        # bordes horizontales (2 px) de cada entrada propia; una entrada mide ~30 px de alto (borde arriba + abajo)
        rows = np.where(m.sum(1) > 110)[0]; groups = []; last = -10
        for y in rows:
            if y - last > 1: groups.append([y, y])
            else: groups[-1][1] = y
            last = y
        ctr = [(a + b) / 2 for a, b in groups]; g = 0; i = 0
        while i < len(ctr) - 1:
            if 25 <= ctr[i + 1] - ctr[i] <= 35: g += 1; i += 2   # par borde superior / inferior = 1 entrada
            else: i += 1
        cnt.append(g)
    cnt = np.array(cnt); np.save(f'cnt{c}.npy', cnt)
    e = median_filter(cnt, 9).astype(int); ev = []
    for i in range(1, len(e) - 18):
        if e[i] >= e[i - 1] + 1 and e[i:i + 18].min() > e[i - 1]:
            if not ev or i / 60 - ev[-1] > 0.15: ev.append(round(i / 60, 3))
    return c, ev, int(median_filter(cnt, 31).max())


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


def sheets(kf):
    os.makedirs('sheets', exist_ok=True)
    rows = []
    for c in clips:
        cap = cv2.VideoCapture(f'clips/c{c}.mp4'); n = int(cap.get(7)); ims = []
        for t in kf.get(str(c), []):
            cap.set(1, min(int((t + 0.5) * 60), n - 3)); ok, f = cap.read()
            if not ok: continue
            k = cv2.resize(f[25:265, 1300:1920], (465, 180)); cv2.putText(k, f'c{c} {t}', (4, 175), 0, 0.6, (0, 255, 255), 2); rows.append(k)
    while rows and len(rows) % 5: rows.append(np.zeros_like(rows[0]))
    R = [np.hstack(rows[i:i + 5]) for i in range(0, len(rows), 5)]
    for j in range(0, len(R), 10): cv2.imwrite(f'sheets/kf_{j // 10}.jpg', np.vstack(R[j:j + 10]))
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
        with ProcessPoolExecutor() as ex:
            res = list(ex.map(kf_count, scan))
        kf_auto = {str(c): ev for c, ev, mx in res}
        json.dump(kf_auto, open('kf_auto.json', 'w'), indent=1)
        for c, ev, mx in res: print(f'c{c}: {len(ev)} eventos {ev}  (máx entradas propias visibles: {mx})')
        kf = json.load(open('kf.json')) if os.path.exists('kf.json') else {}
        for c, ev in kf_auto.items():
            kf.setdefault(c, ev)          # nunca pisa una lista ya corregida o traída del catálogo
        json.dump(kf, open('kf.json', 'w'), indent=1)
        clips = scan                      # las hojas de killfeed y contexto, solo de los clips a revisar
        sheets(kf_auto)
        print('Hojas en sheets/. Corregí kf.json (solo kills propias, sin duplicados) y corré con --shots.')
    kf = json.load(open('kf.json'))
    old = json.load(open('shots.json')) if os.path.exists('shots.json') else {}
    todo = [(int(c), v) for c, v in kf.items() if not (int(c) in verified and c in old)]
    with ProcessPoolExecutor() as ex:
        sh = dict(ex.map(shots_for, todo))
    out = {c: v for c, v in old.items() if int(c) in verified and c in kf}
    out.update({str(c): v for c, v in sh.items()})
    json.dump(out, open('shots.json', 'w'), indent=1)
    print('shots.json listo' + (f' ({len(verified)} clips con disparos del catálogo)' if verified else ''))
