"""Traduce minutos del video terminado (los que marca el usuario) a lo que hay en el plan, y arma tiras de cuadros.

    python engine/locate.py projects/<nombre> 1:23,2:05.5,47        -> reporte + tiras en projects/<nombre>/insp/
    opciones: --span 1.0 (segundos antes y después)  --step 0.1 (cada cuánto un cuadro)  --video output/<nombre>/video/x.mp4  --no-img

Para cada tiempo dice: tramo del plan, clip (y archivo original), tiempo dentro del clip, play (ACT1/ACT2 e índice),
kill más cercana (clip, índice, distancia), transición más cercana, título visible y tiempo de canción.
Las tiras muestran arriba el clip original (sin efectos) y abajo el video renderizado en el mismo momento.
"""
import os, sys, re, argparse, importlib.util
import numpy as np, cv2

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)


def load_plan(project):
    spec = importlib.util.spec_from_file_location('plan', os.path.join(project, 'plan.py'))
    cwd = os.getcwd(); os.chdir(project); sys.path.insert(0, project)
    import io, contextlib
    m = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(m)
    os.chdir(cwd)
    return m


def parse_t(s):
    s = s.strip()
    if ':' in s:
        m, sec = s.split(':')
        return int(m) * 60 + float(sec)
    return float(s)


def fmt(t):
    return f'{int(t // 60)}:{t % 60:05.2f}'


def clip_map(project):
    out = {}
    p = os.path.join(project, 'clips_map.txt')
    if os.path.exists(p):
        for line in open(p, encoding='utf-8', errors='replace'):
            m = re.match(r'\s*c(\d+)\s*<-\s*(.+?\.mp4)', line)
            if m: out[int(m.group(1))] = m.group(2).strip()
    return out


def find_play(plan, seg):
    """Devuelve ('ACT1', i, dict) para el tramo."""
    pl = seg.get('play', -9)
    if pl < 0: return None
    acts = (('ACT1', plan.ACT1, 0), ('ACT2', plan.ACT2, 100))
    for name, act, base in acts:
        i = pl - base
        if 0 <= i < len(act): return name, i, act[i]
    return None


def src_time(seg, t):
    if seg['kind'] == 'slowmo':
        f = (t - seg['o0']) / max(1e-6, seg['o1'] - seg['o0'])
        return seg['s0'] + f * (seg['s1'] - seg['s0'])
    return seg['s0'] + (t - seg['o0'])


def grab(path, times, w=384, h=216):
    cap = cv2.VideoCapture(path); ims = []
    for t in times:
        if t < 0: ims.append(np.zeros((h, w, 3), np.uint8)); continue
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, f = cap.read()
        ims.append(cv2.resize(f, (w, h), interpolation=cv2.INTER_AREA) if ok else np.zeros((h, w, 3), np.uint8))
    return ims


def tile(ims, labels, cols, color):
    out = []
    for im, lb in zip(ims, labels):
        im = im.copy(); cv2.putText(im, lb, (5, 20), 0, 0.55, (0, 0, 0), 3); cv2.putText(im, lb, (5, 20), 0, 0.55, color, 1); out.append(im)
    while len(out) % cols: out.append(np.zeros_like(out[0]))
    return np.vstack([np.hstack(out[i:i + cols]) for i in range(0, len(out), cols)])


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    ap = argparse.ArgumentParser()
    ap.add_argument('project'); ap.add_argument('times')
    ap.add_argument('--span', type=float, default=1.0); ap.add_argument('--step', type=float, default=0.1)
    ap.add_argument('--video'); ap.add_argument('--no-img', action='store_true')
    a = ap.parse_args()
    project = os.path.abspath(a.project); name = os.path.basename(project)
    plan = load_plan(project); cmap = clip_map(project)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import paths
    video = a.video or paths.find_video(name)
    kid = list(getattr(plan, 'kill_id', [None] * len(plan.kills)))
    os.makedirs(os.path.join(project, 'insp'), exist_ok=True)

    for ts in a.times.split(','):
        T = parse_t(ts)
        seg = next((s for s in plan.segments if s['o0'] <= T < s['o1']), None)
        print(f'\n=== {fmt(T)}  ({T:.2f} s del video, canción {T + plan.SONG_A0:.2f} s) ===')
        if seg is None:
            print('  fuera del plan (después del final)'); continue
        kind = seg['kind']
        if kind in ('logo', 'interlude', 'outro'):
            print(f'  tramo: {kind} ({fmt(seg["o0"])} - {fmt(seg["o1"])}), sin clip')
        else:
            c = seg['clip']; st = src_time(seg, T)
            fp = find_play(plan, seg)
            print(f'  tramo: {kind}{" (ráfaga)" if seg.get("burst") else ""}  c{c} = {cmap.get(c, "?")}')
            print(f'  en el clip: {st:.2f} s   (el tramo muestra {seg["s0"]:.2f}-{seg["s1"]:.2f} s del clip, '
                  f'en el video {fmt(seg["o0"])}-{fmt(seg["o1"])})')
            if fp:
                act, i, P = fp
                desc = {k: v for k, v in P.items() if k in ('cap', 'kill_at', 'start_at', 'hard', 'tech', 'flash', 'tin')}
                print(f'  play: {act}[{i}]  clip={P.get("clip", "burst")}  {desc}')
        if len(plan.kills):
            ks = np.array(plan.kills); j = int(np.argmin(abs(ks - T)))
            who = kid[j] if j < len(kid) else None
            print(f'  kill más cercana: {fmt(ks[j])} ({ks[j] - T:+.2f} s)  ' + (f'c{who[0]} kill #{who[1]}' if who else ''))
            near = [(round(float(k - T), 2), kid[i] if i < len(kid) else None) for i, k in enumerate(ks) if abs(k - T) <= 3 and i != j]
            if near: print(f'  otras kills a ±3 s: {near}')
        if getattr(plan, 'boundaries', None):
            b = min(plan.boundaries, key=lambda x: abs(x[0] - T))
            print(f'  transición más cercana: {b[1]} en {fmt(b[0])} ({b[0] - T:+.2f} s)')
        caps = [cp for o, cp in plan.captions if o <= T <= o + 1.6]
        if caps: print(f'  título en pantalla: {caps[0]}')

        if a.no_img: continue
        offs = np.round(np.arange(-a.span, a.span + 1e-6, a.step), 3)
        rows = []
        if kind not in ('logo', 'interlude', 'outro'):
            cp = os.path.join(project, 'clips', f'c{seg["clip"]}.mp4')
            st = src_time(seg, T)
            rows.append(tile(grab(cp, [st + o for o in offs]), [f'c{seg["clip"]} {st + o:.2f}' for o in offs], 7, (0, 255, 255)))
        if os.path.exists(video):
            rows.append(tile(grab(video, [T + o for o in offs]), [f'video {fmt(T + o)}' for o in offs], 7, (255, 255, 0)))
        if rows:
            wmax = max(r.shape[1] for r in rows)
            rows = [np.pad(r, ((0, 12), (0, wmax - r.shape[1]), (0, 0))) for r in rows]
            out = os.path.join(project, 'insp', f'locate_{fmt(T).replace(":", "-")}.jpg')
            cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
            print(f'  tiras: {out}')


if __name__ == '__main__':
    main()
