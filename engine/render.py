import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.abspath(sys.argv[1]); ENGINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT); os.chdir(PROJECT)
sys.argv = [sys.argv[0]] + sys.argv[2:]
import cv2, numpy as np, subprocess, math
from encoders import video_encoder_args
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import project as _project
globals().update(_project.plan_globals(PROJECT))      # edit.json o plan.py: mismos nombres
import preset as _preset
ST = _preset.for_globals(globals())                    # estilo: presets/default.json <- preset del canal <- proyecto
LOOK, CH = ST['look'], ST['channel']

W, H = 1920, 1080
FD = os.path.join(ENGINE, 'assets', 'fonts') + os.sep
F800, F600, F300 = FD + 'montserrat-latin-800-normal.woff', FD + 'montserrat-latin-600-normal.woff', FD + 'montserrat-latin-300-normal.woff'
mode = sys.argv[1]
N = int(round(TOTAL * FPS))
REVEAL_MODE = 'far' if globals().get('REVEAL') else 'orbs'   # plan: REVEAL = True -> revelación en vez del negro con luces

# ---------- dispositivo: CPU o GPU, uno u otro de punta a punta ----------
# WAKO_DEVICE=cpu: numpy + OpenCV en el procesador. WAKO_DEVICE=gpu: todo el cuadro en la placa (engine/gpu.py, OpenGL).
# auto (por defecto): GPU si hay OpenGL 4.3 y ModernGL; si no, CPU. La lógica del edit es la misma en los dos modos:
# solo cambian las operaciones de imagen (bloom, zoom, desenfoques, textos, luces), que gpu.py reemplaza al final.
DEVICE = os.environ.get('WAKO_DEVICE', 'auto')
if DEVICE != 'cpu':
    try:
        import gpu as GP
        GPU_NAME = GP.init(W, H)
        DEVICE = 'gpu'
    except Exception as e:
        if DEVICE == 'gpu':
            raise SystemExit(f'WAKO_DEVICE=gpu pero no se pudo usar la GPU: {e}')
        DEVICE = 'cpu'
cv2.ocl.setUseOpenCL(False)        # modo CPU puro (sin OpenCL escondido)

class Reader:
    def __init__(s, path):
        # s.i = índice del último cuadro leído. Recién abierto es -1 (antes era -10: si el primer cuadro pedido estaba
        # en los primeros 2 s del clip se leía en orden y todo el tramo quedaba 9 cuadros = 0.15 s adelantado)
        s.path = path; s.c = cv2.VideoCapture(path); s.n = int(s.c.get(7)); s.i = -1; s.f = None
    def seek(s, idx):
        """Salto verificado: cerca del inicio de algunos clips OpenCV cae varios cuadros DESPUÉS del pedido (medido: +9,
        la imagen quedaba 0.15 s adelantada a la música y al efecto de kill). Se lee un cuadro, se pregunta dónde quedó
        y, si se pasó, se salta más atrás; si no hay forma, se reabre el clip y se lee desde el principio."""
        back = 0
        while True:
            tgt = idx - back
            if tgt <= 0:
                s.c.release(); s.c = cv2.VideoCapture(s.path); s.i = -1; s.f = None; return
            s.c.set(cv2.CAP_PROP_POS_FRAMES, tgt)
            ok, f = s.c.read()
            if not ok: s.i = idx; return
            pos = int(round(s.c.get(cv2.CAP_PROP_POS_FRAMES))) - 1
            if pos <= idx: s.f = f; s.i = pos; return
            back = 2 * back + 30
    def get(s, idx):
        idx = int(min(max(idx, 0), s.n - 1))
        if idx < s.i or idx > s.i + 120:
            s.seek(idx)
        while s.i < idx:
            ok, f = s.c.read()
            if not ok: s.i = idx; break
            s.f = f; s.i += 1
        return s.f
class HWReader:
    """Modo GPU: lee el clip con ffmpeg usando el decodificador de video de la placa (-hwaccel auto) y entrega NV12;
    el color se pasa a BGR en la GPU con la misma cuenta que OpenCV (cuadros idénticos, medido). La CPU baja de
    ~14 ms a ~3 ms por cuadro y la decodificación corre en otro proceso, en paralelo con el render.
    Salto: ffmpeg -ss (preciso: decodifica desde el keyframe y descarta hasta el cuadro pedido)."""
    def __init__(s, path):
        c = cv2.VideoCapture(path); s.n = int(c.get(7)); s.fps = c.get(5) or FPS
        s.w, s.h = int(c.get(3)), int(c.get(4)); c.release()
        s.path = path; s.fs = s.w * s.h * 3 // 2; s.p = None; s.i = -1; s.f = None
    def close(s):
        if s.p is not None:
            try: s.p.kill(); s.p.wait()
            except Exception: pass
            s.p = None
    def _open(s, idx):
        s.close()
        s.p = subprocess.Popen(['ffmpeg', '-v', 'error', '-hwaccel', 'auto', '-ss', f'{max(0.0, (idx - 0.5) / s.fps):.6f}',
                                '-i', s.path, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'nv12', '-'],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=s.fs * 2)
        s.i = idx - 1
    def get(s, idx):
        idx = int(min(max(idx, 0), s.n - 1))
        if idx == s.i and s.f is not None: return s.f
        if s.p is None or idx < s.i or idx > s.i + 120:
            s._open(idx)
        while s.i < idx:
            b = s.p.stdout.read(s.fs)
            if len(b) < s.fs: s.i = idx; break
            s.f = GP.NV12(b, s.w, s.h); s.i += 1
        return s.f
