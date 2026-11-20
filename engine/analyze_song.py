"""Analiza la canción de un proyecto (projects/<nombre>/song.mp3).

    python engine/analyze_song.py projects/<nombre>

Guarda beats.npy, hits.npy (golpe percusivo exacto por beat) y grid.npy (grilla regular ajustada),
e imprime: BPM, mapa de bombo (para encontrar drops y cortes de batería), los MOMENTOS PARA SINCRONIZAR
(drops, vuelta del bombo después de un corte, subidas de energía, entrada o corte de la voz: cada uno lleva una kill
exacta o el arranque de una buena play; se guardan en sync.json y van en SYNC del plan) y pares de golpes vocales
(candidatos a "bang bang" u otros acentos de la voz)."""
import os, sys, subprocess, json
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

# ---------- momentos para sincronizar ----------
# En "Faster N Harder" el drop más fuerte (el bajo se corta en el 1.er tiempo y vuelve con todo en el 2.º, 78.91 s)
# no subía la energía del compás y quedó sin kill: por eso se buscan tres señales y se miden beat por beat
# (sin suponer dónde empieza el compás).
NB = len(grid) - 1
def _db(x, i0, i1): seg = x[int(grid[i0] * SR):int(grid[min(i1, NB)] * SR)]; return 10 * np.log10(np.mean(seg ** 2) + 1e-12)
fdb = np.array([_db(a, b, b + 1) for b in range(NB)]); bdb = np.array([_db(lo, b, b + 1) for b in range(NB)])
def rise(arr, b, k=4): return arr[b:b + k].mean() - arr[max(0, b - k):b].mean() if b >= k and b + k <= len(arr) else 0.0
def local_max(score, thr, win=3):
    return [b for b in range(len(score)) if score[b] >= thr and score[b] == max(score[max(0, b - win):b + win + 1])]
cands = []
# 1) subidas de energía (mezcla completa o graves), beat por beat
esc = np.array([max(rise(fdb, b), rise(bdb, b) / 1.5) for b in range(NB)])
for b in local_max(esc, 1.4):
    cands.append(dict(t=float(grid[b]), tipo=f'sube la energía (+{rise(fdb, b):.1f} dB, graves +{rise(bdb, b):.1f} dB)', fuerza=float(esc[b])))
if cands:
    early = [c for c in cands if c['t'] < dur * 0.4] or cands
    first = max(early, key=lambda c: c['fuerza']); first['tipo'] = 'entra la batería (primer drop) + ' + first['tipo']
# 2) el bombo vuelve después de un corte de >= 0.5 s (mapa cada 0.25 s)
step = 0.25
kt = np.arange(0, dur, step)
kv = np.array([low[(t >= xx) & (t < xx + step)].max() if ((t >= xx) & (t < xx + step)).any() else 0 for xx in kt])
strong = kv > 0.5
run = np.convolve(strong.astype(float), np.ones(4) / 4, 'valid')
i = (int(np.argmax(run >= 0.75)) if (run >= 0.75).any() else 0) + 4
while i < len(kt):
    if not strong[i]:
        j = i
        while j < len(kt) and not strong[j]: j += 1
        gap = (j - i) * step
        if gap >= 0.5 and j < len(kt) - 4 and strong[j:j + 4].mean() >= 0.75:
            # si el beat en que vuelve ya suena tan fuerte como los 4 siguientes, el drop es ahí (a veces en el 2.º
            # tiempo); si vuelve suave y crece, es el beat de mayor subida de los 6 siguientes
            rb = int(np.argmin(abs(grid - kt[j])))
            if rb + 5 < NB and fdb[rb] >= fdb[rb + 1:rb + 5].mean() - 0.5:
                tb = rb
            else:
                tb = max(range(rb, min(NB, rb + 7)), key=lambda q: esc[q])
            cands.append(dict(t=float(grid[tb]), tipo=f'vuelve el bombo después de un corte de {gap:.2f} s', fuerza=1.5 + gap))
        i = j
    i += 1
# 3) la voz entra o se corta (banda armónica 300-3000 Hz), beat por beat
Hh, _ = librosa.effects.hpss(y, margin=3.0)
hv = sosfiltfilt(butter(4, [300, 3000], 'band', fs=sr, output='sos'), Hh)
vb = np.array([10 * np.log10(np.mean(hv[int(grid[q] * sr):int(grid[q + 1] * sr)] ** 2) + 1e-12) for q in range(NB)])
vsc = np.array([rise(vb, q) for q in range(NB)])
for q in local_max(np.abs(vsc), 6):
    cands.append(dict(t=float(grid[q]), tipo=('entra la voz' if vsc[q] > 0 else 'se corta la voz') + f' ({vsc[q]:+.1f} dB)', fuerza=abs(vsc[q]) / 4))
# juntar los que caen en el mismo beat y descartar el final de la canción (fundido)
cands.sort(key=lambda c: c['t']); sync = []
for c in cands:
    if c['t'] > dur - 6: continue
    if sync and abs(c['t'] - sync[-1]['t']) < 0.3:
        sync[-1]['tipo'] += ' + ' + c['tipo']; sync[-1]['fuerza'] = round(sync[-1]['fuerza'] + c['fuerza'], 2)
    else:
        c['fuerza'] = round(c['fuerza'], 2); sync.append(c)
json.dump(sync, open('sync.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print('\nMomentos para sincronizar (tiempo de canción): cada uno lleva una kill EXACTA o el arranque de una buena play.')
print('Elegí los que se oyen como cambio fuerte (en general fuerza >= 2) y ponelos en SYNC del plan; check_kills.py los controla:')
for c in sync:
    print(f"  {c['t']:7.2f}s  fuerza {c['fuerza']:4.1f}  {c['tipo']}")
print('\nConfirmá el beat exacto de cada uno (la subida puede caer un beat antes o después del golpe): el drop es el beat')
print('donde el bajo vuelve o el primero que suena con todo. Volumen total / graves en dB, beat por beat ([x] = candidato):')
for c in sync:
    bc = int(np.argmin(abs(grid - c['t'])))
    cells = [('[' if q == bc else ' ') + f"{grid[q]:6.2f} {fdb[q]:5.1f}/{bdb[q]:5.1f}" + (']' if q == bc else ' ')
             for q in range(max(0, bc - 3), min(NB, bc + 4))]
    print('  ' + ''.join(cells))

# pares de golpes vocales
H = Hh
hop = 220
SV = np.abs(librosa.stft(H, n_fft=1024, hop_length=hop)); fv = librosa.fft_frequencies(sr=sr, n_fft=1024)
v = SV[(fv > 200) & (fv < 4000)].sum(0); v /= np.percentile(v, 99)
pk, _ = find_peaks(v, prominence=0.35, distance=6); tv = pk * hop / sr
pairs = [(round(tv[i], 2), round(tv[i + 1], 2)) for i in range(len(tv) - 1)
         if 0.12 < tv[i + 1] - tv[i] < 0.32 and min(v[pk[i]], v[pk[i + 1]]) > 0.7]
print('\nPares de golpes vocales (posibles "bang bang"; confirmá con el usuario):')
for a_, b_ in pairs:
    print(f'  {a_:7.2f}s / {b_:7.2f}s')
