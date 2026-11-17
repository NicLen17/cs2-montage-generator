"""Paquete para subir un edit a YouTube: cuadros candidatos para la miniatura, miniatura y datos (capítulos, plays).

    python engine/publish.py projects/<nombre> frames
        -> projects/<nombre>/publish/thumbs/cand_NN.jpg (cuadro de cada kill con título y de cada drop) + thumbs_sheet.jpg
        y reac_NN.jpg (la cara del streamer recortada de su cámara: el cierre y ~0.8 s después de cada kill) + reacciones_sheet.jpg
    python engine/publish.py projects/<nombre> thumb --frame 3 --cam 0 --text "ACE" --sub "M4A1-S" [--type todas]
        tipos: jugada (por defecto en montajes), reaccion, limpia, versus (--frame2), todas (las 3 primeras)
        -> publish/thumbnail_<tipo>.jpg (1280x720), thumbs_compare.jpg (a tamaño celular) y thumbnail.jpg (--pick)
        Ver .claude/skills/yt-publish/references/miniaturas.md (de qué canales sale cada tipo).
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


CAM_DEF = (25, 18, 490, 278)
ACCENT = {'amarillo': (255, 214, 60), 'rojo': (235, 50, 50), 'verde': (70, 220, 90), 'violeta': (190, 90, 255), 'cian': (60, 210, 255)}


def seg_at(p, t):
    return next((g for g in p.segments if g['o0'] <= t < g['o1']), None)


def cam_rect(p, clip):
    return tuple(getattr(p, 'CAM', {}).get(clip, CAM_DEF))


def reaction_moments(p):
    """(clip, tiempo en el clip, etiqueta) donde buscar la cara del streamer: el cierre con reacción primero,
    después ~0.8 s después de cada kill de las plays con título (la reacción llega tarde)."""
    out = []
    face = next((g for g in p.segments if g['kind'] == 'face_out'), None)
    if face:
        for f in (0.35, 0.6, 0.85):
            out.append((face['clip'], face['s0'] + f * (face['s1'] - face['s0']), 'cierre'))
    for t, lb in kill_moments(p):
        g = seg_at(p, t)
        if g and g['kind'] in ('play', 'zoom_out') and g.get('clip'):
            out.append((g['clip'], g['s0'] + (t - g['o0']) + 0.8, lb))
    return out


def cmd_frames(project, p, video):
    d = os.path.join(project, 'publish', 'thumbs'); os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if f.startswith(('cand_', 'reac_')): os.remove(os.path.join(d, f))
    font = ImageFont.truetype(F600, 18)
    def label(im, txt):
        dr = ImageDraw.Draw(im); dr.rectangle((0, 0, im.width, 28), fill=(0, 0, 0)); dr.text((8, 4), txt, font=font, fill=(255, 255, 0)); return im
    tiles = []
    for i, (t, lb) in enumerate(kill_moments(p)):
        f = os.path.join(d, f'cand_{i:02d}.jpg'); grab(video, t, f)
        if os.path.exists(f): tiles.append(label(Image.open(f).convert('RGB').resize((480, 270)), f'cand {i:02d}  {fmt(t)}  {lb}'))
    reacs = []
    for i, (c, st, lb) in enumerate(reaction_moments(p)):
        src = os.path.join(project, 'clips', f'c{c}.mp4')
        if not os.path.exists(src): continue
        x0, y0, x1, y1 = cam_rect(p, c); f = os.path.join(d, f'reac_{i:02d}.jpg')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{st:.3f}', '-i', src, '-frames:v', '1', '-vf', f'crop={x1 - x0}:{y1 - y0}:{x0}:{y0}', '-q:v', '2', f])
        if os.path.exists(f): reacs.append(label(Image.open(f).convert('RGB').resize((320, 180)), f'reac {i:02d} c{c} {lb}'))
    def sheet(ims, w, h, cols, name):
        rows = (len(ims) + cols - 1) // cols; s = Image.new('RGB', (w * cols, h * max(1, rows)))
        for i, im in enumerate(ims): s.paste(im, ((i % cols) * w, (i // cols) * h))
        sp = os.path.join(project, 'publish', name); s.save(sp, quality=85); return sp
    print(f'{len(tiles)} cuadros de kills -> {sheet(tiles, 480, 270, 4, "thumbs_sheet.jpg")}')
    print(f'{len(reacs)} caras del streamer -> {sheet(reacs, 320, 180, 6, "reacciones_sheet.jpg")}')
    print('Elegí un cand (la jugada) y un reac (la cara con más expresión; descartá las que tienen la cámara vacía o tapada).')


def outlined(base, txt, font, xy, fill=(255, 255, 255), stroke=8, spacing=4, angle=0, shadow=True):
    """Texto estilo miniatura de CS: blanco, contorno negro grueso, sombra, inclinación opcional. Devuelve (ancho, alto)."""
    w = int(sum(font.getlength(c) for c in txt) + spacing * max(0, len(txt) - 1) + 4 * stroke + 40)
    asc, desc = font.getmetrics(); h = asc + desc + 4 * stroke + 40
    lay = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); x = 2 * stroke + 20
    for c in txt:
        d.text((x, 2 * stroke + 20), c, font=font, fill=fill + (255,), stroke_width=stroke, stroke_fill=(0, 0, 0, 255)); x += font.getlength(c) + spacing
    if angle: lay = lay.rotate(angle, resample=Image.BICUBIC, expand=True)
    if shadow:
        sh = Image.new('RGBA', lay.size, (0, 0, 0, 0)); sh.putalpha(lay.getchannel('A').point(lambda v: int(v * 0.6)))
        base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)), (int(xy[0]) + 8, int(xy[1]) + 10))
    base.alpha_composite(lay, (int(xy[0]), int(xy[1])))
    return lay.size


def text_w(font, txt, spacing=4, stroke=8):
    return int(sum(font.getlength(c) for c in txt) + spacing * max(0, len(txt) - 1) + 4 * stroke + 40)


def pill(base, txt, font, xy, bg, fg=(0, 0, 0)):
    w = int(sum(font.getlength(c) for c in txt) + 3 * max(0, len(txt) - 1)); asc, desc = font.getmetrics()
    pad = 18; lay = Image.new('RGBA', base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    x, y = xy; d.rounded_rectangle((x, y, x + w + 2 * pad, y + asc + desc + 14), radius=14, fill=bg + (255,), outline=(0, 0, 0, 255), width=4)
    xx = x + pad
    for c in txt: d.text((xx, y + 4), c, font=font, fill=fg + (255,)); xx += font.getlength(c) + 3
    base.alpha_composite(lay)
    return w + 2 * pad


def arrow(base, spec, color=(235, 40, 40)):
    x1, y1, x2, y2 = [float(v) for v in spec.split(',')]
    lay = Image.new('RGBA', base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    ang = np.arctan2(y2 - y1, x2 - x1); L = 56
    hx, hy = x2 - L * 0.8 * np.cos(ang), y2 - L * 0.8 * np.sin(ang)
    head = [(x2, y2), (x2 - L * np.cos(ang - 0.5), y2 - L * np.sin(ang - 0.5)), (x2 - L * np.cos(ang + 0.5), y2 - L * np.sin(ang + 0.5))]
    d.line((x1, y1, hx, hy), fill=(0, 0, 0, 255), width=32); d.polygon(head, fill=(0, 0, 0, 255))
    d.line((x1, y1, hx, hy), fill=color + (255,), width=20)
    d.polygon([(x2 - 6 * np.cos(ang), y2 - 6 * np.sin(ang)), head[1], head[2]], fill=color + (255,))
    base.alpha_composite(lay)


def circle(base, spec, color=(235, 40, 40)):
    x, y, r = [float(v) for v in spec.split(',')]
    lay = Image.new('RGBA', base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    d.ellipse((x - r, y - r, x + r, y + r), outline=(0, 0, 0, 255), width=16); d.ellipse((x - r + 3, y - r + 3, x + r - 3, y + r - 3), outline=color + (255,), width=9)
    base.alpha_composite(lay)


def load_frame(project, n, W=1280, H=720, zoom=1.0, focus=None):
    src = os.path.join(project, 'publish', 'thumbs', f'cand_{n:02d}.jpg')
    if not os.path.exists(src): raise SystemExit(f'No existe {src}: corré primero "frames".')
    im = Image.open(src).convert('RGB')
    if zoom > 1:      # zoom hacia el foco; máximo 2x para no pixelar (regla de cs2-edit)
        z = min(2.0, zoom); w, h = im.size; cw, ch = w / z, h / z
        fx, fy = (focus[0] * w / W, focus[1] * h / H) if focus else (w / 2, h / 2)
        x0 = min(max(0, fx - cw / 2), w - cw); y0 = min(max(0, fy - ch / 2), h - ch)
        im = im.crop((x0, y0, x0 + cw, y0 + ch))
    im = im.resize((W, H), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.18); im = ImageEnhance.Color(im).enhance(1.3); im = ImageEnhance.Sharpness(im).enhance(1.4)
    return im.convert('RGBA')


def load_face(project, n, tight=False):
    src = os.path.join(project, 'publish', 'thumbs', f'reac_{n:02d}.jpg')
    if not os.path.exists(src): return None
    im = Image.open(src).convert('RGB')
    if tight:   # recorte centrado en la cara (detector de OpenCV); si no la encuentra, usa la cámara entera
        fc = []
        try:    # OpenCV 4.x trae el detector; en 5.x puede no estar (queda el recorte centrado de abajo)
            import cv2
            g = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
            fc = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml').detectMultiScale(g, 1.1, 4, minSize=(40, 40))
        except Exception:
            pass
        if not len(fc):     # sin detector: la cara del streamer suele estar centrada en su cámara
            fc = [(int(im.width * 0.5 - im.height * 0.22), int(im.height * 0.2), int(im.height * 0.44), int(im.height * 0.44))]
        if len(fc):
            x, y, w, h = max(fc, key=lambda r: r[2] * r[3]); cx, cy = x + w / 2, y + h / 2
            side = min(im.height, int(h * 2.4)); cw = min(im.width, int(side * 0.85))
            x0 = int(min(max(0, cx - cw / 2), im.width - cw)); y0 = int(min(max(0, cy - side * 0.45), im.height - side))
            im = im.crop((x0, y0, x0 + cw, y0 + side))
    im = ImageEnhance.Contrast(im).enhance(1.12); im = ImageEnhance.Color(im).enhance(1.15); im = ImageEnhance.Sharpness(im).enhance(1.5)
    return im


def framed(base, im, box, border=8, glow=(255, 255, 255)):
    x, y, w, h = box; im = im.resize((w, h), Image.LANCZOS).convert('RGBA')
    m = Image.new('L', (w, h), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=18, fill=255); im.putalpha(m)
    sh = Image.new('RGBA', base.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((x - border - 6, y - border - 6, x + w + border + 6, y + h + border + 6), radius=28, fill=(0, 0, 0, 200))
    base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
    fr = Image.new('RGBA', base.size, (0, 0, 0, 0)); ImageDraw.Draw(fr).rounded_rectangle((x - border, y - border, x + w + border, y + h + border), radius=24, fill=glow + (255,))
    base.alpha_composite(fr); base.alpha_composite(im, (x, y))


def shade_side(base, side, strength=190):
    W, H = base.size; g = (np.linspace(1, 0, W // 2) ** 1.3 * strength).astype(np.uint8); a = np.zeros((H, W), np.uint8)
    if side == 'left': a[:, :W // 2] = g
    else: a[:, W - W // 2:] = g[::-1]
    s = Image.new('RGBA', (W, H), (0, 0, 0, 0)); s.putalpha(Image.fromarray(a)); base.alpha_composite(s)


def logo_badge(project, base, corner):
    lp = os.path.join(project, 'logo.png') if os.path.exists(os.path.join(project, 'logo.png')) else os.path.join(ENGINE, 'assets', 'logo.png')
    R = 52; lg = Image.open(lp).convert('RGBA').resize((2 * R, 2 * R), Image.LANCZOS)
    m = Image.new('L', (2 * R, 2 * R), 0); ImageDraw.Draw(m).ellipse((0, 0, 2 * R - 1, 2 * R - 1), fill=255); lg.putalpha(m)
    W, H = base.size; x = 28 if corner == 'left' else W - 2 * R - 28; y = 26
    ring = Image.new('RGBA', base.size, (0, 0, 0, 0)); ImageDraw.Draw(ring).ellipse((x - 5, y - 5, x + 2 * R + 5, y + 2 * R + 5), outline=(200, 90, 255, 255), width=5)
    base.alpha_composite(ring); base.alpha_composite(lg, (x, y))


def make_thumb(project, p, a, kind):
    W, H = 1280, 720; acc = ACCENT.get(a.accent, ACCENT['amarillo'])
    focus = tuple(float(v) for v in a.focus.split(',')) if a.focus else None
    big = ImageFont.truetype(F800, a.size); subf = ImageFont.truetype(F800, max(38, a.size // 3))
    side = a.side
    if kind == 'jugada':        # realFURI: la jugada real + la cámara del streamer agrandada + 1-2 palabras
        base = load_frame(project, a.frame, zoom=a.zoom, focus=focus)
        shade_side(base, side, 150)
        face = load_face(project, a.cam)
        if face is not None:
            fw = 470; fh = int(fw * face.height / face.width)
            framed(base, face, (40 if side == 'left' else W - fw - 40, 40, fw, fh))
        lines = [l.strip() for l in a.text.split('|') if l.strip()]
        y = H - 70 - (a.size + 30) * len(lines) - (70 if a.sub else 0)
        for ln in lines:
            tw = text_w(big, ln); _, th = outlined(base, ln, big, (10 if side == 'left' else W - tw - 10, y), angle=a.angle); y += a.size + 30
        if a.sub:
            sw = text_w(subf, a.sub, 3, 0); pill(base, a.sub, subf, (46 if side == 'left' else W - sw - 46, y), acc)
    elif kind == 'reaccion':    # FURI actual: cara enorme de un lado, fondo de la jugada desenfocado, texto grande del otro
        base = load_frame(project, a.frame, zoom=max(a.zoom, 1.15), focus=focus).filter(ImageFilter.GaussianBlur(5))
        base.alpha_composite(Image.new('RGBA', (W, H), (0, 0, 0, 80)))
        face = load_face(project, a.cam, tight=True)
        if face is not None:
            fh = 610; fw = min(640, int(fh * face.width / face.height))
            framed(base, face, (W - fw - 44 if side == 'left' else 44, H - fh - 44, fw, fh), border=10)
        lines = [l.strip() for l in a.text.split('|') if l.strip()]
        y = (H - (a.size + 30) * len(lines) - (80 if a.sub else 0)) // 2 - 20
        x = 10 if side == 'left' else W // 2 - 20
        for ln in lines:
            outlined(base, ln, big, (x, y), angle=a.angle); y += a.size + 30
        if a.sub: pill(base, a.sub, subf, (x + 36, y + 10), acc)
    elif kind == 'limpia':      # Dareh: un solo cuadro llamativo, sin texto
        base = load_frame(project, a.frame, zoom=a.zoom if a.zoom > 1 else 1.3, focus=focus)
        r = np.sqrt(((np.arange(W) - W / 2) / (W / 2))[None, :] ** 2 + ((np.arange(H) - H / 2) / (H / 2))[:, None] ** 2)
        v = Image.new('RGBA', (W, H), (0, 0, 0, 0)); v.putalpha(Image.fromarray((np.clip(r - 0.55, 0, 1) ** 1.6 * 210).astype(np.uint8))); base.alpha_composite(v)
    elif kind == 'versus':      # realFURI comparaciones: dos cuadros en diagonal, VS, rojo pierde / verde gana
        if a.frame2 is None: raise SystemExit('versus necesita --frame y --frame2')
        A = load_frame(project, a.frame); B = load_frame(project, a.frame2)
        m = Image.new('L', (W, H), 0); ImageDraw.Draw(m).polygon([(W * 0.56, 0), (W, 0), (W, H), (W * 0.44, H)], fill=255)
        base = A.copy(); base.paste(B, (0, 0), m)
        ln = Image.new('RGBA', (W, H), (0, 0, 0, 0)); ImageDraw.Draw(ln).line((W * 0.56, 0, W * 0.44, H), fill=(255, 255, 255, 255), width=12); base.alpha_composite(ln)
        vs = ImageFont.truetype(F800, 130); outlined(base, 'VS', vs, (W / 2 - text_w(vs, 'VS', 4, 10) / 2, H / 2 - 120), fill=acc, stroke=10)
        t1, t2 = ([l.strip() for l in a.text.split('|')] + [''])[:2]
        f2 = ImageFont.truetype(F800, max(60, a.size // 2))
        outlined(base, t1, f2, (10, 10), fill=ACCENT['rojo'])
        if t2: outlined(base, t2, f2, (W - text_w(f2, t2) - 10, H - f2.size - 90), fill=ACCENT['verde'])
    else:
        raise SystemExit(f'tipo desconocido: {kind}')
    # flecha y círculo: coordenadas del cuadro de la jugada; en "limpia" nunca (sin gráficos, estilo Dareh)
    marks = kind in ('jugada', 'versus') or (kind == 'reaccion' and a.type == 'reaccion')
    if a.arrow and marks: arrow(base, a.arrow)
    if a.circle and marks: circle(base, a.circle)
    if a.logo: logo_badge(project, base, 'right' if side == 'left' else 'left')
    out = os.path.join(project, 'publish', f'thumbnail_{kind}.jpg')
    base.convert('RGB').save(out, quality=90)
    return out


def cmd_thumb(project, p, a):
    kinds = ['jugada', 'reaccion', 'limpia'] if a.type == 'todas' else [a.type]
    outs = [make_thumb(project, p, a, k) for k in kinds]
    for o in outs: print(f'Miniatura: {o}  ({os.path.getsize(o) / 1024:.0f} KB)')
    sm = [Image.open(o).resize((320, 180), Image.LANCZOS) for o in outs]      # así se ven en el celular
    cmp_ = Image.new('RGB', (330 * len(sm) + 10, 200), (24, 24, 24))
    for i, im in enumerate(sm): cmp_.paste(im, (10 + 330 * i, 10))
    cp = os.path.join(project, 'publish', 'thumbs_compare.jpg'); cmp_.save(cp, quality=90)
    pick = os.path.join(project, 'publish', f'thumbnail_{a.pick or kinds[0]}.jpg')
    if os.path.exists(pick):
        import shutil; shutil.copy(pick, os.path.join(project, 'publish', 'thumbnail.jpg'))
    print(f'Comparación a tamaño celular: {cp}\nthumbnail.jpg = {os.path.basename(pick)}')


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
        sub = cap[1] if len(cap) > 1 else ''
        maps = ('MIRAGE', 'DUST2', 'DUST 2', 'INFERNO', 'NUKE', 'ANCIENT', 'ANUBIS', 'VERTIGO', 'OVERPASS', 'TRAIN')
        ch.append((o - 0.5, f'{cap[0]} en {sub.title()}' if sub.upper() in maps else (f'{cap[0]} con {sub}' if sub else cap[0])))
    inter = next((s for s in segs if s['kind'] == 'interlude'), None)
    if inter: ch.append((inter['o0'], 'Interludio')); ch.append((inter['o1'], 'Segundo drop'))
    face = next((s for s in segs if s['kind'] == 'face_out'), None)
    if face: ch.append((face['o0'] - 3, 'Cierre'))
    ch.sort(key=lambda c: c[0]); out = []
    STRUCT = ('Primera play', 'Interludio', 'Segundo drop', 'Cierre')
    for t, lb in ch:
        t = max(0.0, t)
        if out and t - out[-1][0] < 10:              # YouTube pide 10 s mínimo entre capítulos
            pt, plb = out[-1]
            if plb in STRUCT and lb not in STRUCT and t - pt <= 4:
                out[-1] = (pt, f'{"Segundo drop" if plb == "Interludio" else plb} · {lb}')   # "Segundo drop · ACE con M4A1-S"
            elif plb in STRUCT and lb not in STRUCT and (len(out) < 2 or t - out[-2][0] >= 10):
                out[-1] = (t, lb)                                   # la play con título vale más que el rótulo genérico
            continue                                                # nunca se le pone a un minuto el nombre de otra play
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
    ap.add_argument('--type', default='todas', choices=['todas', 'jugada', 'reaccion', 'limpia', 'versus'])
    ap.add_argument('--pick', help='qué tipo copiar a thumbnail.jpg (por defecto el primero)')
    ap.add_argument('--cam', type=int, default=0, help='número de reac_NN (cara del streamer)'); ap.add_argument('--frame2', type=int)
    ap.add_argument('--text', default='ACE', help='"|" separa renglones; en versus, izquierda|derecha'); ap.add_argument('--sub', default='')
    ap.add_argument('--side', default='left', choices=['left', 'right'], help='lado del texto'); ap.add_argument('--accent', default='amarillo', choices=list(ACCENT))
    ap.add_argument('--size', type=int, default=190); ap.add_argument('--zoom', type=float, default=1.0); ap.add_argument('--focus', help='x,y en 1280x720 hacia donde hacer zoom')
    ap.add_argument('--angle', type=float, default=0, help='inclinación del texto en grados (ej. 4)')
    ap.add_argument('--arrow', help='x1,y1,x2,y2 flecha roja (1280x720)'); ap.add_argument('--circle', help='x,y,r círculo rojo (1280x720)')
    ap.add_argument('--logo', action='store_true', help='logo del canal en la esquina de arriba')
    a = ap.parse_args()
    project = os.path.abspath(a.project); p = load_plan(project)
    video = a.video or os.path.join(ROOT, 'output', os.path.basename(project) + '.mp4')
    if a.cmd in ('frames', 'info') and not os.path.exists(video): raise SystemExit(f'No existe {video}: renderizá primero el edit.')
    {'frames': lambda: cmd_frames(project, p, video), 'thumb': lambda: cmd_thumb(project, p, a), 'info': lambda: cmd_info(project, p, video)}[a.cmd]()


if __name__ == '__main__':
    main()
