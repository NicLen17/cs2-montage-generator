"""Evaluación del detector de kills propias contra las kills verificadas a ojo.

    python engine/eval_kills.py                      -> detector nuevo (engine/killfeed.py) vs. catálogo
    python engine/eval_kills.py --baseline           -> además, el detector viejo (conteo de líneas rojas) para comparar
    python engine/eval_kills.py -v                   -> detalle por clip (faltantes y sobrantes)
    python engine/eval_kills.py --doubt              -> lista de los eventos dudosos y si eran kill o no
    python engine/eval_kills.py --disagree           -> kills seguras del killfeed que el catálogo no tiene (hoja en kf_cache/)
    python engine/eval_kills.py --root <repo>        -> carpeta con catalog/ y projects/ (por defecto, la del repo)
    python engine/eval_kills.py --player Wako,ElWako -> con ese nick del jugador (por defecto, el del preset; "" = ninguno)
    python engine/eval_kills.py --no-audio           -> sin el audio como segunda señal (solo el killfeed)

Verdad: las kills de los clips marcados verified en catalog/clips.json (una entrada por clip original, sin repetir).
El video de cada clip sale de la copia a 60 fps de algún proyecto (clips_map.txt) o, si no hay, de entrada/.
Una detección es correcta si cae a ±TOL s de una kill verdadera (emparejamiento uno a uno).
La etapa lenta (leer el killfeed cuadro por cuadro) se guarda en catalog/kf_cache/ y se reusa.
"""
import os, sys, re, json, pickle, argparse
from concurrent.futures import ProcessPoolExecutor
import numpy as np

ENGINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE)
import killfeed as K
import nick as N

TOL = 0.35


def slug(f):
    b = re.sub(r'\s*\(\d+\)', '', os.path.basename(f)); b = re.sub(r'\.mp4$', '', b, flags=re.I)
    return re.sub(r'_source$', '', b)


def dataset(root):
    db = json.load(open(os.path.join(root, 'catalog', 'clips.json'), encoding='utf-8'))
    cands = {}
    pj = os.path.join(root, 'projects')
    for p in sorted(os.listdir(pj)):
        cm = os.path.join(pj, p, 'clips_map.txt')
        if not os.path.exists(cm): continue
        for line in open(cm, encoding='utf-8', errors='replace'):
            m = re.match(r'\s*c(\d+)\s*<-\s*(.+?\.mp4)', line)
            if m:
                v = os.path.join(pj, p, 'clips', f'c{m.group(1)}.mp4')
                if os.path.exists(v): cands.setdefault(slug(m.group(2)), []).append(v)
    ent = os.path.join(root, 'entrada')
    for f in (os.listdir(ent) if os.path.isdir(ent) else []):
        if f.lower().endswith('.mp4'): cands.setdefault(slug(f), []).append(os.path.join(ent, f))
    out = []
    for k, e in sorted(db.items()):
        if not e.get('verified') or e.get('kills') is None or e.get('era') == 'csgo' or k not in cands: continue
        vids = sorted(cands[k], key=lambda v: (abs(K.probe(v)[0] - 60) > 0.5, 'entrada' in v))
        out.append(dict(slug=k, video=vids[0], kills=list(e['kills'])))
    return out


def cached_scan(args):
    k, v, cache = args
    f = os.path.join(cache, k + '.pkl')
    key = (os.path.getsize(v), int(os.path.getmtime(v)), K.SCAN_VERSION)
    if os.path.exists(f):
        d = pickle.load(open(f, 'rb'))
        if d.get('key') == key: return v, d['fr']
    fr = K.scan(v)
    pickle.dump(dict(key=key, fr=fr), open(f, 'wb'), protocol=4)
    return v, fr


def cached_env(args):
    """La envolvente del audio de cada clip (segunda señal del detector), también en catalog/kf_cache/."""
    k, v, cache = args
    f = os.path.join(cache, k + '.env.pkl')
    key = (os.path.getsize(v), int(os.path.getmtime(v)), K.ENV_SR)
    if os.path.exists(f):
        d = pickle.load(open(f, 'rb'))
        if d.get('key') == key: return v, d['env']
    env = K.audio_env(v)
    pickle.dump(dict(key=key, env=env), open(f, 'wb'), protocol=4)
    return v, env


