"""Reacciones de los clips: gritos, festejos y aliento después de la última kill de una play.

    python engine/reactions.py projects/<nombre>              # clips que usa el plan
    python engine/reactions.py projects/<nombre> --all        # todos los clips con kills en kf.json
    python engine/reactions.py projects/<nombre> --clips 3,8  # solo esos

1. Separa la voz del juego en el audio de cada clip con Demucs (htdemucs, dos pistas) y lo guarda en
   `clip_stems/cN/vocals.wav` y `no_vocals.wav` (se reusa si el clip no cambió).
2. Busca en la pista de voz los tramos claramente más fuertes que la charla normal del clip ("vamooo", gritos,
   aliento) que duran lo suficiente para no ser un tiro que se coló, y mide si son GRUPALES: una segunda voz
   que suena al mismo tiempo con altura propia. Solo las grupales se resaltan (pedido del usuario, 20/11/2026).
3. Se queda solo con los que arrancan en la culminación de una play: desde 0.3 s antes de una kill que cierra
   una racha (la siguiente kill está a más de 3 s, o no hay) hasta 3.5 s después. Nunca en medio de la play.
4. Escribe `reactions.json` ({clip: [{t0, t1, peak, db, kill, kind}]}). `audio.py` lo usa para levantar esas
   voces por encima de la música solo en ese momento (ver la skill cs2-edit, §8).
"""
import os, sys, json, subprocess, io, contextlib, argparse
import numpy as np
from scipy.ndimage import uniform_filter1d, binary_closing

ap = argparse.ArgumentParser()
ap.add_argument('project')
ap.add_argument('--all', action='store_true')
ap.add_argument('--clips', default='')
ap.add_argument('--quiet', action='store_true')
args = ap.parse_args()
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
PROJECT = os.path.abspath(args.project)
STEMS = os.path.join(PROJECT, 'clip_stems')
SR = 16000
HOP = 0.01

kf = {int(k): v for k, v in json.load(open(os.path.join(PROJECT, 'kf.json'))).items()}


def plan_clips():
    sys.path.insert(0, PROJECT); cwd = os.getcwd(); os.chdir(PROJECT)
    argv = sys.argv; sys.argv = [argv[0]]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import plan
        return sorted({s['clip'] for s in plan.segments if s['kind'] not in ('logo', 'interlude', 'outro') and s['clip']})
    finally:
        os.chdir(cwd); sys.argv = argv


if args.clips:
    clips = [int(c) for c in args.clips.split(',')]
elif args.all or not os.path.exists(os.path.join(PROJECT, 'plan.py')):
    clips = sorted(c for c in kf if kf[c] and os.path.exists(os.path.join(PROJECT, 'clips', f'c{c}.mp4')))
else:
    clips = plan_clips()


# ---------- 1. separar voz y juego con Demucs ----------
def stem_ok(c):
    src = os.path.join(PROJECT, 'clips', f'c{c}.mp4'); v = os.path.join(STEMS, f'c{c}', 'vocals.wav')
    return os.path.exists(v) and os.path.getmtime(v) >= os.path.getmtime(src)


todo = [c for c in clips if not stem_ok(c)]
if todo:
    tmp = os.path.join(STEMS, '_wav'); os.makedirs(tmp, exist_ok=True)
    wavs = []
    for c in todo:
        w = os.path.join(tmp, f'c{c}.wav'); wavs.append(w)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(PROJECT, 'clips', f'c{c}.mp4'), '-vn',
                        '-ac', '2', '-ar', '44100', w], check=True)
    print(f'Demucs: separando la voz de {len(todo)} clips (CPU, ~10-20 s por clip)...', flush=True)
    subprocess.run([sys.executable, '-m', 'demucs', '--two-stems=vocals', '-n', 'htdemucs', '-o', tmp] + wavs, check=True,
                   stdout=subprocess.DEVNULL if args.quiet else None)
    for c in todo:
        d = os.path.join(STEMS, f'c{c}'); os.makedirs(d, exist_ok=True)
        for st in ('vocals', 'no_vocals'):
            os.replace(os.path.join(tmp, 'htdemucs', f'c{c}', f'{st}.wav'), os.path.join(d, f'{st}.wav'))
        os.remove(os.path.join(tmp, f'c{c}.wav'))


