import os, sys
PROJECT = os.path.abspath(sys.argv[1]); ENGINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT); os.chdir(PROJECT)
sys.argv = [sys.argv[0]] + sys.argv[2:]
import numpy as np, subprocess
from scipy.signal import butter, sosfiltfilt
from plan import *
SR = 48000
def dec(path, ss, t):
    cmd = ['ffmpeg', '-v', 'error', '-ss', f'{max(ss,0):.5f}', '-i', path, '-t', f'{t:.5f}', '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-']
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32).reshape(-1, 2).astype(np.float64)
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
game = np.zeros((n, 2))
for i, s in enumerate(segments):
    if s['kind'] in ('logo', 'interlude', 'outro'): continue
    if s['kind'] == 'slowmo':
        D = s['o1'] - s['o0']; u = np.arange(int(D * SR)) / SR; vmin = (s['s1'] - s['s0'] - 0.12) / (D - 0.12)
        src = s['s0'] + vmin * u + (1 - vmin) * 0.12 * (1 - np.exp(-u / 0.12))
        raw = dec(f"clips/c{s['clip']}.mp4", s['s0'], 1.0); p = np.clip((src - s['s0']) * SR, 0, len(raw) - 2); ii = p.astype(int); fr = (p - ii)[:, None]
        seg = raw[ii] * (1 - fr) + raw[ii + 1] * fr
        seg = sosfiltfilt(butter(2, 1200, 'low', fs=SR, output='sos'), seg, axis=0) * np.linspace(1, 0.2, len(seg))[:, None]
        i0 = int(round(s['o0'] * SR)); game[i0:i0 + len(seg)] += seg * 0.4; continue
    a = ext.get(i, 0.012); b = ext.get((i - 1 + 1, 'end'), 0.012) if False else ext.get((i, 'end'), 0.012)
    o0 = s['o0'] - a; o1 = s['o1'] + b
    src0 = s['s0'] - a
    seg = dec(f"clips/c{s['clip']}.mp4", src0, o1 - o0)
    if src0 < 0: seg = np.pad(seg, ((int(-src0 * SR), 0), (0, 0)))[: len(seg)]
    i0 = int(round(o0 * SR)); L = min(len(seg), n - i0)
    seg = seg[:L].copy()
    fa, fb = int(2 * a * SR), int(2 * b * SR)
    seg[:fa] *= np.linspace(0, 1, fa)[:, None]; seg[-fb:] *= np.linspace(1, 0, fb)[:, None]
    g = 0.78 if s['kind'] != 'face_out' else 0.40
    game[i0:i0 + L] += seg * g
game *= np.clip((OUTRO0 - t) / 1.5, 0, 1)[:, None]

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
# transient emphasis: make shots / headshot dinks pop, duck music a touch under them
from scipy.ndimage import maximum_filter1d, uniform_filter1d
mono = game.mean(axis=1)
hf = sosfiltfilt(butter(2, [1200, 9000], 'band', fs=SR, output='sos'), mono)
ef = np.sqrt(np.maximum(uniform_filter1d(hf ** 2, int(0.003 * SR)), 0)); es = np.sqrt(np.maximum(uniform_filter1d(hf ** 2, int(0.08 * SR)), 0)) + 1e-4
tr = np.clip(ef / es - 1.2, 0, 3) / 3
tr = maximum_filter1d(tr, int(0.01 * SR)); tr = uniform_filter1d(tr, int(0.05 * SR))
lvl = np.clip(ef / (np.percentile(ef[ef > 0], 99) + 1e-9), 0, 1)
tr *= np.clip(lvl * 3, 0, 1)
game = game * (1 + 1.7 * tr)[:, None]
duck = 1 - 0.42 * np.clip(uniform_filter1d(tr, int(0.12 * SR)) * 2.5, 0, 1)
mix = song * 0.92 * duck[:, None] + game + fx
mix = np.tanh(mix * 1.05) / np.tanh(1.05)
mix *= 0.89 / np.abs(mix).max()
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 's16le', '-ar', str(SR), '-ac', '2', '-i', '-', 'work_audio.wav'],
               input=(mix * 32767).astype(np.int16).tobytes())
print('ok', TOTAL)