def baseline(v):
    """El detector viejo de analyze_clips.py (hasta el 20/11/2026), copiado tal cual para comparar."""
    import subprocess
    from scipy.ndimage import median_filter
    w, h = 670, 394
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', v, '-vf', 'crop=670:394:1250:24', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'],
                         stdout=subprocess.PIPE)
    cnt = []
    while True:
        b = p.stdout.read(w * h * 3)
        if len(b) < w * h * 3: break
        reg = np.frombuffer(b, np.uint8).reshape(h, w, 3).astype(np.int16)
        m = (reg[..., 2] > 170) & (reg[..., 2] - np.maximum(reg[..., 1], reg[..., 0]) > 60)
        rows = np.where(m.sum(1) > 110)[0]; groups = []; last = -10
        for y in rows:
            if y - last > 1: groups.append([y, y])
            else: groups[-1][1] = y
            last = y
        ctr = [(a + b) / 2 for a, b in groups]; g = 0; i = 0
        while i < len(ctr) - 1:
            if 25 <= ctr[i + 1] - ctr[i] <= 35: g += 1; i += 2
            else: i += 1
        cnt.append(g)
    cnt = np.array(cnt)
    e = median_filter(cnt, 9).astype(int); ev = []
    for i in range(1, len(e) - 18):
        if e[i] >= e[i - 1] + 1 and e[i:i + 18].min() > e[i - 1]:
            if not ev or i / 60 - ev[-1] > 0.15: ev.append(round(i / 60, 3))
    return v, ev


def match(det, truth, tol=TOL):
    """Emparejamiento uno a uno por cercanía. Devuelve (aciertos [(d, t)], sobrantes [d], faltantes [t])."""
    pairs = sorted((abs(d - t), i, j) for i, d in enumerate(det) for j, t in enumerate(truth) if abs(d - t) <= tol)
    ui, uj, hit = set(), set(), []
    for _, i, j in pairs:
        if i in ui or j in uj: continue
        ui.add(i); uj.add(j); hit.append((det[i], truth[j]))
    return hit, [d for i, d in enumerate(det) if i not in ui], [t for j, t in enumerate(truth) if j not in uj]


