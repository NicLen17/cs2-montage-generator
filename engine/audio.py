import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import compat  # noqa: F401  (nombres viejos de las variables de entorno)
import os, sys
PROJECT = os.path.abspath(sys.argv[1]); ENGINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT); os.chdir(PROJECT)
sys.argv = [sys.argv[0]] + sys.argv[2:]
import numpy as np, subprocess, json
from scipy.signal import butter, sosfiltfilt
from scipy.ndimage import maximum_filter1d, uniform_filter1d
sys.path.insert(0, ENGINE)
import project as _project
globals().update(_project.plan_globals(PROJECT))      # edit.json o plan.py: mismos nombres
import preset as _preset
_A = _preset.for_globals(globals())['audio']           # valores de fábrica: preset del canal (presets/)
SR = 48000
# Mezcla 2 (20/11/2026, pedido del usuario: "los tiros y headshots siguen muy bajos, la música predomina demasiado").
# AUDIO_MIX = 1 en el plan vuelve a la mezcla vieja. Los valores se pueden subir desde el plan; no se bajan sin pedido.
MIX = int(os.environ.get('MONTAGE_AUDIO_MIX', globals().get('AUDIO_MIX', _A['mix'])))
GAME_GAIN = globals().get('GAME_GAIN', 0.78 if MIX == 1 else _A['game_gain'])       # juego en las plays (en el cierre: 0.40 / 0.55)
GAME_EMPH = globals().get('GAME_EMPH', 1.7 if MIX == 1 else _A['game_emph'])        # realce de cada tiro y headshot
MUSIC_DUCK = globals().get('MUSIC_DUCK', 0.42 if MIX == 1 else _A['music_duck'])    # cuánto se aparta la música en cada tiro
MUSIC_BED = globals().get('MUSIC_BED', 0.92 if MIX == 1 else _A['music_bed'])      # música debajo del gameplay (0.92 en logo, interludio, outro)
GAME_PRESENCE = globals().get('GAME_PRESENCE', _A['game_presence'])                    # realce de 2-6 kHz en todo el juego (estallido, headshot)
MUSIC_CARVE = globals().get('MUSIC_CARVE', _A['music_carve'])                        # cuánto libera la música la banda 1.2-6 kHz en cada tiro
REACT_GAIN = globals().get('REACT_GAIN', _A['react_gain'])                           # voz extra en las reacciones (se suma a la que ya trae el clip)
REACT_DUCK = globals().get('REACT_DUCK', _A['react_duck'])                          # cuánto baja la música mientras dura la reacción
REACT_HOLD = globals().get('REACT_HOLD', _A['react_hold'])                           # la música sigue baja este tiempo después del grito
REACT_RELEASE = globals().get('REACT_RELEASE', _A['react_release'])                     # y vuelve a su nivel en este tiempo (curva suave)
REACT_KINDS = globals().get('REACT_KINDS', tuple(_A['react_kinds']))                 # solo reacciones grupales (pedido del 20/11/2026)
OUT_WAV = os.environ.get('MONTAGE_AUDIO_OUT', 'work_audio.wav')
LUFS_TARGET = _A['loudness']['target_lufs']       # None: tan fuerte como deje el pico (el sonido de siempre, ~-10 LUFS)
TP_LIMIT = float(_A['loudness']['true_peak'])     # techo del pico real, en dBTP


def _lufs(x):
    """Loudness integrado (EBU R128) de una mezcla estéreo en memoria, medido con ffmpeg."""
    import re
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-f', 's16le', '-ar', str(SR), '-ac', '2', '-i', '-', '-af', 'ebur128',
                        '-f', 'null', '-'], input=(np.clip(x / max(1.0, np.abs(x).max()), -1, 1) * 32767).astype(np.int16).tobytes(),
                       capture_output=True).stderr.decode('utf-8', 'replace')
    m = re.findall(r'I:\s+(-?[\d.]+) LUFS', r)
    if not m: return None
    return float(m[-1]) + 20 * np.log10(max(1.0, np.abs(x).max()))


