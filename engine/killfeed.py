"""Lectura del killfeed de CS2 (arriba a la derecha) para encontrar las kills propias de un clip.

Uso desde código (lo llama engine/analyze_clips.py):
    fr = scan('clips/c3.mp4')          # etapa 1 (lenta, decodifica el video): entradas con borde rojo de cada cuadro
    ev = detect(fr, name=tpl)          # etapa 2 (rápida): una kill por entrada NUEVA en la que el jugador es el atacante

Cómo lee el killfeed:
  - Las entradas propias (las que involucran al jugador) tienen borde rojo. En cada cuadro se buscan los bordes
    horizontales rojos y se arman las cajas (arriba, abajo, izquierda, derecha). El killfeed está alineado a la derecha:
    el borde derecho es fijo y el ancho de cada entrada depende de los nombres y del arma.
  - Cada caja se sigue en el tiempo (dura ~5-6 s en pantalla; cuando vence la de arriba, las demás suben ~34 px).
    Una entrada que aparece y dura menos de MIN_LIFE se descarta (parpadeo). Una que ya estaba en el primer cuadro
    es de antes del clip.
  - Kill o muerte: dentro de la caja se busca el nombre del jugador (plantilla). Pegado al borde izquierdo = mató;
    pegado al derecho = murió; en el medio (después de un "+") = asistencia. La plantilla sale de las kills ya
    verificadas (engine/assets/kf_name.npz, se arma con engine/eval_kills.py --learn-name) o, si no coincide con
    nada del clip, del texto que más se repite a la izquierda de las entradas del propio clip.
  - Cada evento lleva un puntaje de confianza (0-1). Los dudosos (< DOUBT) son los únicos que hay que mirar a ojo.
"""
import os, subprocess, json
import numpy as np, cv2


CROP = (1250, 24, 670, 394)      # x, y, ancho, alto (1920x1080); se reescala si el clip tiene otra resolución
MIN_LINE = 100                   # píxeles rojos mínimos en una fila para ser borde horizontal de una entrada
MIN_LIFE = 0.5                   # s: menos que esto en pantalla = parpadeo
SCAN_VERSION = 5                 # subir si cambia la etapa 1 (invalida catalog/kf_cache/)
GAP = 7                          # px sin texto que separan el nombre del arma o del "+"
NAME_OK = 0.7                    # parecido mínimo con la plantilla para reconocer el nombre del jugador
DOUBT = 0.6                      # eventos con confianza menor se marcan para revisar a ojo


def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate,width,height',
                        '-of', 'json', path], capture_output=True, text=True)
    s = json.loads(r.stdout)['streams'][0]; n, d = s['r_frame_rate'].split('/')
    return float(n) / float(d), int(s['width']), int(s['height'])


def _runs(mask, gap=3):
    """(inicio, fin) de los tramos verdaderos de un vector booleano, uniendo huecos de hasta `gap`."""
    xs = np.flatnonzero(mask)
    if not len(xs): return []
    cut = np.flatnonzero(np.diff(xs) > gap + 1)
    starts = np.r_[xs[0], xs[cut + 1]]; ends = np.r_[xs[cut], xs[-1]]
    return list(zip(starts.tolist(), ends.tolist()))


def redmask(reg):
    """Píxeles del borde rojo. Lo que lo distingue es el verde bajo: la arena/naranja del mapa tiene mucho verde y no
    pasa; contra el cielo el borde se vuelve magenta (azul alto), así que el azul se tolera más."""
    r, g, b = reg[..., 2].astype(np.int16), reg[..., 1].astype(np.int16), reg[..., 0].astype(np.int16)
    return (r > 100) & (g * 100 < r * 45) & (b * 100 < r * 80)