def load(path):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-ac', '1', '-ar', str(SR), '-'],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def env_db(x, win):
    h = int(HOP * SR); n = len(x) // h
    p = uniform_filter1d(x[:n * h] ** 2, int(win * SR))[::h][:n]
    return 10 * np.log10(p + 1e-10)


def flatness(x):
    """planitud espectral por cuadro de 40 ms: voz (armónica) baja, tiro o ruido alto"""
    h = int(HOP * SR); w = int(0.04 * SR); n = len(x) // h
    out = np.ones(n)
    win = np.hanning(w)
    for i in range(0, n):
        a = i * h; seg = x[a:a + w]
        if len(seg) < w: break
        s = np.abs(np.fft.rfft(seg * win))[5:120] + 1e-9      # 200-3000 Hz
        out[i] = np.exp(np.mean(np.log(s))) / np.mean(s)
    return out


# ---------- voces simultáneas: grupal o individual ----------
_N = 2048; _HOP = 320
_F0 = 80 * 2 ** (np.arange(0, int(12 * np.log2(900 / 80) * 4)) / 48)
_FR = np.fft.rfftfreq(_N, 1 / SR)


def _salience(mag):
    s = np.zeros(len(_F0))
    for h in range(1, 11):
        s += (0.84 ** (h - 1)) * np.interp(_F0 * h, _FR, mag, right=0)
    return s


def _related(a, b):
    """misma voz: octava, quinta o doceava (armónicos de una sola persona, la aspereza de un grito)"""
    st = abs(12 * np.log2(a / b))
    return min(st % 12, 12 - st % 12) < 0.8 or abs(st - 7) < 0.6 or abs(st - 19) < 0.6 or st < 2


def group_score(seg):
    """Fracción del grito en la que suena una SEGUNDA voz al mismo tiempo, con altura propia y continua (no un
    armónico ni la aspereza del grito de una sola persona), y el tramo continuo más largo de esa segunda voz.
    Multi-f0 iterativo: suma de armónicos → la voz más fuerte → se quitan sus armónicos → se busca otra."""
    w = np.hanning(_N); sec, rms = [], []
    for i in range(0, len(seg) - _N, _HOP):
        x = seg[i:i + _N]; rms.append(np.sqrt(np.mean(x ** 2)))
        mag = np.abs(np.fft.rfft(x * w)); mag /= mag.max() + 1e-12
        found = []; s0 = None
        for _ in range(3):
            sl = _salience(mag); j = int(np.argmax(sl))
            if s0 is None: s0 = sl[j]
            if sl[j] < 0.45 * s0: break
            found.append(_F0[j])
            for h in range(1, 11):
                mag[np.abs(_FR - _F0[j] * h) < max(15, _F0[j] * 0.03)] = 0
        others = [g for g in found[1:] if not _related(g, found[0])] if found else []
        sec.append(others[0] if others else None)
    if len(sec) < 3: return 0.0, 0.0
    rms = np.array(rms); loud = rms > rms.max() * 0.3
    cont = run = best = tot = 0
    for i in range(1, len(sec)):
        a, b = sec[i - 1], sec[i]; ok = bool(a and b and abs(12 * np.log2(a / b)) < 1.0)
        run = run + 1 if ok else 0; best = max(best, run)
        if loud[i]: tot += 1; cont += ok
    return cont / max(tot, 1), best * _HOP / SR


GROUP_MIN, GROUP_RUN = 0.20, 0.10      # calibrado en my_jealousy_v3: grupal 0.42 (c30); individuales 0.00-0.07


# ---------- 2-3. detectar reacciones al final de cada play ----------
def closing_kills(ks):
    """kills que cierran una racha: la siguiente está a más de 3 s (o es la última del clip)"""
    ks = sorted(ks)
    return [k for i, k in enumerate(ks) if i == len(ks) - 1 or ks[i + 1] - k > 3.0]