_DEC = {}
def decode_all(paths):
    """Decodifica varios archivos con UNA sola llamada a ffmpeg y los guarda enteros en memoria. Abrir ffmpeg cuesta
    ~0.5 s en Windows y antes se abría una vez por tramo (~50 veces, 27 de los 38 s que tardaba la mezcla)."""
    import tempfile, shutil
    paths = [p for p in dict.fromkeys(paths) if p not in _DEC and os.path.exists(p)]
    if not paths: return
    tmp = tempfile.mkdtemp(prefix='montage_audio_')
    try:
        cmd = ['ffmpeg', '-v', 'error', '-y']
        for p in paths: cmd += ['-i', p]
        for i, p in enumerate(paths):
            cmd += ['-map', f'{i}:a:0', '-f', 'f32le', '-ac', '2', '-ar', str(SR), os.path.join(tmp, f'{i}.raw')]
        if subprocess.run(cmd, capture_output=True).returncode != 0 and len(paths) > 1:
            for p in paths: decode_all([p])          # algún archivo sin audio: de a uno
            return
        for i, p in enumerate(paths):
            f = os.path.join(tmp, f'{i}.raw')
            _DEC[p] = np.fromfile(f, np.float32).reshape(-1, 2) if os.path.exists(f) else np.zeros((0, 2), np.float32)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
def dec(path, ss, t):
    if path not in _DEC: decode_all([path])
    a = _DEC.get(path, np.zeros((0, 2), np.float32)); i0 = int(round(max(ss, 0) * SR))
    return a[i0:i0 + int(round(t * SR))].astype(np.float64)
decode_all(['song.mp3'] + [f"clips/c{s['clip']}.mp4" for s in segments if s.get('clip')])


n = int(TOTAL * SR); t = np.arange(n) / SR
song = np.zeros((n, 2))
XF = int(0.025 * SR)
for k, (o0, o1, s0) in enumerate(song_map):
    o1 = min(o1, TOTAL)
    i0 = int(round(o0 * SR)); i1 = int(round(o1 * SR))
    piece = dec('song.mp3', s0, (o1 - o0) + 0.05)[: i1 - i0 + XF]
    if k > 0: piece[:XF] *= np.linspace(0, 1, XF)[:, None]
    if k < len(song_map) - 1:
        piece[i1 - i0:] *= np.linspace(1, 0, len(piece) - (i1 - i0))[:, None]
    e = min(n, i0 + len(piece)); song[i0:e] += piece[:e - i0]
fo = np.clip((TOTAL - 0.3 - t) / (TOTAL - 0.3 - (OUTRO0 - 1.5)), 0, 1) ** 1.6
song *= (np.clip(t / 0.8, 0, 1) * fo)[:, None]

TWa = {'mega': 0.30, 'whip_lr': 0.13, 'whip_rl': 0.13, 'light': 0.17, 'zoom': 0.13, 'whip_short': 0.075, 'light_short': 0.085}
ext = {}
for ob, typ, bi in boundaries:
    w = TWa.get(typ, 0.012); ext[bi] = w            # segment bi starts early by w
    ext[(bi - 1, 'end')] = w

# ---------- juego ----------
game = np.zeros((n, 2))
placed = []                                          # (i0, L, segmento, audio) de cada tramo con sonido del juego
for i, s in enumerate(segments):
    if s['kind'] in ('logo', 'interlude', 'outro'): continue
    if s['kind'] == 'slowmo':
        D = s['o1'] - s['o0']; u = np.arange(int(D * SR)) / SR; vmin = (s['s1'] - s['s0'] - 0.12) / (D - 0.12)
        src = s['s0'] + vmin * u + (1 - vmin) * 0.12 * (1 - np.exp(-u / 0.12))
        raw = dec(f"clips/c{s['clip']}.mp4", s['s0'], 1.0); p = np.clip((src - s['s0']) * SR, 0, len(raw) - 2); ii = p.astype(int); fr = (p - ii)[:, None]
        seg = raw[ii] * (1 - fr) + raw[ii + 1] * fr
        seg = sosfiltfilt(butter(2, 1200, 'low', fs=SR, output='sos'), seg, axis=0) * np.linspace(1, 0.2, len(seg))[:, None]
        i0 = int(round(s['o0'] * SR)); game[i0:i0 + len(seg)] += seg * (0.4 if MIX == 1 else 0.5); continue
    a = ext.get(i, 0.012); b = ext.get((i, 'end'), 0.012)
    o0 = s['o0'] - a; o1 = s['o1'] + b
    src0 = s['s0'] - a
    seg = dec(f"clips/c{s['clip']}.mp4", src0, o1 - o0)
    if src0 < 0: seg = np.pad(seg, ((int(-src0 * SR), 0), (0, 0)))[: len(seg)]
    i0 = int(round(o0 * SR)); L = min(len(seg), n - i0)
    seg = seg[:L].copy()
    fa, fb = int(2 * a * SR), int(2 * b * SR)
    seg[:fa] *= np.linspace(0, 1, fa)[:, None]; seg[-fb:] *= np.linspace(1, 0, fb)[:, None]
    placed.append((i0, L, s, seg))