def entries(reg, with_lines=False):
    """Cajas con borde rojo de un recorte del killfeed (BGR). Devuelve [(y0, y1, xl, xr), ...] de arriba a abajo.
    Una caja sale de dos bordes horizontales a ~30 px, o de uno solo más los dos verticales (contra el cielo o una
    pared clara el borde de arriba se aclara y deja de ser rojo)."""
    reg = reg.astype(np.int16)
    rm = redmask(reg)
    H, W = rm.shape
    cnt = rm.sum(1)
    lines, weak = [], []
    for ya, yb in _runs(cnt > MIN_LINE * 0.6, gap=0):
        if yb - ya > 6: continue                    # una franja roja gruesa no es un borde (pantalla roja al morir)
        rs = _runs(rm[ya:yb + 1].any(0), gap=30)
        xl, xr = max(rs, key=lambda q: q[1] - q[0])
        if xr - xl >= MIN_LINE: lines.append((ya, yb, xl, xr))
        elif xr - xl >= MIN_LINE * 0.6: weak.append((ya, yb, xl, xr))

    def edge(x0, x1, y0, y1):
        """Columna con más rojo entre y0 e y1 (borde vertical) y qué fracción de la altura cubre."""
        x0, x1, y0, y1 = max(0, x0), min(W, x1), max(0, y0), min(H, y1)
        if x1 <= x0 or y1 - y0 < 4: return None, 0.0
        f = rm[y0:y1, x0:x1].mean(0); k = int(np.argmax(f))
        return x0 + k, float(f[k])

    cand = []
    for i, (ya, yb, xl, xr) in enumerate(lines):
        for j in range(i + 1, len(lines)):          # par de bordes horizontales
            ya2, yb2, xl2, xr2 = lines[j]
            if ya2 - ya > 40: break
            if 24 <= ya2 - ya <= 38 and abs(xr - xr2) <= 8 and (abs(xl - xl2) <= 8 or min(xr - xl, xr2 - xl2) > 0.5 * max(xr - xl, xr2 - xl2)):
                cand.append((ya, yb2, min(xl, xl2), max(xl, xl2), max(xr, xr2), 2))
        for h in (31, -31):                         # un borde + los dos verticales
            y0, y1 = (ya, yb + h) if h > 0 else (ya + h, yb)
            if y0 < 0 or y1 > H: continue
            cl, fl = edge(xl - 6, xl + 14, y0 + 4, y1 - 3); cr, fr_ = edge(xr - 14, xr + 6, y0 + 4, y1 - 3)
            if fl >= 0.5 and (fr_ >= 0.5 or xr >= W - 4):     # (con HUD grande el borde derecho toca el recorte)
                cand.append((y0, y1, xl, xl, xr, 1))
    cand.sort(key=lambda c: (-c[5], c[0]))
    out = []
    for y0, y1, xa, xb, xr, _ in cand:
        if any(abs(y0 - o[0]) <= 8 and abs(xr - o[3]) <= 10 for o in out): continue
        el, fl = edge(xa - 6, xb + 14, y0 + 4, y1 - 3); er, fr_ = edge(xr - 14, xr + 6, y0 + 4, y1 - 3)
        out.append((y0, y1, el if fl >= 0.6 else xa, er if fr_ >= 0.6 else xr))
    out.sort()
    out = [o for o in out if not any(p[0] <= o[0] + 4 and o[1] <= p[1] + 4 and p is not o and p[1] - p[0] > o[1] - o[0] + 10 for p in out)]
    return (out, lines + weak) if with_lines else out


def text_of(reg, box):
    """Imagen del texto de una entrada (brillo sin el rojo: max(verde, azul)), sin los bordes."""
    y0, y1, xl, xr = box
    t = reg[y0 + 4:y1 - 3, xl + 4:xr - 3]
    return np.maximum(t[..., 0], t[..., 1])


