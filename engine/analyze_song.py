"""Analiza la canción de un proyecto (projects/<nombre>/song.mp3).

    python engine/analyze_song.py projects/<nombre>

Guarda beats.npy, hits.npy (golpe percusivo exacto por beat) y grid.npy (grilla ajustada: una recta si el tempo es fijo,
una por tramo si la canción cambia de tempo), sync.json (MOMENTOS PARA SINCRONIZAR: drops, vuelta del bombo después de
un corte, subidas de energía, entrada o corte de la voz; cada uno lleva una kill exacta o el arranque de una buena
play), vocal_hits.json (pares de golpes vocales, candidatos a "bang bang") y song.json (tempo por tramo, compás,
energía beat por beat y por sección, y dónde conviene arrancar el video y poner los dos drops).
Imprime además el mapa de bombo, para confirmar a oído drops y cortes de batería.
"""
import os, sys, subprocess, json
import numpy as np, librosa
from scipy.signal import butter, sosfiltfilt, find_peaks

SR = 48000
SYNC_MIN = 2.0           # fuerza desde la que un momento separa dos secciones de la canción


def pick_sync(cands, gaps, grid, lv, bs):
    """Los momentos que se pueden tomar solos como SYNC, sin que nadie los confirme a oído: una subida fuerte
    (fuerza >= 8) o el bombo que vuelve después de un corte, puestos en el primer beat que ya suena con todo (la subida
    se suele marcar un beat antes, cuando asoma el bajo). Medido contra 34 momentos confirmados a mano en 5 canciones:
    encuentra la mitad y 4 de cada 5 caen en el beat exacto (el resto, un beat corrido). Por eso es un punto de
    partida, no la última palabra: edit.json puede fijar su propia lista en song.sync."""
    NB = len(lv); out = []
    for c, gap in zip(cands, gaps):
        if not (gap >= 0.5 or c['fuerza'] >= 8): continue
        b = int(np.argmin(abs(grid - c['t']))); q = None
        for k in range(max(4, b - 1), min(NB - 5, b + 3)):
            if bs[k] >= bs[k + 1:k + 5].mean() - 3 and lv[k] >= lv[k + 1:k + 5].mean() - 3: q = k; break
        if q is None: continue
        if 0.5 * (lv[q] + bs[q]) - 0.5 * (lv[q - 4:q - 1].mean() + bs[q - 4:q - 1].mean()) < 5: continue   # un cambio de verdad
        t = float(grid[q])
        if out and abs(t - out[-1]) < 1.0: continue
        out.append(round(t, 3))
    return out


def find_song(project='.'):
    if os.path.exists(os.path.join(project, 'song.mp3')): return 'song.mp3'
    return next(f for f in sorted(os.listdir(project)) if f.lower().endswith(('.mp3', '.wav', '.m4a', '.flac')))


def track_beats(y, sr):
    """Beats de librosa. Si el tempo cambia a lo largo de la canción (medido en ventanas), se sigue con el tempo de
    cada momento en vez de uno solo para todo el tema. Devuelve (beats, tempo_fijo: bool)."""
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time')
    try:
        oenv = librosa.onset.onset_strength(y=y, sr=sr)
        local = librosa.feature.tempo(onset_envelope=oenv, sr=sr, aggregate=None)
        base = float(np.atleast_1d(tempo)[0])
        # se ignoran los errores de octava (el doble o la mitad)
        rel = local / base
        rel = np.where(abs(rel - 2) < 0.1, rel / 2, np.where(abs(rel - 0.5) < 0.05, rel * 2, rel))
        off = abs(rel - 1) > 0.06
        # Un cambio real dura y es estable: al menos 20 s seguidos con otro tempo, siempre el mismo. En una canción de
        # tempo fijo la medida local salta unos segundos a 4/3 o 5/4 del tempo en los cortes y partes sincopadas
        # (medido en Caffeine Rush: 136 y 143 BPM durante ~10 s en un tema de 105): eso no es un cambio.
        need = int(20 * sr / 512); i = 0; changed = False
        while i < len(off):
            if off[i]:
                j = i
                while j < len(off) and off[j]: j += 1
                seg = local[i:j]
                if j - i >= need and np.std(seg) < 0.02 * np.median(seg): changed = True
                i = j
            i += 1
        if changed:
            _, beats2 = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, bpm=local, units='time')
            if len(beats2) > 8: return beats2, False
    except Exception:
        pass
    return beats, True