def score(name, res, data, verbose=False, tol=TOL):
    tp = fp = fn = 0; offs = []
    for d in data:
        hit, extra, miss = match(res[d['video']], d['kills'], tol)
        tp += len(hit); fp += len(extra); fn += len(miss); offs += [a - b for a, b in hit]
        if verbose and (extra or miss):
            print(f'   {d["slug"][:44]:44}  faltan {miss}  sobran {extra}')
    p = tp / max(1, tp + fp); r = tp / max(1, tp + fn)
    print(f'{name:28} kills {tp + fn:4}  aciertos {tp:4}  faltantes {fn:4}  sobrantes {fp:4}   '
          f'precisión {p:6.1%}  recall {r:6.1%}  F1 {2 * p * r / max(1e-9, p + r):6.1%}'
          + (f'   desfase mediano {np.median(offs):+.2f}s' if offs else ''))
    return p, r


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.path.dirname(ENGINE))
    ap.add_argument('--baseline', action='store_true'); ap.add_argument('-v', action='store_true')
    ap.add_argument('--refresh', action='store_true'); ap.add_argument('--doubt', action='store_true')
    ap.add_argument('--disagree', action='store_true')
    ap.add_argument('--player', default=None); ap.add_argument('--no-audio', action='store_true')
    a = ap.parse_args()
    cache = os.path.join(a.root, 'catalog', 'kf_cache'); os.makedirs(cache, exist_ok=True)
    dsf = os.path.join(cache, 'dataset.json')
    if os.path.exists(dsf) and not a.refresh and os.path.getmtime(dsf) > os.path.getmtime(os.path.join(a.root, 'catalog', 'clips.json')):
        data = json.load(open(dsf, encoding='utf-8'))
    else:
        data = dataset(a.root); json.dump(data, open(dsf, 'w', encoding='utf-8'), indent=1)
    print(f'{len(data)} clips verificados, {sum(len(d["kills"]) for d in data)} kills')
    vids = [d['video'] for d in data]
    with ProcessPoolExecutor() as ex:
        frs = dict(ex.map(cached_scan, [(d['slug'], d['video'], cache) for d in data]))
        envs = {} if a.no_audio else dict(ex.map(cached_env, [(d['slug'], d['video'], cache) for d in data]))
        base = None
        if a.baseline:
            bf = os.path.join(cache, 'baseline.json')
            base = json.load(open(bf)) if os.path.exists(bf) else {}
            todo = [v for v in vids if v not in base]
            base.update(dict(ex.map(baseline, todo))); json.dump(base, open(bf, 'w'), indent=1)
    # el jugador se deduce de cada play (el nombre que se repite en sus entradas rojas); para los clips con una sola
    # entrada se usan los nombres deducidos del resto (como en un proyecto con muchos clips). Si el preset declara el
    # nick, sus plantillas se aprenden de estos mismos clips (sin guardarlas: la evaluación no escribe en catalog/nicks/)
    names = K.player_names([frs[v] for v in vids])
    nicks = [x.strip() for x in a.player.split(',') if x.strip()] if a.player is not None else N.configured()
    nick = N.templates(nicks, [frs[v] for v in vids], save=False)
    if nicks: print(f'nick del jugador: {", ".join(nicks)} ({len(nick)} plantillas)')
    evs = {v: K.detect(frs[v], names=names, nick=nick, audio=envs.get(v)) for v in vids}
    allk = {v: [e['t'] for e in ev] for v, ev in evs.items()}
    sure = {v: [e['t'] for e in ev if e['conf'] >= K.DOUBT] for v, ev in evs.items()}
    doubt = {v: [e['t'] for e in ev if e['conf'] < K.DOUBT] for v, ev in evs.items()}
    for tol in (TOL, 0.7):
        print(f'\n--- tolerancia ±{tol} s ---')
        if base: score('detector viejo (conteo)', base, data, a.v and tol == TOL, tol)
        score('detector nuevo (killfeed)', allk, data, a.v and tol == TOL, tol)
        score(f'  solo seguros (conf>={K.DOUBT})', sure, data, tol=tol)
        score('  solo dudosos', doubt, data, tol=tol)
    nd = sum(len(x) for x in doubt.values()); nt = sum(len(x) for x in allk.values())
    print(f'\ndudosos para mirar a ojo: {nd} de {nt} eventos ({len(names)} nombres de jugador deducidos de las plays)')
    if a.doubt:
        for d in data:
            for e in evs[d['video']]:
                if e['conf'] < K.DOUBT:
                    ok = any(abs(e['t'] - t) <= TOL for t in d['kills'])
                    print(f'   {d["slug"][:40]:40} {e["t"]:7.2f}  conf {e["conf"]:.2f}  {e["why"]}  -> {"KILL" if ok else "no"}')
    if a.disagree:
        # kills SEGURAS del killfeed que el catálogo no tiene (ni a ±0.7 s): candidatas a kill faltante en el catálogo.
        import cv2
        rows = []; print('\nKills seguras del killfeed que no están en el catálogo (revisar a ojo; el catálogo NO se toca):')
        for d in data:
            for e in evs[d['video']]:
                if e['conf'] >= K.DOUBT and not any(abs(e['t'] - t) <= 0.7 for t in d['kills']):
                    print(f'   {d["slug"]}  {e["t"]:.2f}s  (catálogo: {d["kills"]})')
                    cap = cv2.VideoCapture(d['video']); cap.set(1, int((e['t'] + 0.6) * frs[d['video']]['fps'])); ok, f = cap.read()
                    if ok:
                        k = K.view(f, frs[d['video']].get('layout'))
                        cv2.putText(k, f'{d["slug"][:26]} {e["t"]:.2f}', (6, 172), 0, 0.5, (0, 255, 255), 1); rows.append(k)
        if rows:
            while len(rows) % 4: rows.append(np.zeros_like(rows[0]))
            out = os.path.join(cache, 'discrepancias.jpg')
            cv2.imwrite(out, np.vstack([np.hstack(rows[i:i + 4]) for i in range(0, len(rows), 4)])); print('Hoja:', out)


if __name__ == '__main__':
    main()