out = {}
for c in clips:
    v = load(os.path.join(STEMS, f'c{c}', 'vocals.wav'))
    g = load(os.path.join(STEMS, f'c{c}', 'no_vocals.wav'))
    ev = env_db(v, 0.06); eg = env_db(g, 0.06)
    active = ev > max(np.percentile(ev, 99) - 45, -60)          # hay alguien hablando
    if active.sum() < 20:
        out[c] = []; continue
    speech = np.percentile(ev[active], 50)                       # charla normal del clip
    loud = np.percentile(ev[active], 97)
    thr = max(speech + 8.0, min(loud, speech + 14.0) - 1.0)
    fl = flatness(v)[:len(ev)]
    hot = binary_closing(ev > thr, np.ones(int(0.25 / HOP), bool))
    # bordes de cada tramo caliente
    d = np.diff(np.r_[0, hot.astype(int), 0]); starts = np.where(d == 1)[0]; ends = np.where(d == -1)[0]
    ck = closing_kills(kf.get(c, []))
    evs = []
    for a, b in zip(starts, ends):
        dur = (b - a) * HOP
        voiced = np.median(fl[a:b]) < 0.35
        if dur < 0.22 or not voiced: continue                    # un tiro colado en la pista de voz: corto y ruidoso
        t0 = a * HOP; t1 = b * HOP
        kill = next((k for k in ck if k - 0.3 <= t0 <= k + 3.5), None)
        if kill is None: continue                                # en medio de una play o lejos de una kill: no
        # extender a la cola natural del grito (hasta que cae 10 dB del pico, máximo 2.5 s desde el inicio)
        pk = ev[a:b].max(); j = b
        while j < len(ev) and ev[j] > pk - 10 and (j - a) * HOP < 2.5: j += 1
        t1 = j * HOP
        over = pk - speech
        evs.append(dict(t0=round(t0, 2), t1=round(t1, 2), kill=kill, j=sorted(kf[c]).index(kill), db=round(float(over), 1),
                        peak=round(float(pk), 1), voice_vs_game=round(float(np.mean(ev[a:b] - eg[a:b])), 1),
                        kind='grito' if over >= 13 else 'reaccion'))
    # dos tramos del mismo festejo (pausa para respirar) se unen
    merged = []
    for e in evs:
        if merged and e['kill'] == merged[-1]['kill'] and e['t0'] - merged[-1]['t1'] < 0.6:
            m = merged[-1]; m['t1'] = max(m['t1'], e['t1']); m['db'] = max(m['db'], e['db']); m['peak'] = max(m['peak'], e['peak'])
            m['kind'] = 'grito' if m['db'] >= 13 else 'reaccion'
        else:
            merged.append(e)
    for e in merged:
        sc, rn = group_score(v[int(e['t0'] * SR):int(e['t1'] * SR)])
        e['voices2'] = round(float(sc), 2); e['run2'] = round(float(rn), 2)
        e['group'] = bool(sc >= GROUP_MIN or rn >= GROUP_RUN)
        e['loud'] = e['kind']                       # grito (+13 dB o más) / reaccion
        e['kind'] = 'grupal' if e['group'] else 'individual'
    out[c] = merged

json.dump({str(k): v for k, v in out.items()}, open(os.path.join(PROJECT, 'reactions.json'), 'w'), indent=1)
print(f"{'clip':>5} {'inicio':>7} {'fin':>6} {'kill':>9} {'+dB':>5} {'2.a voz':>7}  {'tipo':10}  fin de tramo sugerido")
for c in clips:
    for e in out[c]:
        sug = round(min(e['t0'] + 0.9, e['t1']), 2) if e['group'] else '— (individual: no se resalta)'
        print(f"c{c:<4} {e['t0']:7.2f} {e['t1']:6.2f} {e['kill']:6.2f}[{e['j']}] {e['db']:5.1f} {e['voices2']:7.2f}  {e['kind']:10}  {sug}"
              + ('' if not e['group'] or e['t0'] - e['kill'] <= 1.8 else '  (llega tarde: solo si ya entra, p. ej. en el cierre)'))
    if not out[c] and not args.quiet:
        print(f"c{c:<4}   (sin reacción al final de una play)")
print('->', os.path.join(PROJECT, 'reactions.json'))