def find_hits(a, beats):
    """Para cada beat, el golpe real (bombo o caja) en una ventana de ±90 ms: donde la envolvente sube más."""
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
    return np.array(hits), lo


def fix_phase(a, beats):
    """Si el seguidor de beats quedó en el contratiempo (el bombo suena justo entre dos beats, mucho más fuerte que sobre
    ellos), corre todo medio beat. En una canción bien seguida no toca nada."""
    if len(beats) < 16: return beats
    lo = sosfiltfilt(butter(4, [35, 160], 'band', fs=SR, output='sos'), a) ** 2
    def power(ts):
        v = [lo[max(0, int((t - 0.04) * SR)):int((t + 0.04) * SR)].mean() for t in ts if 0.05 < t < len(lo) / SR - 0.05]
        return float(np.median(v)) if v else 0.0
    mid = (beats[:-1] + beats[1:]) / 2
    on, off = power(beats), power(mid)
    if off > 8 * on and off > 0:           # 9 dB más de bombo en el contratiempo que en el beat
        return np.concatenate([mid, [beats[-1] + (beats[-1] - beats[-2]) / 2]])
    return beats


def _line(x, yy):
    """Recta robusta (descarta los golpes corridos: fills, síncopas, partes sin batería)."""
    for _ in range(6):
        p = np.polyfit(x, yy, 1); r = yy - np.polyval(p, x)
        keep = abs(r) < max(0.012, 2.5 * np.median(abs(r))); x, yy = x[keep], yy[keep]
        if len(x) < 4: break
    return np.polyfit(x, yy, 1)