RDR = HWReader if DEVICE == 'gpu' and os.environ.get('WAKO_HWDEC', '1') != '0' else Reader
class LazyRD(dict):
    """Lectores abiertos por (clip, ranura). En modo GPU cada uno es un proceso de ffmpeg: se cierran los que no se
    usan hace rato (quedan como mucho 6 abiertos)."""
    MAX = 6
    def __init__(self): super().__init__(); self.used = {}; self.tick = 0
    def __missing__(self, key):
        if RDR is HWReader and len(self) >= self.MAX:
            old = min(self, key=lambda k: self.used.get(k, 0)); self.pop(old).close()
        r = RDR(f'clips/c{key[0]}.mp4'); self[key] = r; return r
    def __getitem__(self, key):
        self.tick += 1; self.used[key] = self.tick
        return super().__getitem__(key)
RD = LazyRD()
SLOWS = {c: (RDR(p), t0) for c, (p, t0) in SLOWMO_SRC.items()}
# Exposición pareja entre clips (look.auto_exposure, apagado por defecto): cada clip se lleva hacia un brillo medio común,
# así un clip oscuro (Nuke, Ancient) no queda apagado al lado de uno al sol. 1 = iguala del todo; el ajuste nunca pasa de ±25 %.
AUTO_EXP = float(LOOK.get('auto_exposure') or 0.0)
_CLIP_GAIN = {}
def clip_gain(c):
    if c not in _CLIP_GAIN:
        cap = cv2.VideoCapture(f'clips/c{c}.mp4'); n = int(cap.get(7)); vals = []
        for i in np.linspace(n * 0.15, n * 0.85, 7).astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(i)); ok, fr = cap.read()
            if ok: vals.append(float(cv2.cvtColor(cv2.resize(fr, (160, 90)), cv2.COLOR_BGR2GRAY).mean()))
        cap.release()
        m = float(np.median(vals)) if vals else 105.0
        _CLIP_GAIN[c] = float(min(1.25, max(0.8, (105.0 / max(1.0, m)) ** AUTO_EXP)))
    return _CLIP_GAIN[c]
def frame(seg, t, slot=0):
    return RD[(seg['clip'], slot)].get(round((seg['s0'] + (t - seg['o0'])) * FPS))

# ---------- look ----------
def mk_lut():
    x = np.arange(256) / 255.0
    sc = 1 / (1 + np.exp(-(x - 0.5) * 5.5)); sc = (sc - sc.min()) / (sc.max() - sc.min())
    base = LOOK['contrast'] * sc + (1 - LOOK['contrast']) * x
    b = np.clip(base + 0.04 * (1 - x) ** 2.2 - 0.02 * x ** 2, 0, 1)
    g = np.clip(base + 0.008 * (1 - x) ** 2, 0, 1)
    r = np.clip(base + 0.03 * x ** 1.4 - 0.012 * (1 - x) ** 2, 0, 1)
    return np.stack([(c * 255).astype(np.uint8) for c in (b, g, r)], 1).reshape(256, 1, 3)
LUT = mk_lut()
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
RR = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
VIGN = np.clip(1 - LOOK['vignette'] * np.clip(RR - 0.6, 0, None) ** 1.5, 0, 1)[..., None].astype(np.float32)
DIST = np.sqrt((xx - W / 2) ** 2 + (yy - H / 2) ** 2)