# Mezcla 2: cada clip al mismo nivel (vienen grabados a volúmenes distintos y los más bajos quedaban tapados por la música)
cgain = {}
if MIX >= 2:
    hp = butter(2, 120, 'high', fs=SR, output='sos'); w = int(0.4 * SR)
    lv = {}
    for i0, L, s, seg in placed:
        x = sosfiltfilt(hp, seg.mean(axis=1))
        if len(x) < w: continue
        lv.setdefault(s['clip'], []).append(np.sqrt(uniform_filter1d(x ** 2, w)[w // 2::w // 2] + 1e-12))
    lvdb = {c: 20 * np.log10(np.percentile(np.concatenate(r), 90)) for c, r in lv.items()}
    ref = np.median(list(lvdb.values())) if lvdb else 0
    cgain = {c: float(np.clip(10 ** ((ref - d) / 20), 0.6, 1.8)) for c, d in lvdb.items()}
for i0, L, s, seg in placed:
    g = GAME_GAIN if s['kind'] != 'face_out' else (0.40 if MIX == 1 else 0.55)
    game[i0:i0 + L] += seg * g * cgain.get(s['clip'], 1.0)
game *= np.clip((OUTRO0 - t) / 1.5, 0, 1)[:, None]
if globals().get('REVEAL'):                          # revelación antes del drop: el juego entra a la par de la imagen
    _a, _b = int(INTER[0] * SR), int(O_DROP2 * SR)
    _x = np.arange(_b - _a) / max(1, _b - _a); game[_a:_b] *= (0.2 + 0.8 * _x * _x * (3 - 2 * _x))[:, None]
play_mask = np.zeros(n, bool)
for s in segments:
    if s['kind'] in ('play', 'zoom_out'): play_mask[int(s['o0'] * SR):int(s['o1'] * SR)] = True
def _db(x): return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)
if MIX >= 2 and play_mask.any():
    # las canciones vienen masterizadas muy fuerte y el audio de Twitch no: con una ganancia fija el juego quedaba
    # 15 dB debajo de la música. Se nivela contra la música de este video: el juego queda GAME_VS_MUSIC dB debajo
    # (antes del realce de los tiros, que lo pasa por encima en cada disparo).
    GAME_VS_MUSIC = float(os.environ.get('MONTAGE_GAME_VS_MUSIC', globals().get('GAME_VS_MUSIC', _A['game_vs_music'])))
    cur = _db(game.mean(axis=1)[play_mask]) - _db(song.mean(axis=1)[play_mask] * MUSIC_BED)
    game_lift = float(np.clip(10 ** ((GAME_VS_MUSIC - cur) / 20), 1.0, 6.0))
    game *= game_lift
    cgain = {c: g * game_lift for c, g in cgain.items()} or {c: game_lift for c in {s['clip'] for s in segments}}

# ---------- efectos de transición ----------
rng = np.random.default_rng(2)
fx = np.zeros((n, 2))
def band_sweep(dur, f_lo, f_hi, peak):
    tt = np.arange(int(dur * SR)) / SR; nz = rng.normal(0, 1, len(tt)); out = np.zeros(len(tt)); K = 14; seg = len(tt) // K + 1
    for k in range(K):
        x = k / (K - 1); fc = f_lo * (f_hi / f_lo) ** (1 - abs(x - peak) / max(peak, 1 - peak))
        bb = sosfiltfilt(butter(2, [fc * 0.6, min(fc * 1.6, 20000)], 'band', fs=SR, output='sos'), nz)
        out[k * seg:(k + 1) * seg] = bb[k * seg:(k + 1) * seg]
    env = np.where(tt / dur < peak, (tt / dur / peak) ** 2, np.clip(1 - (tt / dur - peak) / (1 - peak), 0, 1) ** 1.5)
    return out * env / (np.abs(out).max() + 1e-9)
for ob, typ, bi in boundaries:
    if typ == 'mega':
        w = band_sweep(0.7, 250, 9000, 0.75); i = int((ob - 0.52) * SR); fx[i:i + len(w)] += (w * 0.30)[:, None]
        tt = np.arange(int(1.6 * SR)) / SR; fq = 30 + 80 * np.exp(-tt / 0.06)
        boom = np.tanh(1.6 * (np.sin(2 * np.pi * np.cumsum(fq) / SR) * np.exp(-tt / 0.5)))
        i = int(ob * SR); fx[i:i + len(boom)] += (boom * 0.30)[:, None]
        continue
    if typ.startswith('whip') or typ == 'zoom':
        dur = 0.34 if 'short' not in typ else 0.22
        w = band_sweep(dur, 350, 6000, 0.6); i = int((ob - dur * 0.6) * SR)
        pan = np.linspace(-0.9, 0.9, len(w)) * (1 if typ != 'whip_rl' else -1) if typ != 'zoom' else np.zeros(len(w))
        L = np.sqrt(0.5 * (1 - pan)); R = np.sqrt(0.5 * (1 + pan))
        g = 0.20 if 'short' not in typ else 0.12
        fx[i:i + len(w), 0] += w * L * g * 1.4; fx[i:i + len(w), 1] += w * R * g * 1.4
    elif typ.startswith('light'):
        dur = 0.5 if 'short' not in typ else 0.3
        tt = np.arange(int(dur * SR)) / SR
        sh = sosfiltfilt(butter(2, 5000, 'high', fs=SR, output='sos'), rng.normal(0, 1, len(tt)))
        sh *= np.sin(np.pi * tt / dur) ** 2 / np.abs(sh).max()
        i = int((ob - dur / 2) * SR); g = 0.10 if 'short' not in typ else 0.06
        fx[i:i + len(sh), 0] += sh * g; fx[i:i + len(sh), 1] += sh * g
for o in (segments[1]['o0'], segments[-2]['o0'] + 0.5):
    w = band_sweep(0.9, 300, 5000, 0.45); i = int((o - 0.1) * SR); fx[i:i + len(w)] += (w * 0.15)[:, None]
fx = fx[:n]

# ---------- realce de transitorios: los tiros y el "dink" del headshot saltan y la música se aparta ----------
mono = game.mean(axis=1)
hf = sosfiltfilt(butter(2, [1200, 9000], 'band', fs=SR, output='sos'), mono)
ef = np.sqrt(np.maximum(uniform_filter1d(hf ** 2, int(0.003 * SR)), 0)); es = np.sqrt(np.maximum(uniform_filter1d(hf ** 2, int(0.08 * SR)), 0)) + 1e-4
tr = np.clip(ef / es - 1.2, 0, 3) / 3
tr = maximum_filter1d(tr, int(0.01 * SR)); tr = uniform_filter1d(tr, int(0.05 * SR))
lvl = np.clip(ef / (np.percentile(ef[ef > 0], 99) + 1e-9), 0, 1)
tr *= np.clip(lvl * 3, 0, 1)
bed = np.full(n, 0.92)
if MIX == 1:
    game = game * (1 + GAME_EMPH * tr)[:, None]
    duck = 1 - MUSIC_DUCK * np.clip(uniform_filter1d(tr, int(0.12 * SR)) * 2.5, 0, 1)
else:
    # presencia: la banda del estallido y del headshot (2-6 kHz) un poco más arriba en todo el juego
    game = game + GAME_PRESENCE * sosfiltfilt(butter(2, [2000, 6000], 'band', fs=SR, output='sos'), game, axis=0)
    game = game * (1 + GAME_EMPH * tr)[:, None]
    hold = maximum_filter1d(tr, int(0.06 * SR))                   # la música se aparta enseguida y vuelve en ~100 ms
    duck = 1 - MUSIC_DUCK * np.clip(uniform_filter1d(hold, int(0.10 * SR)) * 2.5, 0, 1)
    # en cada tiro la música además libera la banda donde vive el disparo (ecualizador dinámico)
    mid = sosfiltfilt(butter(2, [1200, 6000], 'band', fs=SR, output='sos'), song, axis=0)
    song = song - mid * (MUSIC_CARVE * np.clip(uniform_filter1d(hold, int(0.08 * SR)) * 2.5, 0, 1))[:, None]
    # y queda más baja debajo de todo el gameplay que en el logo, el interludio y el outro
    for s in segments:
        if s['kind'] in ('logo', 'interlude', 'outro'): continue
        bed[int(s['o0'] * SR):int(s['o1'] * SR)] = MUSIC_BED
    bed = uniform_filter1d(bed, int(0.35 * SR))

# ---------- reacciones (gritos, festejos) al cierre de una play: la voz sube por encima de la música solo ahí ----------
react = np.zeros((n, 2)); rduck = np.ones(n); rlog = []
USE_RX = globals().get('REACTIONS', True)
if USE_RX is not False and os.path.exists('reactions.json'):
    RX = {int(k): v for k, v in json.load(open('reactions.json')).items()}
    KF = {int(k): v for k, v in json.load(open('kf.json')).items()}
    for c, evs in RX.items():
        if isinstance(USE_RX, dict) and USE_RX.get(c, True) is False: continue
        segs_c = [s for s in segments if s['clip'] == c and s['kind'] in ('play', 'face_out', 'zoom_out')]
        vpath = f'clip_stems/c{c}/vocals.wav'
        if not segs_c or not evs or not os.path.exists(vpath): continue
        shown = [k for k in KF.get(c, []) if any(s['s0'] - 0.3 <= k <= s['s1'] + 0.3 for s in segs_c)]
        if not shown: continue
        last = max(shown)                                         # la kill que cierra la play que se ve
        for e in evs:
            if abs(e['kill'] - last) > 0.05: continue             # nunca en medio de una play
            if e.get('kind') not in REACT_KINDS: continue         # gritos individuales: no se resaltan
            done = False
            for s in segs_c:
                # la reacción vive dentro de su tramo: termina (con fundido) en el corte, nunca suena sobre otro clip
                a0 = max(e['t0'] - 0.06, s['s0']); a1 = min(e['t1'], s['s1'])
                if a1 - a0 < 0.12: continue
                o = s['o0'] + (a0 - s['s0']); i0 = int(round(o * SR))
                v = dec(vpath, a0, a1 - a0)[: n - i0]
                m = len(v); fi = min(int(0.05 * SR), m // 3); fo_ = min(int(0.22 * SR), m // 2)
                env = np.ones(m); env[:fi] = np.linspace(0, 1, fi); env[m - fo_:] = np.linspace(1, 0, fo_)
                gk = (0.55 if s['kind'] == 'face_out' else GAME_GAIN) * cgain.get(c, 1.0)
                react[i0:i0 + m] += v * (env * REACT_GAIN * gk)[:, None]
                # la música no vuelve de golpe: sigue baja REACT_HOLD s después del grito (sin pasar el corte del clip)
                # y recién ahí sube en REACT_RELEASE s (el usuario la sentía volver muy rápido)
                o_end = o + m / SR; hold_end = max(o_end, min(o_end + REACT_HOLD, s['o1']))
                k0 = i0; k1 = int(hold_end * SR); k2 = min(n, k1 + int(REACT_RELEASE * SR))
                dk = np.zeros(k2 - k0)
                dk[:fi] = np.linspace(0, 1, fi); dk[fi:k1 - k0] = 1
                dk[k1 - k0:] = 0.5 * (1 + np.cos(np.linspace(0, np.pi, k2 - k1)))
                rduck[k0:k2] = np.minimum(rduck[k0:k2], 1 - REACT_DUCK * dk)
                rlog.append(f"c{c} {e['kind']} (+{e['db']} dB sobre la charla): clip {a0:.2f}-{a1:.2f}s -> video {o:.2f}-{o + a1 - a0:.2f}s")
                done = True
            if not done:
                end = max(s['s1'] for s in segs_c)
                rlog.append(f"c{c} {e['kind']} en {e['t0']:.2f}s del clip queda AFUERA (el tramo termina en {end:.2f}s): "
                            f"si la play lo merece, alargá el fin del tramo (check_kills.py sugiere cuánto)")
    rduck = 1 - uniform_filter1d(1 - rduck, int(0.08 * SR))

songm = song * (bed * duck * rduck)[:, None]
mix = songm + game + react + fx
mix = np.tanh(mix * 1.05) / np.tanh(1.05)
if MIX == 1:
    mix *= 0.89 / np.abs(mix).max()
else:
    # los tiros más fuertes dejan picos entre muestras: se normaliza al pico real (sobremuestreado 4x) en -1.5 dBTP
    from scipy.signal import resample_poly
    tp = max(np.abs(resample_poly(mix[:, ch], 4, 1)).max() for ch in (0, 1))
    if LUFS_TARGET is None:
        mix *= 10 ** (TP_LIMIT / 20) / tp
    else:
        # objetivo de loudness (EBU R128): se lleva la mezcla a ese nivel y el pico real solo puede bajarla, nunca subirla
        lufs_in = _lufs(mix)
        g = 10 ** ((LUFS_TARGET - lufs_in) / 20) if lufs_in is not None else 10 ** (TP_LIMIT / 20) / tp
        mix *= min(g, 10 ** (TP_LIMIT / 20) / tp)
    # el AAC del video final agrega ~1.5 dB de pico en los tiros: se codifica una prueba, se mide y se corrige
    import tempfile, re
    for _ in range(2):
        tmp = os.path.join(tempfile.gettempdir(), f'montage_tp_{os.getpid()}.m4a')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 's16le', '-ar', str(SR), '-ac', '2', '-i', '-', '-c:a', 'aac', '-b:a', '320k', tmp],
                       input=(mix * 32767).astype(np.int16).tobytes())
        r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', tmp, '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                           capture_output=True, text=True, errors='replace').stderr
        os.remove(tmp)
        pk = re.findall(r'Peak:\s+(-?[\d.]+|-inf)', r)
        if not pk or float(pk[-1]) <= -1.3: break
        mix *= 10 ** ((-1.4 - float(pk[-1])) / 20)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 's16le', '-ar', str(SR), '-ac', '2', '-i', '-', OUT_WAV],
               input=(mix * 32767).astype(np.int16).tobytes())


