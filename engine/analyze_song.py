"""Analiza la canción de un proyecto (projects/<nombre>/song.mp3).

    python engine/analyze_song.py projects/<nombre>

Guarda beats.npy, hits.npy (golpe percusivo exacto por beat) y grid.npy (grilla regular ajustada),
e imprime: BPM, mapa de bombo (para encontrar drops y cortes de batería) y pares de golpes vocales
(candidatos a "bang bang" u otros acentos de la voz)."""
import os, sys, subprocess
import numpy as np, librosa
from scipy.signal import butter, sosfiltfilt, find_peaks

project = os.path.abspath(sys.argv[1]); os.chdir(project)
song = 'song.mp3' if os.path.exists('song.mp3') else next(f for f in os.listdir('.') if f.lower().endswith(('.mp3', '.wav', '.m4a', '.flac')))
SR = 48000

y, sr = librosa.load(song, sr=22050)
dur = len(y) / sr
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time')
np.save('beats.npy', beats)

a = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', song, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                                 capture_output=True).stdout, np.float32).astype(float)
lo = sosfiltfilt(butter(4, [35, 160], 'band', fs=SR, output='sos'), a)
hi = sosfiltfilt(butter(4, [1500, 8000], 'band', fs=SR, output='sos'), a)
env = lambda x: np.sqrt(np.convolve(x ** 2, np.ones(96) / 96, 'same'))
el, eh = env(lo), env(hi)
hits = []
for b in beats:
    i0 = max(0, int((b - 0.09) * SR)); i1 = int((b + 0.09) * SR)
    e = el[i0:i1] / el.max() + 0.6 * eh[i0:i1] / eh.max()
    if len(e) < 600:
        hits.append(b); continue
    d = e[480:] - e[:-480]; j = int(np.argmax(d)) + 480; pk = e[j]
    fl = np.percentile(e[:max(1, j - 200)], 20) if j > 200 else e[:j].min()
    k = j
    while k > 0 and e[k] > fl + 0.3 * (pk - fl): k -= 1
    hits.append((i0 + k) / SR)
hits = np.array(hits); np.save('hits.npy', hits)
idx = np.arange(len(hits)); m = (hits > 5) & (hits < dur - 5)
x, yy = idx[m], hits[m]
for _ in range(6):
    p = np.polyfit(x, yy, 1); r = yy - np.polyval(p, x); keep = abs(r) < max(0.012, 2.5 * np.median(abs(r))); x, yy = x[keep], yy[keep]
p = np.polyfit(x, yy, 1); grid = np.polyval(p, idx); np.save('grid.npy', grid)
print(f'Canción: {song}  duración {dur:.1f}s  BPM {60 / p[0]:.2f}  beats {len(beats)}')

# mapa de bombo cada 0.25 s:  '#' fuerte  '+' medio  '.' sin bombo
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=256)); f = librosa.fft_frequencies(sr=sr, n_fft=2048)
t = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=256)
low = S[f < 130].sum(0); low /= np.percentile(low, 90)
print('\nMapa de bombo (cada caracter = 0.25 s). Los "." seguidos son cortes de batería; donde vuelve "#" hay un drop:')
for a0 in range(0, int(dur), 8):
    line = ''
    for xx in np.arange(a0, min(a0 + 8, dur), 0.25):
        i = (t >= xx) & (t < xx + 0.25); v = low[i].max() if i.any() else 0
        line += '#' if v > 0.5 else ('+' if v > 0.2 else '.')
    print(f'{a0:4d}s {line}')

# pares de golpes vocales
H, P = librosa.effects.hpss(y, margin=3.0)
hop = 220
SV = np.abs(librosa.stft(H, n_fft=1024, hop_length=hop)); fv = librosa.fft_frequencies(sr=sr, n_fft=1024)
v = SV[(fv > 200) & (fv < 4000)].sum(0); v /= np.percentile(v, 99)
pk, _ = find_peaks(v, prominence=0.35, distance=6); tv = pk * hop / sr
pairs = [(round(tv[i], 2), round(tv[i + 1], 2)) for i in range(len(tv) - 1)
         if 0.12 < tv[i + 1] - tv[i] < 0.32 and min(v[pk[i]], v[pk[i + 1]]) > 0.7]
print('\nPares de golpes vocales (posibles "bang bang"; confirmá con el usuario):')
for a_, b_ in pairs:
    print(f'  {a_:7.2f}s / {b_:7.2f}s')