def scan(path, keep_text=4):
    """Etapa 1: decodifica el recorte del killfeed y devuelve dict(fps, n, boxes=[[(y0,y1,xl,xr),...] por cuadro],
    text={(cuadro, i): imagen}) con el texto de cada caja cada `keep_text` cuadros."""
    fps, W, H = probe(path)
    sx, sy = W / 1920, H / 1080
    x, y, w, h = [int(round(v * s)) for v, s in zip(CROP, (sx, sy, sx, sy))]
    vf = f'crop={w}:{h}:{x}:{y}' + ('' if (W, H) == (1920, 1080) else f',scale={CROP[2]}:{CROP[3]}')
    w, h = CROP[2], CROP[3]
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', path, '-vf', vf, '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'],
                         stdout=subprocess.PIPE)
    boxes, lines, text = [], [], {}
    i = 0
    while True:
        b = p.stdout.read(w * h * 3)
        if len(b) < w * h * 3: break
        reg = np.frombuffer(b, np.uint8).reshape(h, w, 3)
        bx, ln = entries(reg, True); boxes.append(bx); lines.append(ln)
        for k, box in enumerate(bx):
            if i % keep_text == 0 or (i > 0 and len(boxes[-2]) != len(bx)):
                text[(i, k)] = text_of(reg, box)
        i += 1
    p.wait()
    return dict(fps=fps, n=len(boxes), boxes=boxes, lines=lines, text=text)


# ---------------------------------------------------------------- etapa 2: seguir entradas y decidir kill / muerte

def _ncc(a, b):
    a = a.astype(np.float32) - a.mean(); b = b.astype(np.float32) - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-6 else 0.0


def _sig(fr, tr):
    """Imagen representativa (mediana) del texto de una entrada seguida. Solo con los cuadros donde la caja tiene el
    ancho más común (si en un cuadro se cortó el borde izquierdo, el nombre del atacante quedaría afuera)."""
    ims = [fr['text'][key] for key in tr['keys'] if key in fr['text']]
    if not ims: return None
    wm = int(np.median([im.shape[1] for im in ims]))
    ims = [im for im in ims if abs(im.shape[1] - wm) <= 3] or ims
    h = min(im.shape[0] for im in ims); w = min(im.shape[1] for im in ims)
    if h < 8 or w < 40: return None
    return np.median(np.stack([im[:h, :w] for im in ims[:40]]), 0).astype(np.uint8)


def _clean(bx):
    """Cajas de un cuadro sin duplicados: si dos se pisan en vertical (más de la mitad), queda la de alto más normal."""
    keep = []
    for k in sorted(range(len(bx)), key=lambda k: abs((bx[k][1] - bx[k][0]) - 30)):
        y0, y1 = bx[k][0], bx[k][1]
        if all(min(y1, bx[j][1]) - max(y0, bx[j][0]) < 0.5 * min(y1 - y0, bx[j][1] - bx[j][0]) for j in keep):
            keep.append(k)
    return sorted(keep, key=lambda k: bx[k][0])