# ---------- balance juego / música (queda en audio_balance.txt para comparar entre edits) ----------
gm, sm = (game + react).mean(axis=1), songm.mean(axis=1)
lines = [f'mezcla {MIX}: juego {GAME_GAIN} · realce {GAME_EMPH} · música {MUSIC_BED if MIX >= 2 else 0.92} (se aparta {MUSIC_DUCK} en cada tiro)'
         + (f' · juego nivelado ×{game_lift:.2f}' if MIX >= 2 else ''),
         f'juego vs música en las plays: {_db(gm[play_mask]) - _db(sm[play_mask]):+.1f} dB']
sh = []
for k in globals().get('kills', []):
    i = int(k * SR); w0, w1 = i - int(0.03 * SR), i + int(0.15 * SR)
    if w0 - int(0.25 * SR) < 0 or w1 > n: continue
    pk = np.sqrt(np.max(uniform_filter1d(gm[w0:w1] ** 2, int(0.01 * SR))))
    mus = np.sqrt(np.max(uniform_filter1d(sm[w0:w1] ** 2, int(0.01 * SR)))) + 1e-9
    sh.append(20 * np.log10(pk / mus + 1e-9))
if sh:
    sh = np.array(sh)
    lines.append(f'tiro de cada kill sobre la música: mediana {np.median(sh):+.1f} dB, el más bajo {sh.min():+.1f} dB ({len(sh)} kills)')
lines += [f'loudness: {_lufs(mix):.1f} LUFS' + (f' (objetivo {LUFS_TARGET:g})' if LUFS_TARGET is not None else ' (sin objetivo: lo que deja el pico)')]
lines += [f'reacciones resaltadas: {sum("->" in r for r in rlog)}'] + ['  ' + r for r in rlog]
open(os.environ.get('MONTAGE_AUDIO_LOG', 'audio_balance.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
print('\n'.join(lines))
print('ok', TOTAL)