def fit_grid(hits, dur, fixed=True):
    """Grilla de beats. Tempo fijo: una recta para toda la canción (como siempre). Si no, una recta por tramo.
    Devuelve (grid, tramos) con tramos = [{i0, i1, t0, t1, bpm}]."""
    idx = np.arange(len(hits)); m = (hits > 5) & (hits < dur - 5)
    if m.sum() < 8: m = np.ones(len(hits), bool)
    p = _line(idx[m], hits[m]); grid = np.polyval(p, idx)
    one = [dict(i0=0, i1=int(len(hits)), t0=float(grid[0]), t1=float(grid[-1]), bpm=round(60 / p[0], 2))]
    if len(hits) < 48:
        return grid, one
    # tempo local en ventanas de 24 beats: si todas las ventanas con buen ajuste coinciden con la recta global, es fijo
    W, ST = 24, 4
    wins = []
    for s in range(0, len(hits) - W + 1, ST):
        x = idx[s:s + W]; pw = _line(x, hits[s:s + W]); r = hits[s:s + W] - np.polyval(pw, x)
        if np.median(abs(r)) < 0.012 and (abs(r) < 0.03).mean() > 0.7:
            wins.append((s, pw))
    drift = [abs(pw[0] / p[0] - 1) > 0.004 or abs(np.polyval(pw, s + W / 2) - np.polyval(p, s + W / 2)) > 0.03 for s, pw in wins]
    # Tempo fijo con partes sincopadas (el golpe fuerte cae corrido, pero vuelve): la mayoría de las ventanas siguen la
    # recta global. Tempo que de verdad cambia o deriva: casi ninguna la sigue.
    if not wins or np.mean(drift) < (0.5 if fixed else 0.15):
        return grid, one
    # tramos: ventanas seguidas con el mismo tempo (±0.4 %) y la misma fase (±30 ms)
    groups = []
    for s, pw in wins:
        g = groups[-1] if groups else None
        if g and abs(pw[0] / g['p'][0] - 1) < 0.004 and abs(np.polyval(pw, s + W / 2) - np.polyval(g['p'], s + W / 2)) < 0.03:
            g['b'] = s + W; g['p'] = _line(idx[g['a']:g['b']], hits[g['a']:g['b']])
        else:
            groups.append(dict(a=s, b=s + W, p=pw))
    groups = [g for g in groups if g['b'] - g['a'] >= W]
    if len(groups) < 2:
        return grid, one
    # el cambio entre dos tramos va donde se cruzan sus rectas (o, si son paralelas, en el medio del hueco)
    cuts = [0]
    for g0, g1 in zip(groups, groups[1:]):
        d = g0['p'][0] - g1['p'][0]
        x = (g1['p'][1] - g0['p'][1]) / d if abs(d) > 1e-9 else (g0['b'] + g1['a']) / 2
        if not (g0['a'] + 4 <= x <= g1['b'] - 4): x = (g0['b'] + g1['a']) / 2
        cuts.append(int(round(x)))
    cuts.append(len(hits))
    grid = np.empty(len(hits)); segs = []
    for g, c0, c1 in zip(groups, cuts, cuts[1:]):
        grid[c0:c1] = np.polyval(g['p'], idx[c0:c1])
        segs.append(dict(i0=int(c0), i1=int(c1), t0=float(grid[c0]), t1=float(grid[c1 - 1]), bpm=round(60 / g['p'][0], 2)))
    single = np.polyval(p, idx)
    if (np.diff(grid) <= 0.05).any():          # un cruce mal puesto: mejor la recta única que beats encimados
        return single, one
    # Solo vale si explica los golpes claramente mejor que la recta única. En un tema de golpes irregulares (medido en
    # "Don't Like Remix": apenas el 12 % de los golpes cae sobre cualquier grilla) partirlo en tramos no arregla nada.
    near = lambda g: float((abs(hits - g) < 0.03).mean())
    if near(grid) < 0.5 or near(grid) < near(single) + 0.15:
        return single, one
    return grid, segs


def analyze(project, verbose=True):
    say = print if verbose else (lambda *a, **k: None)
    project = os.path.abspath(project); cwd = os.getcwd(); os.chdir(project)
    try:
        return _analyze(say)
    finally:
        os.chdir(cwd)


