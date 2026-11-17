import numpy as np, librosa, json
y, sr = librosa.load('stems/htdemucs/song/vocals.wav', sr=22050, mono=True)
grid = np.load('grid.npy')
hop = 128
rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
on_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
ons = librosa.onset.onset_detect(onset_envelope=on_env, sr=sr, hop_length=hop, backtrack=True, units='time', delta=0.08)
lvl = rms / np.percentile(rms, 98)
# solo onsets con voz real (nivel > 0.12 en los 80 ms siguientes)
keep = []
for o in ons:
    i = int(o * sr / hop); seg = lvl[i:i + int(0.08 * sr / hop)]
    if len(seg) and seg.max() > 0.15: keep.append(o)
ons = np.array(keep)
# timbre de cada sílaba (MFCC promedio de 150 ms)
M = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)
def feat(o):
    i = int(o * sr / hop); return M[1:, i:i + int(0.15 * sr / hop)].mean(1)
F = np.array([feat(o) for o in ons])
def sim(a, b): return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
print('Actividad vocal (cada caracter 0.25 s; # fuerte, + media, . nada):')
for a0 in range(0, 152, 8):
    line = ''
    for xx in np.arange(a0, a0 + 8, 0.25):
        m = (t >= xx) & (t < xx + 0.25); v = lvl[m].max() if m.any() else 0
        line += '#' if v > 0.5 else ('+' if v > 0.15 else '.')
    print(f'{a0:4d}s {line}')
# rachas: onsets sucesivos con separación parecida (0.18-0.8 s, variación <25%) y timbre parecido
runs = []; i = 0
while i < len(ons) - 2:
    j = i + 1; gaps = []
    while j < len(ons):
        g = ons[j] - ons[j - 1]
        if not (0.18 <= g <= 0.8): break
        if gaps and abs(g - np.median(gaps)) > 0.25 * np.median(gaps): break
        if sim(F[j], F[i]) < 0.80 and sim(F[j], F[j - 1]) < 0.85: break
        gaps.append(g); j += 1
    if j - i >= 3: runs.append((i, j)); i = j
    else: i += 1
print('\nRachas de repeticiones (inicio, n, separación media, tiempos):')
out = []
for a, b in runs:
    ts = ons[a:b]; gi = [int(np.argmin(abs(grid - x))) for x in ts]
    off = [round(1000 * (x - grid[k])) for x, k in zip(ts, gi)]
    print(f'  {ts[0]:7.2f}s  n={b - a:2d}  gap={np.mean(np.diff(ts)):.3f}  ' + ' '.join(f'{x:.2f}' for x in ts) + f'   (ms vs beat: {off})')
    out.append([round(float(x), 3) for x in ts])
json.dump({'onsets': [round(float(x), 3) for x in ons], 'runs': out}, open('vocal_reps.json', 'w'))