def _same_text(a, b, vict=0.6):
    """Dos imágenes de texto son la misma entrada: parecidas en total y también en la víctima (lado derecho).
    Alineadas a la derecha como el killfeed, tolerando unos px de corrimiento (la caja no siempre se lee igual)."""
    if a is None or b is None: return False
    best = (0.0, 0.0)
    for dy in (-3, -2, -1, 0, 1, 2, 3):
        for dx in (-2, 0, 2):
            aa = a[max(0, dy):a.shape[0] + min(0, dy)]; bb = b[max(0, -dy):b.shape[0] + min(0, -dy)]
            if dx > 0: aa = aa[:, :-dx]
            elif dx < 0: bb = bb[:, :dx]
            h = min(aa.shape[0], bb.shape[0]); w = min(aa.shape[1], bb.shape[1])
            if h < 8 or w < 40: continue
            aa, bb = aa[:h, aa.shape[1] - w:], bb[:h, bb.shape[1] - w:]
            r = max(8, w // 3)
            best = max(best, (_ncc(aa, bb), _ncc(aa[:, -r:], bb[:, -r:])))
    return best[0] > 0.75 and best[1] > vict


def tracks(fr):
    """Sigue cada caja roja en el tiempo. Devuelve [dict(first, last, n, keys=[(cuadro, i)], xl, w, y0, sig)]."""
    fps = fr['fps']; G = int(0.5 * fps)
    act, done = [], []
    for i, bx in enumerate(fr['boxes']):
        for t in [t for t in act if i - t['last'] > G]:
            act.remove(t); done.append(t)
        ks = _clean(bx)
        cand = []
        for k in ks:
            y0, y1, xl, xr = bx[k]
            for t in act:
                gap = i - t['last']; dy = y0 - t['y0']
                lo = -20 if gap <= 2 else -75
                if abs(xl - t['xl']) <= 10 and abs((xr - xl) - t['w']) <= 12 and lo <= dy <= 8:
                    cand.append((abs(xl - t['xl']) + 0.3 * abs(dy), k, id(t), t))
        cand.sort(key=lambda c: c[0]); uk, ut = set(), set()
        for _, k, tid, t in cand:
            if k in uk or tid in ut: continue
            uk.add(k); ut.add(tid)
            y0, y1, xl, xr = bx[k]
            t.update(last=i, y0=y0, n=t['n'] + 1); t['keys'].append((i, k))
            t['xls'].append(xl); t['ws'].append(xr - xl)
            t['xl'] = int(np.median(t['xls'][-15:])); t['w'] = int(np.median(t['ws'][-15:]))
        for k in ks:
            if k not in uk:
                y0, y1, xl, xr = bx[k]
                act.append(dict(first=i, last=i, n=1, y0=y0, y00=y0, xl=xl, w=xr - xl, xls=[xl], ws=[xr - xl], keys=[(i, k)]))
    done += act
    done.sort(key=lambda t: t['first'])
    for t in done: t['sig'] = _sig(fr, t); t['frames'] = {i for i, _ in t['keys']}
    # una entrada que se pierde un rato (pantalla roja al morir, destello, todas subiendo de golpe cuando vence la de
    # arriba) y vuelve a aparecer es la misma: se une con la anterior si tiene el mismo texto, nunca está más abajo y
    # las dos no se ven a la vez en un mismo cuadro
    out = []
    for t in done:
        prev = None
        for o in out:
            # mismo ancho, o una de las dos es la misma caja con el borde izquierdo cortado (se compara alineado a la derecha)
            same_box = abs(t['xl'] - o['xl']) <= 10 and abs(t['w'] - o['w']) <= 12
            cut = abs((t['xl'] + t['w']) - (o['xl'] + o['w'])) <= 10 and min(t['w'], o['w']) >= 60
            if -0.5 * fps <= t['first'] - o['last'] <= 8 * fps and (same_box or cut) and t['y00'] <= o['y0'] + 8 \
                    and len(t['frames'] & o['frames']) <= 2 and _same_text(t['sig'], o['sig']):
                prev = o
        if prev is not None:
            prev.update(last=max(prev['last'], t['last']), n=prev['n'] + t['n'], y0=t['y0']); prev['keys'] += t['keys']
            prev['frames'] |= t['frames']
            if t['w'] > prev['w'] + 12: prev.update(sig=t['sig'], w=t['w'], xl=t['xl'])     # la versión completa
        else:
            out.append(t)
    for t in out: t['start'] = t['first']
    return out


# ---------------------------------------------------------------- nombre del jugador

def _ink(sig):
    """Máscara de letras: más claras que el fondo de la entrada (umbral de Otsu, nunca menos de 100)."""
    s = np.ascontiguousarray(sig, np.uint8)
    otsu, _ = cv2.threshold(s, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return s > max(100.0, otsu)


def _span(sig):
    xs = np.flatnonzero(_ink(sig).sum(0) >= 2)
    return (int(xs[0]), int(xs[-1]) + 1) if len(xs) else None


def _tight(im):
    """Recorta una imagen de texto a la caja de sus letras."""
    m = _ink(im); ys = np.flatnonzero(m.sum(1) >= 1); xs = np.flatnonzero(m.sum(0) >= 1)
    if len(ys) < 5 or len(xs) < 6: return None
    return im[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1]


def _block(sig, side, gap=None):
    """Primer bloque de texto desde la izquierda ('L') o la derecha ('R'): el atacante o la víctima. Termina en el
    primer hueco de `gap` columnas sin letras. Solo se usa para aprender plantillas; para decidir se usa _find."""
    if sig is None: return None
    gap = GAP if gap is None else gap
    xs = np.flatnonzero(_ink(sig).sum(0) >= 2)
    if not len(xs): return None
    if side == 'R': xs = xs[::-1]
    a = b = xs[0]
    for x in xs[1:]:
        if abs(x - b) > gap: break
        b = x
    a, b = min(a, b), max(a, b)
    return _tight(sig[:, a:b + 1]) if b - a >= 6 else None


def _find(sig, tpl):
    """Mejor lugar de la plantilla dentro de la entrada: (parecido 0-1, x)."""
    if sig is None or tpl is None or sig.shape[1] < tpl.shape[1] + 1: return 0.0, -1
    t = tpl
    if t.shape[0] >= sig.shape[0]:
        d = t.shape[0] - sig.shape[0] + 1; t = t[d // 2:d // 2 + sig.shape[0] - 1]
    if t.shape[0] < 5: return 0.0, -1
    r = cv2.matchTemplate(sig.astype(np.float32), t.astype(np.float32), cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(r)
    return float(mx), int(loc[0])


def _sim(a, b):
    """Parecido entre dos nombres recortados (mismo ancho ±8 %)."""
    if a is None or b is None or abs(a.shape[1] - b.shape[1]) > max(3, 0.08 * max(a.shape[1], b.shape[1])): return 0.0
    big, small = (a, b) if a.shape[0] * a.shape[1] >= b.shape[0] * b.shape[1] else (b, a)
    pad = cv2.copyMakeBorder(big, 3, 3, 4, 4, cv2.BORDER_REPLICATE)
    return _find(pad, small)[0]


def _where(sig, tpls):
    """Parecido del nombre del jugador pegado a la izquierda (mató), a la derecha (murió) o en el medio (asistencia)."""
    sp = _span(sig) if sig is not None else None
    sl = sr = sm = 0.0
    if sp is None: return sl, sr, sm
    ink = _ink(sig).sum(0) >= 2
    for tp in tpls:
        s, x = _find(sig, tp)
        if x < 0: continue
        if x - sp[0] <= 6: sl = max(sl, s)
        elif sp[1] - (x + tp.shape[1]) <= 6: sr = max(sr, s)
        elif not ink[max(0, x - 4):max(0, x - 1)].any(): sm = max(sm, s)     # separado de lo anterior ("X + jugador")
    return sl, sr, sm


def _groups(blocks, thr=0.8):
    groups = []
    for im in blocks:
        for g in groups:
            if _sim(im, g[0]) > thr: g.append(im); break
        else:
            groups.append([im])
    return sorted(groups, key=len, reverse=True)


def _medoid(g):
    return max(g, key=lambda x: sum(_sim(x, y) for y in g))


def _live(fr):
    """Entradas nuevas del clip (no estaban al empezar y duran más que un parpadeo)."""
    return [t for t in tracks(fr) if t['first'] > 2 and (t['last'] - t['first'] + 1) / fr['fps'] >= MIN_LIFE]


def clip_name(trs):
    """El jugador de la play: todas las entradas con borde rojo lo nombran (como atacante, víctima o asistencia), así
    que es el nombre que aparece en más entradas. Candidatos: el primer y el último nombre de cada entrada.
    Devuelve (imagen del nombre, en cuántas entradas aparece) o (None, 0) si ningún nombre se repite."""
    cands = []
    for t in trs:
        for side in ('L', 'R'):
            b = _block(t['sig'], side)
            # un nombre es una línea de texto; los íconos (arma, calavera) son más altos y se repiten en todas las
            # entradas, así que no pueden ser candidatos
            if b is not None and b.shape[1] < 220 and b.shape[0] <= 0.6 * t['sig'].shape[0]: cands.append((b, side))
    best, bc = None, 1
    for b, side in cands:
        c = sum(_find(t['sig'], b)[0] >= 0.8 for t in trs)
        if c > bc or (c == bc and best is not None and side == 'L' and b.shape[1] > best.shape[1]): best, bc = b, c
    return (best, bc) if best is not None else (None, 0)


def player_names(frs):
    """Nombres del jugador en un proyecto (uno por cuenta), deducidos de las plays donde un nombre se repite. Sirven
    para los clips con una sola entrada roja, donde no hay repetición que diga quién es el jugador."""
    found = [n for n, c in (clip_name(_live(fr)) for fr in frs) if n is not None]
    return [_medoid(g) for g in _groups(found)]


# ---------------------------------------------------------------- etapa 2 completa: eventos con confianza

def detect(fr, names=None):
    """Kills propias del clip: [dict(t, conf, why, life, kind)] por tiempo. kind 'kill' = el nombre del jugador a la
    izquierda de una entrada nueva; 'dudosa' = entrada nueva en la que no se pudo leer quién mató. Muertes y
    asistencias no son kills: quedan en fr['otros']. El jugador se deduce de la propia play (clip_name); si en el
    clip no se repite ningún nombre, se prueba con `names` (player_names del resto del proyecto)."""
    fps = fr['fps']
    trs = _live(fr)
    tp, cnt = clip_name(trs); src = 'clip'
    if tp is None and names:
        sc = [(max([_find(t['sig'], n)[0] for t in trs] or [0.0]), k) for k, n in enumerate(names)]
        s_, k = max(sc) if sc else (0.0, -1)
        if s_ >= 0.8: tp, src = names[k], 'proyecto'
    fr['jugador'] = dict(src=src if tp is not None else None, veces=cnt)
    ev, otros, victims = [], [], []
    for t in sorted(trs, key=lambda t: t['start']):
        # la misma entrada (mismo atacante, arma y víctima) que ya se contó hace menos de 20 s: se perdió y volvió a
        # aparecer, no es una kill nueva (un enemigo muere una sola vez por ronda)
        dup = [tv for tv, sg in victims if t['start'] - tv < 20 * fps and _same_text(t['sig'], sg, vict=0.85)]
        if dup:
            otros.append(dict(t=round(t['start'] / fps, 3), kind='repetida', why=f'misma víctima que en {dup[0] / fps:.2f}s'))
            continue
        life = (t['last'] - t['start'] + 1) / fps
        exp = min(4.5, (fr['n'] - t['start']) / fps)
        k_life = 1.0 if life >= 0.4 * exp else 0.7
        sl, sr, sm = _where(t['sig'], [tp]) if tp is not None else (0.0, 0.0, 0.0)
        tt = round(t['start'] / fps, 3)
        if sl >= NAME_OK and sl >= sr:
            conf = (0.75 + 0.25 * min(1.0, (sl - NAME_OK) / (1 - NAME_OK))) * k_life * (1.0 if src == 'clip' else 0.9)
            why = f'jugador a la izquierda ({sl:.2f})' + ('' if src == 'clip' else ', nombre de otro clip')                 + ('' if k_life == 1 else f', dura poco ({life:.1f}s)')
            ev.append(dict(t=tt, conf=round(conf, 2), why=why, life=round(life, 2), kind='kill'))
            victims.append((t['start'], t['sig']))
        elif sr >= NAME_OK:
            otros.append(dict(t=tt, kind='muerte', why=f'jugador a la derecha ({sr:.2f})'))
        elif sm >= 0.8:
            otros.append(dict(t=tt, kind='asistencia', why=f'jugador en el medio ({sm:.2f})'))
        else:
            why = 'no se leyó el nombre del jugador' if tp is not None else 'una sola entrada: no se sabe cuál es el jugador'
            ev.append(dict(t=tt, conf=round(0.45 * k_life, 2), why=why, life=round(life, 2), kind='dudosa'))
            victims.append((t['start'], t['sig']))
    # dos eventos casi juntos de la misma entrada (caja partida en un cuadro) -> uno
    ev.sort(key=lambda e: e['t']); out = []
    for e in ev:
        if out and e['t'] - out[-1]['t'] < 0.1:
            if e['conf'] > out[-1]['conf']: out[-1] = e
            continue
        out.append(e)
    fr['otros'] = otros
    return out