# ayudas que usan los dos modos (gpu.py tiene su versión)
clip = np.clip
def chmean(f): return f.mean(axis=2, keepdims=True)
def zeros(): return np.zeros((H, W, 3), np.float32)
def center_mean(f): h_, w_ = f.shape[:2]; return float(f[h_ // 4:3 * h_ // 4:6, w_ // 4:3 * w_ // 4:6].mean())
def to_u8(f): return np.clip(f, 0, 255).astype(np.uint8)

def bloom(f, amount, thresh=185):
    sm = cv2.resize(f, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    hi = np.clip(sm - thresh, 0, None) * (255 / (255 - thresh))
    g = cv2.GaussianBlur(hi, (0, 0), 8) + 0.8 * cv2.GaussianBlur(hi, (0, 0), 26)
    return f + cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR) * amount
def streak(f, amount, tint):
    """anamorphic horizontal light streaks from highlights"""
    sm = cv2.resize(f, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    hi = np.clip(sm.max(axis=2, keepdims=True) - 225, 0, None) / 30
    s1 = cv2.blur(hi, (161, 1)); s1 = cv2.blur(s1, (161, 1)); s1 = cv2.GaussianBlur(s1, (0, 0), 1.5)
    s1 = s1[..., None] if s1.ndim == 2 else s1
    s1 = s1 / max(1.0, float(s1.max()) * 1.6)
    return f + cv2.resize(s1 * tint, (W, H), interpolation=cv2.INTER_LINEAR) * amount * 120
def grade(f8):
    f = cv2.LUT(f8, LUT)
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    hsv[..., 1] = cv2.convertScaleAbs(hsv[..., 1], alpha=LOOK['saturation'])
    f = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    sh = cv2.GaussianBlur(f, (0, 0), 1.2); f = cv2.addWeighted(f, 1 + LOOK['sharpen'], sh, -LOOK['sharpen'], 0)
    return bloom(f.astype(np.float32), LOOK['bloom'], LOOK['bloom_threshold']) * VIGN

def affine(f, s, cx, cy, dx=0.0, dy=0.0, clamp=True):
    if clamp:
        hw, hh = W / (2 * s), H / (2 * s); cx = min(max(cx, hw), W - hw); cy = min(max(cy, hh), H - hh)
    if abs(s - 1) < 1e-4 and abs(cx - W / 2) < .5 and abs(cy - H / 2) < .5 and dx == 0 and dy == 0: return f
    M = np.float32([[s, 0, W / 2 - s * cx + dx], [0, s, H / 2 - s * cy + dy]])
    return cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
def zoom(f, z, dx=0, dy=0): return affine(f, z, W / 2, H / 2, dx, dy, clamp=False)
def shrink(f, z, ang=0.0):
    """El cuadro achicado al centro (z < 1) y apenas girado (grados) sobre negro: la play "vista de lejos"."""
    if z >= 0.9999 and abs(ang) < 1e-3: return f
    M = cv2.getRotationMatrix2D((W / 2, H / 2), ang, z)
    return cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
def reveal(f, r):
    """Revelación antes del drop (REVEAL = True en el plan): la play aparece chica, oscura y casi sin color y se acerca e
    ilumina hasta llenar la pantalla justo en el drop (r = 1), donde cae su primera kill. Siempre en movimiento (pedido
    del 20/11/2026: quieta al aparecer se veía tosca): sale del negro con un fundido corto ya acercándose, acelera hacia
    el drop y se endereza de un giro leve."""
    r = min(max(r, 0.0), 1.0); k = ss(r)
    z = 0.38 + 0.62 * (0.5 * r + 0.5 * r ** 2.4)        # velocidad desde el primer cuadro, acelera hacia el drop
    f = shrink(f, z, 2.5 * (1 - r) ** 2)
    mean = chmean(f); f = mean + (f - mean) * (0.35 + 0.65 * k)
    return f * (ss(r / 0.12) * (0.2 + 0.8 * k ** 1.3))  # fundido de ~0.5 s desde el negro
def shift(f, dx):
    M = np.float32([[1, 0, dx], [0, 1, 0]])
    return cv2.warpAffine(f, M, (W, H), borderMode=cv2.BORDER_REFLECT)
def hblur(f, L):
    L = int(L)
    if L < 3: return f
    return cv2.blur(f, (L, 1), borderType=cv2.BORDER_REFLECT)
def radial_blur(f, strength, n=5):
    if strength < 0.004: return f
    acc = f.copy()
    for i in range(1, n): acc += zoom(f, 1 + strength * i / (n - 1))
    return acc / n
def rgb_split(f, px):
    if px < 0.6: return f
    o = f.copy()
    o[..., 2] = cv2.warpAffine(f[..., 2], np.float32([[1, 0, px], [0, 1, 0]]), (W, H), borderMode=cv2.BORDER_REFLECT)
    o[..., 0] = cv2.warpAffine(f[..., 0], np.float32([[1, 0, -px], [0, 1, 0]]), (W, H), borderMode=cv2.BORDER_REFLECT)
    return o
def ss(x): x = min(max(x, 0), 1); return x * x * (3 - 2 * x)
def eio(x): x = min(max(x, 0), 1); return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def eo(x): x = min(max(x, 0), 1); return 1 - (1 - x) ** 3
def leak(px, inten=1.0, col=(150, 205, 255)):
    d = np.sqrt(((xx - px * W) / (W * 0.45)) ** 2 + ((yy - H * 0.45) / (H * 0.9)) ** 2)
    return np.exp(-d ** 2 * 2.2)[..., None] * inten * np.array(col, np.float32)
def ring(f, te, dur=0.45, strength=1.0, col=(255, 240, 225)):
    if te < 0 or te > dur: return f
    x = te / dur; rad = 60 + 1000 * eo(x); th = 22 * (1 - x) + 3
    a = np.exp(-((DIST - rad) / th) ** 2)[..., None] * (1 - x) * 0.55 * strength
    f[:] = f * (1 - a) + np.array(col, np.float32) * a
    return f

# ---------- text helpers ----------
def text_mask(txt, font, track=0, pad=60):
    w = int(sum(font.getlength(ch) for ch in txt) + track * max(0, len(txt) - 1)) + 2 * pad
    asc, desc = font.getmetrics(); h = asc + desc + 2 * pad
    m = Image.new('L', (w, h), 0); d = ImageDraw.Draw(m); x = pad
    for ch in txt: d.text((x, pad), ch, font=font, fill=255); x += font.getlength(ch) + track
    a = np.array(m).astype(np.float32) / 255
    g1 = np.array(m.filter(ImageFilter.GaussianBlur(10))).astype(np.float32) / 255
    g2 = np.array(m.filter(ImageFilter.GaussianBlur(34))).astype(np.float32) / 255
    return a[..., None], g1[..., None], g2[..., None]
def blit(f, a, cx, cy, col, al, scale=1.0):
    if al <= 0.002: return
    if abs(scale - 1) > 1e-3: a = cv2.resize(a, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR); a = a[..., None] if a.ndim == 2 else a
    h, w = a.shape[:2]; x0, y0 = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if xa >= xb or ya >= yb: return
    f[ya:yb, xa:xb] += a[ya - y0:yb - y0, xa - x0:xb - x0] * np.array(col, np.float32) * al
def darken(f, a, cx, cy, al, scale=1.0):
    if al <= 0.002: return
    if abs(scale - 1) > 1e-3: a = cv2.resize(a, None, fx=scale, fy=scale); a = a[..., None] if a.ndim == 2 else a
    h, w = a.shape[:2]; x0, y0 = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if xa >= xb or ya >= yb: return
    f[ya:yb, xa:xb] *= 1 - np.clip(a[ya - y0:yb - y0, xa - x0:xb - x0] * 1.6, 0, 1) * al

# captions bottom-centre
def cap_sprite(big, small):
    return (text_mask(big, ImageFont.truetype(F800, ST['captions']['size']), 10),
            (text_mask(small, ImageFont.truetype(F300, ST['captions']['sub_size']), 8) if small else None))
CAPS = [(o, cap_sprite(b, s)) for o, (b, s) in captions]
def draw_cap(f, spr, te, cy=H - ST['captions']['from_bottom']):
    dur = ST['captions']['duration']
    if te < 0 or te > dur: return
    al = ss(te / 0.2) * (1 - ss((te - dur + 0.35) / 0.35)); dy = 10 * (1 - ss(te / 0.4))
    (a, g1, g2), sub = spr
    darken(f, g2, W / 2, cy + dy, 0.45 * al)
    blit(f, g1, W / 2, cy + dy, (255, 225, 190), 0.3 * al); blit(f, a, W / 2, cy + dy, (255, 255, 255), al)
    if sub:
        a2, g21, _ = sub; blit(f, a2, W / 2, cy + 52 + dy, (235, 235, 235), al)

# ---------- logo intro ----------
# logo.png del proyecto > logo del preset > logo genérico del motor
LG = cv2.imdecode(np.fromfile(_preset.logo_path(ST, PROJECT), np.uint8), cv2.IMREAD_COLOR); LR = 175
LG = cv2.resize(LG, (2 * LR, 2 * LR), interpolation=cv2.INTER_AREA).astype(np.float32)
ly, lx = np.mgrid[0:2 * LR, 0:2 * LR].astype(np.float32); ld = np.sqrt((lx - LR + .5) ** 2 + (ly - LR + .5) ** 2)
LMASK = np.clip(LR - ld, 0, 1)[..., None]
LOGO_C = (W / 2, 400)
ANG = np.arctan2(yy - LOGO_C[1], xx - LOGO_C[0]); DL = np.sqrt((xx - LOGO_C[0]) ** 2 + (yy - LOGO_C[1]) ** 2)
RING_BAND = np.exp(-((DL - (LR + 14)) / 7.0) ** 2)[..., None]
RING_GLOW = np.exp(-((DL - (LR + 14)) / 38.0) ** 2)[..., None]
TV = text_mask(CH['name'].upper(), ImageFont.truetype(F800, 104), 18)
SUBT = text_mask(SONG_TITLE, ImageFont.truetype(F600, 34), 16)
SUB2 = text_mask(CH['tagline'], ImageFont.truetype(F300, 22), 6)
RING_COLS = [np.array(_preset.bgr(c), np.float32) for c in ST['colors']['ring']]
def grad_col(theta):
    """purple -> magenta -> cyan gradient around the ring (BGR)"""
    u = (np.sin(theta) * 0.5 + 0.5)
    c1, c2, c3 = RING_COLS
    return np.where(u[..., None] < 0.5, c1 + (c2 - c1) * (u[..., None] * 2), c2 + (c3 - c2) * ((u[..., None] - 0.5) * 2))
def logo_ring(f, t, sweep, pulse):
    rel = (ANG + math.pi / 2) % (2 * math.pi)
    on = (rel <= sweep).astype(np.float32)[..., None]
    col = grad_col(ANG + t * 1.6)
    return f + (RING_BAND * on * col * 1.0 + RING_GLOW * on * col * (0.35 + 0.35 * pulse))
LG_M = LG * LMASK
def paste_avatar(f, sc, al):
    img = LG_M
    if abs(sc - 1) > 1e-3:
        img = cv2.resize(img, None, fx=sc, fy=sc, interpolation=cv2.INTER_LINEAR)
    h, w = img.shape[:2]; x0, y0 = int(LOGO_C[0] - w / 2), int(LOGO_C[1] - h / 2)
    m = cv2.resize(LMASK, (w, h))[..., None]
    f[y0:y0 + h, x0:x0 + w] = f[y0:y0 + h, x0:x0 + w] * (1 - m * al) + img * al
    return f
LOGO_HITS = None
def logo(t):
    global LOGO_HITS
    if LOGO_HITS is None: LOGO_HITS = [o for o, i in out_hits(0, segments[0]['o1'] + 0.01)]
    L = segments[0]['o1']
    f = zeros()
    pulse = max([math.exp(-(t - o) / 0.18) for o in LOGO_HITS if 0 <= t - o < 0.8] + [0])
    # soft background light
    f = f + leak(0.5 + 0.08 * math.sin(t * 1.3), 0.10 + 0.05 * pulse, (180, 60, 140))
    # ring: sweep in, rotate gradient
    f = logo_ring(f, t, eio(t / 1.0) * 2 * math.pi, pulse)
    # avatar
    al = ss((t - 0.25) / 0.5); sc = 0.88 + 0.12 * eo((t - 0.25) / 0.7)
    if al > 0: f = paste_avatar(f, sc, al)
    # texts
    a, g1, g2 = TV; ta = ss((t - 0.75) / 0.45); dy = 18 * (1 - eo((t - 0.75) / 0.6))
    blit(f, g2, W / 2, 660 + dy, (255, 80, 170), 0.55 * ta * (0.8 + 0.4 * pulse)); blit(f, g1, W / 2, 660 + dy, (255, 200, 235), 0.35 * ta); blit(f, a, W / 2, 660 + dy, (255, 255, 255), ta)
    a, g1, g2 = SUBT; ta = ss((t - 1.15) / 0.45); dy = 12 * (1 - eo((t - 1.15) / 0.6))
    blit(f, g1, W / 2, 762 + dy, (255, 210, 120), 0.4 * ta); blit(f, a, W / 2, 762 + dy, (240, 240, 240), ta)
    a, g1, g2 = SUB2; ta = ss((t - 1.45) / 0.45)
    blit(f, a, W / 2, 812, (200, 200, 200), ta)
    if t < 0.35: f = f * (t / 0.35)
    # exit: glow burst into the play
    if t > L - 0.4:
        k = ss((t - (L - 0.4)) / 0.4); f = bloom(f, 2.5 * k, 60) + 255 * 0.85 * k ** 2
    return f

# ---------- interlude lights + words ----------
inter_hits = [o for o, i in out_hits(INTER[0], O_DROP2 + 0.01)]
rng_orbs = np.random.default_rng(9); ORBS = []
for o in inter_hits:
    for _ in range(4):
        ORBS.append(dict(t=o, x=rng_orbs.uniform(0.08, 0.92) * W, y=rng_orbs.uniform(0.12, 0.88) * H, r=rng_orbs.uniform(50, 190),
                         col=np.array([rng_orbs.uniform(150, 255), rng_orbs.uniform(190, 240), 255], np.float32) if rng_orbs.random() < .6 else np.array([255, 220, 170], np.float32),
                         vx=rng_orbs.uniform(-60, 60), vy=rng_orbs.uniform(-40, -10)))
def orbs(t):
    sm = np.zeros((H // 4, W // 4, 3), np.float32)
    for ob in ORBS:
        te = t - ob['t']
        if te < 0 or te > 1.2: continue
        al = math.exp(-te / 0.35) * min(1, te / 0.03)
        cx = (ob['x'] + ob['vx'] * te) / 4; cy = (ob['y'] + ob['vy'] * te) / 4; r = ob['r'] / 4 * (1 + 0.4 * te)
        cv2.circle(sm, (int(cx), int(cy)), int(r), (ob['col'] * al).tolist(), -1, lineType=cv2.LINE_AA)
    sm = cv2.GaussianBlur(sm, (0, 0), 6) * 0.5 + cv2.GaussianBlur(sm, (0, 0), 18) * 0.4
    return cv2.resize(sm, (W, H))
def beat_pulse(t):
    return max([math.exp(-(t - o) / 0.12) for o in inter_hits if 0 <= t - o < 0.5] + [0])
WFONT = ImageFont.truetype(F800, 118)
LINES = {}
for o, w, l in WORDS: LINES.setdefault(l, []).append((o, w))
WSPR = {w: text_mask(w, WFONT, 14) for o, w, l in WORDS}
SPACE = 46
LAYOUT = {}
for l, items in LINES.items():
    widths = [WSPR[w][0].shape[1] - 120 for o, w in items]
    tot = sum(widths) + SPACE * (len(items) - 1); x = W / 2 - tot / 2
    for (o, w), wd in zip(items, widths):
        LAYOUT[w] = (x + wd / 2, 375 + l * 150); x += wd + SPACE
def draw_words(f, t, translucent):
    pulse = beat_pulse(t)
    for k, (o, w, l) in enumerate(WORDS):
        te = t - o
        if te < 0: continue
        a, g1, g2 = WSPR[w]; cx, cy = LAYOUT[w]
        al = ss(te / 0.22)
        dy = 30 * (1 - eo(te / 0.5)) + 5 * math.sin(2 * math.pi * (t * 0.45 + k * 0.17))
        dx = 3 * math.sin(2 * math.pi * (t * 0.3 + k * 0.29))
        sc = 1.0
        v0 = VANISH[0] + 0.035 * k; vt = (t - v0) / (VANISH[1] - VANISH[0])
        if vt > 0:
            al *= 1 - ss(vt); sc = 1 + 0.25 * eo(vt); dy -= 30 * eo(vt)
        if al <= 0.003: continue
        base = 0.82 if translucent else 1.0
        darken(f, g2, cx + dx, cy + dy, 0.5 * al * translucent, sc)
        blit(f, g2, cx + dx, cy + dy, (255, 170, 120), al * (0.35 + 0.45 * pulse), sc)
        blit(f, g1, cx + dx, cy + dy, (255, 235, 215), al * (0.35 + 0.35 * pulse), sc)
        blit(f, a, cx + dx, cy + dy, (255, 255, 255), al * base, sc)
def build_layout(words):
    sp = {w: text_mask(w, WFONT, 14) for o, w, l in words}
    lines = {}
    for o, w, l in words: lines.setdefault(l, []).append((o, w))
    lay = {}; nl = len(lines)
    for l, items in lines.items():
        widths = [sp[w][0].shape[1] - 120 for o, w in items]
        tot = sum(widths) + SPACE * (len(items) - 1); x = W / 2 - tot / 2
        for (o, w), wd in zip(items, widths):
            lay[w] = (x + wd / 2, H / 2 - 75 * (nl - 1) + l * 150 - 40); x += wd + SPACE
    return sp, lay
for p in PHRASES: p['sp'], p['lay'] = build_layout(p['words'])
def draw_phrase(f, t, p):
    if t < p['start'] or t > p['vanish'][1] + 0.2: return f
    dim = ss((t - p['start']) / 0.4) * (1 - ss((t - p['vanish'][0]) / (p['vanish'][1] - p['vanish'][0])))
    f = f * (1 - 0.38 * dim)
    pulse = max([math.exp(-(t - o) / 0.12) for o, w, l in p['words'] if 0 <= t - o < 0.5] + [0])
    for k, (o, w, l) in enumerate(p['words']):
        te = t - o
        if te < 0: continue
        a, g1, g2 = p['sp'][w]; cx, cy = p['lay'][w]
        al = ss(te / 0.22); dy = 30 * (1 - eo(te / 0.5)) + 5 * math.sin(2 * math.pi * (t * 0.45 + k * 0.17)); sc = 1.0
        vt = (t - (p['vanish'][0] + 0.035 * k)) / (p['vanish'][1] - p['vanish'][0])
        if vt > 0: al *= 1 - ss(vt); sc = 1 + 0.25 * eo(vt); dy -= 30 * eo(vt)
        if al <= 0.003: continue
        darken(f, g2, cx, cy + dy, 0.45 * al, sc)
        blit(f, g2, cx, cy + dy, (255, 170, 120), al * (0.35 + 0.45 * pulse), sc)
        blit(f, g1, cx, cy + dy, (255, 235, 215), al * (0.35 + 0.35 * pulse), sc)
        blit(f, a, cx, cy + dy, (255, 255, 255), al * 0.9, sc)
    return f
def interlude(t):
    f = orbs(t)
    if t - INTER[0] < 0.3: f = f * ((t - INTER[0]) / 0.3)
    return f

# ---------- outro ----------
OUT1 = text_mask(CH['outro_text'].upper(), ImageFont.truetype(F800, 70), 10)
DOT = text_mask('.', ImageFont.truetype(F800, 70), 0)
OUT2 = text_mask(CH['link'], ImageFont.truetype(F600, 32), 6)
out_hits_o = [o for o, i in out_hits(OUTRO0, TOTAL)]
def outro(t):
    te = t - OUTRO0; f = zeros()
    pulse = max([math.exp(-(t - o) / 0.2) for o in out_hits_o if 0 <= t - o < 0.8] + [0])
    end_fade = 1 - ss((te - (OUTRO_LEN - 1.3)) / 1.1)
    f = f + leak(0.5, (0.08 + 0.05 * pulse) * end_fade, (200, 90, 150))
    a, g1, g2 = OUT1; al = ss((te - 0.3) / 0.6) * end_fade; dy = 14 * (1 - eo((te - 0.3) / 0.9))
    w1 = a.shape[1] - 120
    blit(f, g2, W / 2, H / 2 - 20 + dy, (255, 90, 180), al * (0.4 + 0.3 * pulse)); blit(f, g1, W / 2, H / 2 - 20 + dy, (255, 215, 240), 0.3 * al); blit(f, a, W / 2, H / 2 - 20 + dy, (255, 255, 255), al)
    da, dg1, dg2 = DOT
    for k in range(3):
        ak = ss((te - 1.1 - 0.45 * k) / 0.25) * end_fade
        x = W / 2 + w1 / 2 + 22 + k * 30
        blit(f, dg1, x, H / 2 - 20 + dy, (255, 215, 240), 0.4 * ak); blit(f, da, x, H / 2 - 20 + dy, (255, 255, 255), ak)
    a, g1, g2 = OUT2; al = ss((te - 2.2) / 0.5) * end_fade
    blit(f, a, W / 2, H / 2 + 62, (230, 215, 245), al)
    return f

# ---------- segment frames ----------
def cam_center(clip): x0, y0, x1, y1 = CAM[clip]; return (x0 + x1) / 2, (y0 + y1) / 2
FACE_Z = ST['camera']['open_zoom']
def slow_src(seg, t):
    a, b = seg['s0'], seg['s1']; D = seg['o1'] - seg['o0']; u = t - seg['o0']
    vmin = (b - a - 0.12) / (D - 0.12)
    return a + vmin * u + (1 - vmin) * 0.12 * (1 - math.exp(-u / 0.12))
def seg_frame(seg, t, slot=0):
    k = seg['kind']
    if k == 'logo': return logo(t)
    if k == 'interlude': return interlude(t)
    if k == 'outro': return outro(t)
    if k == 'slowmo':
        src = slow_src(seg, t); rd, t0_ = SLOWS[seg['clip']]; f = grade(rd.get(round((src - t0_) * 240)))
        u = (t - seg['o0']) / (seg['o1'] - seg['o0'])
        f = zoom(f, 1 + 0.06 * eio(u))
        mean = chmean(f); f = mean + (f - mean) * (1 - 0.35 * ss(u / 0.4))   # slight desaturation
        return f * (1 - 0.15 * ss(u / 0.4))
    f = grade(frame(seg, t, slot))
    if AUTO_EXP and seg['clip']:
        g_ = clip_gain(seg['clip'])
        if abs(g_ - 1) > 0.01: f = f * g_
    if k == 'zoom_out':
        x = eio((t - seg['o0']) / 1.1); s = FACE_Z ** (1 - x); cx, cy = cam_center(OPEN_CLIP)
        f = affine(f, s, cx + (W / 2 - cx) * x, cy + (H / 2 - cy) * x)
        if 0 < x < 1: f = radial_blur(f, 0.035 * math.sin(math.pi * x))
        te = t - seg['o0']
        if te < 0.45: f = f + (255 - f) * 0.85 * (1 - ss(te / 0.45))      # arrive out of the logo's glow
    elif k == 'face_out':
        x = eio((t - seg['o0'] - 0.5) / 1.5); s = ST['camera']['close_zoom'] ** x; cx, cy = cam_center(END_CLIP)
        f = affine(f, s, W / 2 + (cx - W / 2) * x, H / 2 + (cy - H / 2) * x)
        f = f * (1 - ss((t - (seg['o1'] - 1.3)) / 1.3))
    if seg['play'] == 100 and t < O_DROP2:
        if REVEAL_MODE == 'far':                      # la play se acerca y se ilumina hasta el drop
            f = reveal(f, (t - INTER[0]) / max(1e-6, O_DROP2 - INTER[0]))
        else:                                         # (viejo) sale del negro con luces
            r = ss((t - REV0) / (O_DROP2 - REV0 - 0.25))
            f = f * (0.12 + 0.88 * r) * r ** 0.6 + orbs(t) * (1 - r)
    return f

def seg_index(t):
    for i, s in enumerate(segments):
        if s['o0'] <= t < s['o1']: return i
    return len(segments) - 1
TW = dict(ST['transitions']['durations'])
TI = float(ST['transitions']['intensity'])       # fuerza de las transiciones (1 = la de siempre)
KI_BASE = float(ST['kill_fx']['intensity'])      # fuerza de los efectos de kill
KDECAY = float(ST['kill_fx']['decay'])
KFOLLOW = float(ST['kill_fx']['energy_follow'])  # 0 = todos los efectos igual; 1 = mitad de fuerza en lo calmo, 1.5 en lo más alto
KENERGY = globals().get('KILL_ENERGY') if KFOLLOW else None
SH = np.random.default_rng(5).normal(0, 1, (N + 10, 2))
ACE_TINTS = [_preset.bgr(c) for c in ST['kill_fx']['ace_tints']]
ace_idx = {i: j for j, i in enumerate([i for i, (k, c) in enumerate(zip(kills, kill_play)) if c == ACE_CLIP])}

def render_f(n):
    """Cuadro n terminado en float (numpy en CPU, G en GPU)."""
    t = n / FPS
    S = segments[seg_index(t)]; f = None
    for ob, typ, bi in boundaries:
        if typ in TW and abs(t - ob) < TW[typ]:
            w = TW[typ]; p = (t - (ob - w)) / (2 * w)
            A = seg_frame(segments[bi - 1], t, 0); B = seg_frame(segments[bi], t, 1)
            if typ.startswith('whip'):
                d = 1 if typ in ('whip_lr', 'whip_short') else -1
                amp = W * (0.55 if typ != 'whip_short' else 0.35); bl = (240 if typ != 'whip_short' else 150) * math.sin(math.pi * p) * TI
                Ab = hblur(shift(A, d * amp * eio(p)), bl); Bb = hblur(shift(B, -d * amp * (1 - eio(p))), bl)
                m = ss((p - 0.35) / 0.3); f = (Ab * (1 - m) + Bb * m) * (1 + 0.12 * math.sin(math.pi * p))
            elif typ.startswith('light'):
                k = math.sin(math.pi * p) * TI; m = ss((p - 0.4) / 0.2)
                f = bloom(A * (1 - m) + B * m, 1.15 * k, 140) + leak(-0.2 + 1.4 * p, 0.5 * k)
                f = f + (255 - clip(f, 0, 255)) * 0.08 * k
            elif typ == 'mega':
                # exaggerated full-screen hit: punch-in + chroma + streak burst on A, white flash peak, B explodes out of light
                k = math.sin(math.pi * p) * TI; m = ss((p - 0.45) / 0.1)
                Az = radial_blur(zoom(A, 1 + 0.6 * eio(p / 0.5)), 0.22 * k, n=7)
                Bz = radial_blur(zoom(B, 1 + 0.45 * (1 - eio((p - 0.5) / 0.5))), 0.22 * k, n=7)
                f = Az * (1 - m) + Bz * m
                f = rgb_split(f, 24 * k)
                f = streak(f, 0.8 * k, np.array([1.0, 0.85, 0.75], np.float32))
                f = bloom(f, 0.5 * k, 190) + leak(1.2 - 1.4 * p, 0.25 * k, (255, 200, 240)) + leak(-0.2 + 1.4 * p, 0.2 * k)
                f = f + (255 - clip(f, 0, 255)) * 0.85 * max(0, 1 - abs(p - 0.5) / 0.07)
            elif typ == 'zoom':
                m = ss((p - 0.4) / 0.2)
                Az = radial_blur(zoom(A, 1 + 0.35 * eio(p)), 0.16 * math.sin(math.pi * p) * TI)
                Bz = radial_blur(zoom(B, 1 + 0.25 * (1 - eio(p))), 0.16 * math.sin(math.pi * p) * TI)
                f = Az * (1 - m) + Bz * m
            break
    if f is None:
        f = seg_frame(S, t, 0)
        for ob, typ, bi in boundaries:
            if typ == 'black_in' and ob - 1.4 <= t < ob:
                k = ss((t - ob + 1.4) / 1.4)
                f = bloom(zoom(f, 1 + 0.04 * k), 0.6 * math.sin(math.pi * k), 150) * (1 - k) ** 1.3

    # kill effects
    z, dx, dy, split, white, bl, rad, db, pop, stk = 1.0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    stint = np.array([1, 1, 1], np.float32); lk = None; rings = []
    for ki, ko in enumerate(kills):
        te = t - ko
        if te < -0.017 or te > 0.7: continue
        att = min(1.0, (te + 0.017) / 0.05)          # entrada en ~3 cuadros: sin saltos de un cuadro al otro (los "tirones")
        te = max(te, 0); e = att * math.exp(-te / KDECAY)
        shx = math.sin(2 * math.pi * 11 * te + ki); shy = math.cos(2 * math.pi * 9 * te + 2 * ki)   # sacudida suave, no ruido por cuadro
        if kill_flash[ki] == 'burst':                # ráfagas: casi sin efecto, que se vea la kill
            white += 0.07 * att * math.exp(-te / 0.05); z += 0.015 * e
            continue
        if kill_flash[ki] == 'bang':
            z += 0.06 * e; split += 8 * e; white += 0.10 * att * math.exp(-te / 0.04); dx += 5 * e * shx; dy += 5 * e * shy
            continue
        if kill_flash[ki]:
            # 'flashing light' highlight for special shots
            white += att * 0.22 * math.exp(-te / 0.06); bl += 0.5 * e; z += 0.06 * e
            stk += 0.55 * math.exp(-te / 0.14); stint = np.array([1.0, 0.92, 0.82], np.float32)
            lk = (0.5, 0.28 * math.exp(-te / 0.2), (200, 225, 255)); rings.append((te, 0.5, 1.0, (255, 245, 230)))
            continue
        if ki in ace_idx and ace_idx[ki] not in (0, len(ace_idx) - 1):
            j = ace_idx[ki]; tint = np.array(ACE_TINTS[j], np.float32)
            white += att * 0.20 * math.exp(-te / 0.05); bl += 0.6 * e; z += 0.03 * e
            stk += 0.35 * math.exp(-te / 0.12); stint = tint / 255
            continue
        if ki in ace_idx:
            j = ace_idx[ki]; last = j == len(ace_idx) - 1; g = 1.0 + 0.3 * last
            # golpe fuerte normalizado por el brillo del centro del cuadro (donde está el enemigo): en mapas claros
            # (Dust2 al sol) la luz, el destello y el bloom quemaban la imagen y la kill no se veía
            cl = center_mean(f) / 255
            ka = min(1.0, max(0.4, 1.0 - (cl - 0.45) * 3.0))
            tint = np.array(ACE_TINTS[j], np.float32)
            stk += 0.4 * g * ka * math.exp(-te / 0.16); stint = tint / 255
            bl += 0.22 * g * ka * e; z += (0.05 + 0.012 * j) * e; split += (8 + 2 * j) * e
            dx += 8 * g * e * shx; dy += 8 * g * e * shy
            white += att * (0.06 + 0.015 * j) * ka * math.exp(-te / 0.045)
            lk = (0.15 + 0.7 * ((j * 0.37) % 1), 0.30 * g * ka * math.exp(-te / 0.2), tuple(tint))
            rings.append((te, 0.5, 0.9 + 0.2 * j, tuple(tint)))
            if last: rad += 0.05 * math.exp(-te / 0.09); white += att * 0.06 * ka * math.exp(-te / 0.07); rings.append((te - 0.08, 0.6, 1.2, (255, 255, 255)))
            continue
        fx = KILL_FX[ki % len(KILL_FX)]
        if fx == 'bloom': bl += 1.0 * e; z += 0.03 * e
        elif fx == 'chroma_zoom': split += 10 * e; z += 0.06 * e
        elif fx == 'shake_blur': dx += 10 * e * shx; dy += 10 * e * shy; db += 18 * e; z += 0.025 * e
        elif fx == 'flash': white += att * 0.30 * math.exp(-te / 0.05); bl += 0.5 * e
        elif fx == 'radial_zoom': z += 0.08 * e; rad += 0.06 * math.exp(-te / 0.07)
        elif fx == 'pop': pop += e; z += 0.035 * e
    KI = KI_BASE
    if KENERGY:          # el efecto acompaña a la canción: la última kill que entró manda
        act = [ki for ki, ko in enumerate(kills) if -0.017 <= t - ko <= 0.7]
        if act: KI = KI_BASE * (1 + KFOLLOW * (KENERGY[act[-1]] - 0.5))
    if KI != 1.0:
        z = 1 + (z - 1) * KI; dx *= KI; dy *= KI; split *= KI; white *= KI; bl *= KI; rad *= KI; db *= KI; pop *= KI; stk *= KI
        if lk is not None: lk = (lk[0], lk[1] * KI, lk[2])
        rings = [(a_, b_, c_ * KI, d_) for a_, b_, c_, d_ in rings]
    if bl > 0.01: f = bloom(f, bl, 165)
    if stk > 0.01: f = streak(f, stk, stint)
    if lk is not None and lk[1] > 0.01: f = f + leak(lk[0], lk[1], lk[2])
    if pop > 0.01:
        mean = chmean(f); f = mean + (f - mean) * (1 + 0.4 * pop); f = (f - 128) * (1 + 0.12 * pop) + 128
    f = zoom(f, z, dx, dy)
    if db > 2: f = hblur(f, db)
    if rad > 0.004: f = radial_blur(f, rad)
    f = rgb_split(f, split)
    for te, dur, st, col in rings: f = ring(f, te, dur, st, col)
    if white > 0.005: f = f + (255 - clip(f, 0, 255)) * min(white, 0.8)
    # words over interlude + ace reveal
    if WORDS and WORDS[0][0] - 0.05 <= t <= VANISH[1] + 0.2:
        translucent = ss((t - REV0) / 1.0)
        draw_words(f, t, translucent)
    for p in PHRASES: f = draw_phrase(f, t, p)
    for o, spr in CAPS: draw_cap(f, spr, t - o)
    if t > TOTAL - 0.5: f = f * max(0, (TOTAL - t) / 0.5)
    return f
def render(n): return to_u8(render_f(n))

if DEVICE == 'gpu':
    # misma lógica, operaciones de imagen en la placa (engine/gpu.py)
    GP.setup(globals())
    _R = globals()
    clip, chmean, zeros, center_mean, to_u8 = GP.clip, GP.chmean, GP.zeros, GP.center_mean, GP.to_u8
    bloom, streak, grade, affine, zoom, shift = GP.bloom, GP.streak, GP.grade, GP.affine, GP.zoom, GP.shift
    shrink = GP.shrink
    hblur, radial_blur, rgb_split, leak, ring, blit, darken = GP.hblur, GP.radial_blur, GP.rgb_split, GP.leak, GP.ring, GP.blit, GP.darken
    logo_ring = lambda f, t, sweep, pulse: GP.logo_ring(f, t, sweep, pulse, _R)
    paste_avatar = lambda f, sc, al: GP.paste_avatar(f, _R, sc, al)
    orbs = lambda t: GP.orbs(t, _R)

if mode == 'raw':     # prueba: guarda cuadros a resolución completa sin comprimir (comparar CPU vs GPU)
    os.makedirs(sys.argv[3], exist_ok=True)
    for tt in sys.argv[2].split(','):
        np.save(os.path.join(sys.argv[3], f'{float(tt):07.2f}.npy'), render(int(float(tt) * FPS)))
elif mode == 'preview':
    for tt in sys.argv[2].split(','):
        os.makedirs('previews', exist_ok=True); cv2.imwrite(f'previews/pv_{float(tt):06.2f}.jpg', cv2.resize(render(int(float(tt) * FPS)), (640, 360)))
else:
    def part(a, b, out, bitrate=30, step=1):
        """Renderiza los cuadros [a, b) y los codifica directo con la calidad final (build.py los une sin recodificar).
        step=2: borrador (30 fps, 960x540, bitrate bajo): mismo look, la mitad de cuadros."""
        draft = step > 1
        w, h = (W // 2, H // 2) if draft else (W, H)
        gpu = DEVICE == 'gpu'      # en GPU el cuadro baja ya en NV12, el formato que toma el codificador
        enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'nv12' if gpu else 'bgr24',
                                '-s', f'{w}x{h}', '-r', str(FPS / step), '-i', '-',
                                *video_encoder_args('final', bitrate, src_nv12=gpu), out],
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
        for n in range(a, min(b, N), step):
            if gpu:
                f = render_f(n)
                enc.stdin.write(GP.to_nv12(GP.area2(f) if draft else f))
                continue
            fr = render(n)
            if draft: fr = cv2.resize(fr, (w, h), interpolation=cv2.INTER_AREA)
            enc.stdin.write(fr.tobytes())
        enc.stdin.close()
        if enc.wait() != 0: raise SystemExit(f'Falló ffmpeg en {out}')
    if mode == 'serve':
        # proceso que queda vivo y recibe pedazos por stdin ("a b salida bitrate paso"): carga clips, fuentes y GPU una
        # sola vez y build.py le va dando el próximo pedazo libre (reparto parejo aunque unos pedazos pesen más que otros)
        sys.stdin.reconfigure(encoding='utf-8'); sys.stdout.reconfigure(encoding='utf-8')   # rutas con acentos
        for line in sys.stdin:
            if not line.strip(): continue
            a, b, out, br, st = line.split('\t')
            part(int(a), int(b), out, int(br), int(st))
            sys.stdout.write(f'@@done\t{out}\n'); sys.stdout.flush()
    else:   # part a b salida [bitrate] [paso]
        part(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], *(int(x) for x in sys.argv[5:7]))
        print('done', sys.argv[4])
