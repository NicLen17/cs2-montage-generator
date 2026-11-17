"""Paquete para subir un edit a YouTube: cuadros candidatos para la miniatura, miniatura y datos (capítulos, plays).

    python engine/publish.py projects/<nombre> frames
        -> projects/<nombre>/publish/thumbs/cand_NN.jpg (cuadro de cada kill con título y de cada drop) + thumbs_sheet.jpg
    python engine/publish.py projects/<nombre> thumb --frame 3 --text "ACE" --sub "USP-S" [--side left|right]
        -> projects/<nombre>/publish/thumbnail.jpg (1280x720, < 2 MB)
    python engine/publish.py projects/<nombre> info
        -> projects/<nombre>/publish/info.json: capítulos válidos para YouTube, plays con título, duración, canción

Capítulos de YouTube: el primero en 0:00, al menos 3, cada uno de 10 s o más (si no, YouTube los ignora).
"""
import os, sys, json, argparse, subprocess, importlib.util, io, contextlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
FD = os.path.join(ENGINE, 'assets', 'fonts')
F800, F600 = os.path.join(FD, 'montserrat-latin-800-normal.woff'), os.path.join(FD, 'montserrat-latin-600-normal.woff')


def load_plan(project):
    spec = importlib.util.spec_from_file_location('plan', os.path.join(project, 'plan.py'))
    cwd = os.getcwd(); os.chdir(project); sys.path.insert(0, project)
    m = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(m)
    os.chdir(cwd)
    return m


def fmt(t):
    t = int(t); return f'{t // 60}:{t % 60:02d}'


def grab(video, t, out):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.3f}', '-i', video, '-frames:v', '1', '-q:v', '2', out])


def kill_moments(p):
    """(tiempo, etiqueta) de las kills de plays con título y de las kills en drops."""
    out = []
    caps = sorted(p.captions)
    for o, cap in caps:
        seg = next((g for g in p.segments if g['o0'] <= o < g['o1']), None)
        end = max((g['o1'] for g in p.segments if seg and g['play'] == seg['play']), default=o + 12)
        nxt = [k for k in p.kills if o - 0.2 <= k <= end]      # solo las kills de esa play
        for k in nxt[:6]: out.append((k + 0.2, f'{cap[0]} {cap[1] if len(cap) > 1 else ""}'.strip()))
    for P in list(p.ACT1) + list(p.ACT2):
        if 'kill_at' in P: out.append((P['kill_at'] - p.SONG_A0 + 0.15, f'drop c{P["clip"]}'))
    seen, res = [], []
    for t, lb in sorted(out):
        if all(abs(t - s) > 0.4 for s in seen): seen.append(t); res.append((t, lb))
    return res


