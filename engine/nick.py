"""El nick del jugador en el killfeed, cuando el canal lo declara ("channel": {"player": "Wako"} en el preset; puede
ser una lista si usa varias cuentas: ["Wako", "ElWako"]).

No hay OCR: el nombre se reconoce por imagen (killfeed._find). Lo que se guarda son PLANTILLAS del nick tal como sale
en el killfeed, en catalog/nicks/<nick>/NN.png, y se reusan entre proyectos:

  1. En cada play donde un nombre se repite en las entradas rojas (killfeed.clip_name) ese nombre es candidato.
  2. El candidato se acepta como el nick si se parece al nick DIBUJADO con una fuente del sistema (parecida, no la del
     juego: alcanza para distinguir "Wako" de "El Tripas", no para leer el killfeed directamente).
  3. Las plantillas aceptadas se guardan. En los proyectos siguientes sirven aunque el clip tenga una sola entrada.

    python engine/nick.py                      -> nicks del preset y cuántas plantillas tiene cada uno
    python engine/nick.py --forget <nick>      -> borra sus plantillas (si se aprendió una mal)
"""
import os, sys, re
import numpy as np, cv2

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)
import killfeed as K

LOOKS = 0.8                      # parecido mínimo entre un nombre deducido y el nick dibujado para aceptarlo
MARGIN = 0.05                    # ...y tiene que parecerse más al nick que a cualquier otro nick por este margen
MAX_TPL = 16                     # plantillas guardadas por nick (variantes de escala de HUD, de fondo, de compresión)
FONTS = ['arialbd.ttf', 'segoeuib.ttf', 'verdanab.ttf', 'tahomabd.ttf', 'bahnschrift.ttf',
         'DejaVuSans-Bold.ttf', 'LiberationSans-Bold.ttf', 'Arial Bold.ttf', 'Helvetica.ttc']
FONT_DIRS = [os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts'), '/usr/share/fonts', '/Library/Fonts',
             '/System/Library/Fonts', os.path.expanduser('~/.fonts')]
_fonts = None


def nicks_of(preset):
    """Lista de nicks de un preset ya cargado (preset.load()): acepta texto, lista o nada."""
    p = (preset.get('channel') or {}).get('player')
    if not p: return []
    return [str(x).strip() for x in ([p] if isinstance(p, str) else p) if str(x).strip()]


def configured():
    """Nicks del preset del canal (config.json). Sin preset legible, ninguno."""
    try:
        import preset
        return nicks_of(preset.load())
    except Exception:
        return []


def _font_files():
    global _fonts
    if _fonts is None:
        _fonts = []
        for d in FONT_DIRS:
            if not os.path.isdir(d): continue
            have = {}
            for base, _, fs in os.walk(d):
                for f in fs: have.setdefault(f.lower(), os.path.join(base, f))
            _fonts += [have[f.lower()] for f in FONTS if f.lower() in have]
    return _fonts


def render(txt, font=None, size=40):
    """El texto dibujado en blanco sobre negro, recortado a sus letras."""
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(font, size) if font else ImageFont.load_default(size)
    im = Image.new('L', (size * (len(txt) + 2), size * 2), 0)
    ImageDraw.Draw(im).text((size // 2, size // 4), txt, 255, font=f)
    a = np.array(im); ys = np.flatnonzero(a.max(1) > 128); xs = np.flatnonzero(a.max(0) > 128)
    return a[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1] if len(ys) and len(xs) else None


_rendered = {}


def looks_like(tpl, nick):
    """Parecido (0-1) entre un nombre recortado del killfeed y el nick dibujado con las fuentes del sistema. La fuente
    no es la del juego: se compara a la misma altura, probando varios anchos."""
    if nick not in _rendered:
        _rendered[nick] = [r for r in (render(nick, f) for f in (_font_files() or [None])) if r is not None]
    t = cv2.GaussianBlur(tpl.astype(np.float32), (0, 0), 1.0); best = 0.0
    for r in _rendered[nick]:
        for sx in (0.85, 0.92, 1.0, 1.08, 1.15, 1.25):
            w = int(t.shape[1] * sx)
            if w < 6: continue
            rr = cv2.GaussianBlur(cv2.resize(r, (w, t.shape[0]), interpolation=cv2.INTER_AREA).astype(np.float32), (0, 0), 1.0)
            m = max(4, abs(w - t.shape[1]) + 4)
            big = cv2.copyMakeBorder(t, 2, 2, m, m, cv2.BORDER_CONSTANT)
            best = max(best, float(cv2.matchTemplate(big, rr, cv2.TM_CCOEFF_NORMED).max()))
    return best


def _dir(nick, root=ROOT):
    return os.path.join(root, 'catalog', 'nicks', re.sub(r'[^\w\-]+', '_', nick.lower()).strip('_') or 'nick')


def stored(nick, root=ROOT):
    d = _dir(nick, root)
    if not os.path.isdir(d): return []
    out = [cv2.imread(os.path.join(d, f), cv2.IMREAD_GRAYSCALE) for f in sorted(os.listdir(d)) if f.endswith('.png')]
    return [t for t in out if t is not None]


def learn(frs, nicks):
    """{nick: [plantillas]} con los nombres deducidos de las plays (un nombre repetido en sus entradas rojas) que se
    parecen a alguno de los nicks."""
    out = {n: [] for n in nicks}
    for fr in frs:
        tp, c = K.clip_name(K._live(fr), fr['fps'])
        if tp is None or c < 2: continue
        sc = sorted(((looks_like(tp, n), n) for n in nicks), reverse=True)
        if sc[0][0] >= LOOKS and (len(sc) == 1 or sc[0][0] - sc[1][0] >= MARGIN):
            out[sc[0][1]].append(tp)
    return out


def templates(nicks, frs=(), root=ROOT, save=True):
    """Plantillas de los nicks: las guardadas en catalog/nicks/ más las que se aprenden de estos clips (que quedan
    guardadas para los proyectos siguientes). Devuelve [] si no hay nicks o todavía no se aprendió ninguna."""
    if not nicks: return []
    new = learn(frs, nicks) if frs else {}
    out = []
    for n in nicks:
        have = stored(n, root); add = []
        for g in K._groups(new.get(n, []), thr=0.9):          # una por variante (escala del HUD, cuenta, compresión)
            m = K._medoid(g)
            if len(have) + len(add) < MAX_TPL and not any(K._sim(m, h) > 0.9 for h in have + add): add.append(m)
        if add and save:
            d = _dir(n, root); os.makedirs(d, exist_ok=True)
            for i, m in enumerate(add): cv2.imwrite(os.path.join(d, f'{len(have) + i:02d}.png'), m)
        out += have + add
    return out


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    a = sys.argv[1:]
    if a[:1] == ['--forget'] and len(a) > 1:
        import shutil
        shutil.rmtree(_dir(a[1]), ignore_errors=True); print('Plantillas borradas:', _dir(a[1]))
    else:
        ns = configured()
        if not ns:
            print('El preset del canal no tiene "channel": {"player": ...}: el jugador se deduce de cada play.')
        for n in ns:
            print(f'{n}: {len(stored(n))} plantilla(s) en {_dir(n)}')