def _analyze(say):
    song = find_song()
    y, sr = librosa.load(song, sr=22050)
    dur = len(y) / sr
    beats, fixed = track_beats(y, sr)
    np.save('beats.npy', beats)

    a = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', song, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                                     capture_output=True).stdout, np.float32).astype(float)
    shifted = fix_phase(a, beats)
    if shifted is not beats:
        beats = shifted; np.save('beats.npy', beats)
        say('(el seguidor de beats había quedado en el contratiempo: se corrió medio beat)')
    hits, lo = find_hits(a, beats); np.save('hits.npy', hits)
    grid, tempo_segs = fit_grid(hits, dur, fixed); np.save('grid.npy', grid)
    bpm = tempo_segs[0]['bpm']
    if len(tempo_segs) == 1:
        say(f'Canción: {song}  duración {dur:.1f}s  BPM {bpm:.2f}  beats {len(beats)}')
    else:
        say(f'Canción: {song}  duración {dur:.1f}s  beats {len(beats)}  TEMPO VARIABLE, {len(tempo_segs)} tramos:')
        for s in tempo_segs: say(f"   {s['t0']:6.1f}s - {s['t1']:6.1f}s   {s['bpm']:.2f} BPM")

    # mapa de bombo cada 0.25 s:  '#' fuerte  '+' medio  '.' sin bombo
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=256)); f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    t = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=256)
    low = S[f < 130].sum(0); low /= np.percentile(low, 90)
    say('\nMapa de bombo (cada caracter = 0.25 s). Los "." seguidos son cortes de batería; donde vuelve "#" hay un drop:')
    for a0 in range(0, int(dur), 8):
        line = ''
        for xx in np.arange(a0, min(a0 + 8, dur), 0.25):
            i = (t >= xx) & (t < xx + 0.25); v = low[i].max() if i.any() else 0
            line += '#' if v > 0.5 else ('+' if v > 0.2 else '.')
        say(f'{a0:4d}s {line}')

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
    first = None
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
                cands.append(dict(t=float(grid[tb]), tipo=f'vuelve el bombo después de un corte de {gap:.2f} s', fuerza=1.5 + gap, gap=gap))
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
            sync[-1]['gap'] = max(sync[-1].get('gap', 0), c.get('gap', 0))
        else:
            c['fuerza'] = round(c['fuerza'], 2); sync.append(c)
    gaps = [c.pop('gap', 0) for c in sync]
    json.dump(sync, open('sync.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    say('\nMomentos para sincronizar (tiempo de canción): cada uno lleva una kill EXACTA o el arranque de una buena play.')
    say('Elegí los que se oyen como cambio fuerte y ponelos en song.sync de edit.json (SYNC del plan); check_kills.py los controla:')
    for c in sync:
        say(f"  {c['t']:7.2f}s  fuerza {c['fuerza']:4.1f}  {c['tipo']}")
    say('\nConfirmá el beat exacto de cada uno (la subida puede caer un beat antes o después del golpe): el drop es el beat')
    say('donde el bajo vuelve o el primero que suena con todo. Volumen total / graves en dB, beat por beat ([x] = candidato):')
    for c in sync:
        bc = int(np.argmin(abs(grid - c['t'])))
        cells = [('[' if q == bc else ' ') + f"{grid[q]:6.2f} {fdb[q]:5.1f}/{bdb[q]:5.1f}" + (']' if q == bc else ' ')
                 for q in range(max(0, bc - 3), min(NB, bc + 4))]
        say('  ' + ''.join(cells))

    # pares de golpes vocales
    H = Hh
    hop = 220
    SV = np.abs(librosa.stft(H, n_fft=1024, hop_length=hop)); fv = librosa.fft_frequencies(sr=sr, n_fft=1024)
    v = SV[(fv > 200) & (fv < 4000)].sum(0); v /= np.percentile(v, 99)
    pk, _ = find_peaks(v, prominence=0.35, distance=6); tv = pk * hop / sr
    pairs = [(round(tv[i], 2), round(tv[i + 1], 2)) for i in range(len(tv) - 1)
             if 0.12 < tv[i + 1] - tv[i] < 0.32 and min(v[pk[i]], v[pk[i + 1]]) > 0.7]
    json.dump([[float(a_), float(b_)] for a_, b_ in pairs], open('vocal_hits.json', 'w'))
    say('\nPares de golpes vocales (posibles "bang bang"; confirmá con el usuario). Guardados en vocal_hits.json:')
    for a_, b_ in pairs:
        say(f'  {a_:7.2f}s / {b_:7.2f}s')

    info = song_info(song, dur, grid, tempo_segs, sync, gaps, first, fdb, bdb)
    json.dump(info, open('song.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    sg = info['suggest']
    say('\nMomentos que entran solos como SYNC si edit.json no trae song.sync: ' + ', '.join(f'{x:.2f}' for x in info['sync']))
    say(f"\nSugerencia para el edit (song.json): arrancar el video en {sg['start']:.2f}s, primer drop {sg['drop1']:.2f}s, "
        f"drop principal {sg['drop2']:.2f}s. Compás: el 1 cae en los beats {info['bar_phase']} + 4n.")
    say('Energía por sección (0 = calma, 1 = todo):')
    for s in info['sections']:
        say(f"  {s['t0']:6.1f}s - {s['t1']:6.1f}s   {s['energy']:.2f}  {s['label']}")
    return info


def song_info(song, dur, grid, tempo_segs, sync, gaps, first, fdb, bdb):
    """Lo que el planificador y el armado automático necesitan de la canción, sin volver a analizarla."""
    NB = len(grid) - 1
    # energía beat por beat, 0-1: volumen total con algo de peso de los graves, entre el piso y el techo de la canción
    e = 0.7 * fdb + 0.3 * bdb
    lo_, hi_ = np.percentile(e, 10), np.percentile(e, 95)
    en = np.clip((e - lo_) / max(1e-6, hi_ - lo_), 0, 1)
    en = np.convolve(np.pad(en, 2, mode='edge'), np.ones(5) / 5, 'valid')          # suavizado de un compás
    # secciones: entre un momento fuerte y el siguiente
    strong = [c['t'] for c in sync if c['fuerza'] >= SYNC_MIN]
    cuts = [float(grid[0])] + [x for x in strong if x - grid[0] > 2] + [float(grid[NB])]
    sections = []
    for t0, t1 in zip(cuts, cuts[1:]):
        if t1 - t0 < 1.0: continue
        m = (grid[:NB] >= t0) & (grid[:NB] < t1)
        v = float(en[m].mean()) if m.any() else 0.0
        sections.append(dict(t0=round(t0, 3), t1=round(t1, 3), energy=round(v, 3),
                             label='calma' if v < 0.35 else ('media' if v < 0.7 else 'alta')))
    # dónde arrancar: primer drop = el momento "entra la batería"; drop principal = la vuelta del bombo más fuerte de la
    # segunda mitad (después del corte más largo), con lugar para el cierre; el video arranca 16 beats antes del primero
    def settle(i):
        """El drop es el primer beat que ya suena con todo el bajo (la subida suele marcarse un beat antes)."""
        for q in range(i, min(NB - 5, i + 3)):
            if bdb[q] >= bdb[q + 1:q + 5].mean() - 3: return q
        return i
    d1 = first['t'] if first else (strong[0] if strong else float(grid[min(32, NB)]))
    i1 = settle(int(np.argmin(abs(grid - d1))))
    d1 = float(grid[i1])
    auto = [t for t in pick_sync(sync, gaps, grid, fdb, bdb) if t >= d1 - 0.5]
    # drop principal: de los momentos fuertes de la segunda parte que dejan al menos 38 s de canción para el acto 2, el
    # que deja la canción más arriba y sube más desde lo que venía (probado contra los drops elegidos a mano)
    def jump(t):
        i = int(np.argmin(abs(grid - t))); after = float(en[i:i + 16].mean())
        return after + 0.5 * (after - float(en[max(0, i - 8):i].mean()))
    late = [t for t in auto if max(d1 + 30, dur * 0.4) < t <= dur - 38]
    if not late:
        late = [float(grid[settle(int(np.argmin(abs(grid - c['t']))))]) for c in sync if max(d1 + 30, dur * 0.4) < c['t'] <= dur - 38]
    d2 = max(late, key=jump) if late else float(grid[min(NB, i1 + 192)])
    back = next((k for k in (16, 12, 8) if i1 - k >= 0), 4)
    return dict(song=song, duration=round(dur, 3), bpm=tempo_segs[0]['bpm'], tempo=tempo_segs,
                tempo_fixed=len(tempo_segs) == 1, bar_phase=int(i1 % 4),
                suggest=dict(start=round(float(grid[i1 - back]), 3), drop1=round(float(grid[i1]), 3),
                             drop2=round(float(grid[int(np.argmin(abs(grid - d2)))]), 3)),
                sync=auto,
                sections=sections, energy_beats=[round(float(x), 3) for x in en],
                level_beats=[round(float(x), 1) for x in fdb], bass_beats=[round(float(x), 1) for x in bdb],
                candidates=[dict(c, gap=round(float(g), 2)) for c, g in zip(sync, gaps)])


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    analyze(sys.argv[1])