def cmd_frames(project, p, video):
    d = os.path.join(project, 'publish', 'thumbs'); os.makedirs(d, exist_ok=True)
    ms = kill_moments(p); tiles = []
    for i, (t, lb) in enumerate(ms):
        f = os.path.join(d, f'cand_{i:02d}.jpg'); grab(video, t, f)
        if not os.path.exists(f): continue
        im = Image.open(f).convert('RGB').resize((480, 270)); dr = ImageDraw.Draw(im)
        dr.rectangle((0, 0, 480, 30), fill=(0, 0, 0)); dr.text((8, 4), f'{i:02d}  {fmt(t)}  {lb}', font=ImageFont.truetype(F600, 18), fill=(255, 255, 0))
        tiles.append(im)
    cols = 4; rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new('RGB', (480 * cols, 270 * max(1, rows)))
    for i, im in enumerate(tiles): sheet.paste(im, ((i % cols) * 480, (i // cols) * 270))
    sp = os.path.join(project, 'publish', 'thumbs_sheet.jpg'); sheet.save(sp, quality=85)
    print(f'{len(tiles)} candidatos en {d}\nHoja: {sp}')


def text_layer(size, txt, font, fill, stroke, x, y, spacing=0):
    lay = Image.new('RGBA', size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for ch in txt:
        d.text((x, y), ch, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0, 255)); x += font.getlength(ch) + spacing
    return lay


def cmd_thumb(project, p, a):
    src = os.path.join(project, 'publish', 'thumbs', f'cand_{a.frame:02d}.jpg')
    if not os.path.exists(src): raise SystemExit(f'No existe {src}: corré primero "frames".')
    W, H = 1280, 720
    im = Image.open(src).convert('RGB')
    if a.zoom > 1:                                   # zoom hacia el centro (mira); máximo 2x para no pixelar
        z = min(2.0, a.zoom); w, h = im.size; cw, ch = w / z, h / z
        im = im.crop(((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2))
    im = im.resize((W, H), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.18); im = ImageEnhance.Color(im).enhance(1.25); im = ImageEnhance.Sharpness(im).enhance(1.3)
    base = im.convert('RGBA')
    # degradado oscuro del lado del texto para que se lea
    g = np.linspace(1, 0, W // 2) ** 1.4 * 200
    grad = np.zeros((H, W), np.uint8)
    if a.side == 'left': grad[:, :W // 2] = g
    else: grad[:, W - W // 2:] = g[::-1]
    shade = Image.new('RGBA', (W, H), (0, 0, 0, 0)); shade.putalpha(Image.fromarray(grad))
    base.alpha_composite(shade)
    big = ImageFont.truetype(F800, a.size); sub = ImageFont.truetype(F800, max(40, a.size // 3))
    tw = sum(big.getlength(c) for c in a.text) + 6 * (len(a.text) - 1)
    sw = sum(sub.getlength(c) for c in a.sub) + 4 * max(0, len(a.sub) - 1)
    x = 60 if a.side == 'left' else W - 60 - max(tw, sw)
    y = H // 2 - a.size // 2 - (30 if a.sub else 0)
    glow = text_layer((W, H), a.text, big, (255, 255, 255, 255), 0, x, y, 6).filter(ImageFilter.GaussianBlur(14))
    base.alpha_composite(glow)
    base.alpha_composite(text_layer((W, H), a.text, big, (255, 255, 255, 255), 6, x, y, 6))
    if a.sub:
        base.alpha_composite(text_layer((W, H), a.sub, sub, (255, 214, 90, 255), 4, x + 4, y + a.size + 6, 4))
    # logo circular abajo, del lado contrario al texto
    lp = os.path.join(project, 'logo.png') if os.path.exists(os.path.join(project, 'logo.png')) else os.path.join(ENGINE, 'assets', 'logo.png')
    R = 70; lg = Image.open(lp).convert('RGBA').resize((2 * R, 2 * R), Image.LANCZOS)
    mask = Image.new('L', (2 * R, 2 * R), 0); ImageDraw.Draw(mask).ellipse((0, 0, 2 * R - 1, 2 * R - 1), fill=255); lg.putalpha(mask)
    lx = W - 2 * R - 36 if a.side == 'left' else 36; ly = H - 2 * R - 30
    ring = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ImageDraw.Draw(ring).ellipse((lx - 6, ly - 6, lx + 2 * R + 6, ly + 2 * R + 6), outline=(200, 90, 255, 255), width=6)
    base.alpha_composite(ring); base.alpha_composite(lg, (lx, ly))
    out = os.path.join(project, 'publish', 'thumbnail.jpg')
    base.convert('RGB').save(out, quality=90)
    print(f'Miniatura: {out}  ({os.path.getsize(out) / 1024:.0f} KB)')


def song_tags(project):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format_tags=artist,title', '-of', 'json', os.path.join(project, 'song.mp3')],
                       capture_output=True, text=True)
    try: return json.loads(r.stdout)['format'].get('tags', {})
    except Exception: return {}


def chapters(p):
    segs = p.segments; ch = [(0.0, 'Intro')]
    first = next((s for s in segs if s['kind'] in ('zoom_out', 'play')), None)
    if first: ch.append((first['o0'], 'Primera play'))
    for o, cap in sorted(p.captions):
        ch.append((o - 0.5, f'{cap[0]} con {cap[1]}' if len(cap) > 1 and cap[1] else cap[0]))
    inter = next((s for s in segs if s['kind'] == 'interlude'), None)
    if inter: ch.append((inter['o0'], 'Interludio')); ch.append((inter['o1'], 'Segundo drop'))
    face = next((s for s in segs if s['kind'] == 'face_out'), None)
    if face: ch.append((face['o0'] - 3, 'Cierre'))
    ch.sort(key=lambda c: c[0]); out = []
    for t, lb in ch:
        t = max(0.0, t)
        if out and t - out[-1][0] < 10:              # YouTube pide 10 s mínimo: gana el capítulo con título de play
            if lb not in ('Primera play', 'Interludio', 'Cierre') and out[-1][1] not in ('Intro',): out[-1] = (out[-1][0], lb)
            continue
        out.append((t, lb))
    if out and p.TOTAL - out[-1][0] < 10: out.pop()
    return [(fmt(t), lb) for t, lb in out]


def cmd_info(project, p, video):
    name = os.path.basename(project); tags = song_tags(project)
    plays = [dict(t=fmt(o), titulo=cap[0], sub=(cap[1] if len(cap) > 1 else '')) for o, cap in sorted(p.captions)]
    info = dict(proyecto=name, video=video, duracion=fmt(p.TOTAL), tema=getattr(p, 'SONG_TITLE', ''),
                artista=tags.get('artist', ''), titulo_tag=tags.get('title', ''), kills=len(p.kills),
                plays_con_titulo=plays, capitulos=chapters(p), canal='WAKO TV', twitch='https://twitch.tv/el_wako')
    d = os.path.join(project, 'publish'); os.makedirs(d, exist_ok=True)
    out = os.path.join(d, 'info.json'); json.dump(info, open(out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(json.dumps(info, indent=1, ensure_ascii=False)); print('Guardado en', out)
    if len(info['capitulos']) < 3: print('Aviso: menos de 3 capítulos, YouTube no los va a mostrar.')


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    ap = argparse.ArgumentParser()
    ap.add_argument('project'); ap.add_argument('cmd', choices=['frames', 'thumb', 'info'])
    ap.add_argument('--video'); ap.add_argument('--frame', type=int, default=0)
    ap.add_argument('--text', default='ACE'); ap.add_argument('--sub', default=''); ap.add_argument('--side', default='left', choices=['left', 'right'])
    ap.add_argument('--size', type=int, default=170); ap.add_argument('--zoom', type=float, default=1.0)
    a = ap.parse_args()
    project = os.path.abspath(a.project); p = load_plan(project)
    video = a.video or os.path.join(ROOT, 'output', os.path.basename(project) + '.mp4')
    if a.cmd in ('frames', 'info') and not os.path.exists(video): raise SystemExit(f'No existe {video}: renderizá primero el edit.')
    {'frames': lambda: cmd_frames(project, p, video), 'thumb': lambda: cmd_thumb(project, p, a), 'info': lambda: cmd_info(project, p, video)}[a.cmd]()


if __name__ == '__main__':
    main()
