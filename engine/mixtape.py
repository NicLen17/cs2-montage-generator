"""Mezcla de varias canciones para un solo edit: las mejores partes de cada una, unidas con fundidos.

    python engine/mixtape.py projects/<nombre>          lee projects/<nombre>/mix.json y escribe la canción del proyecto

mix.json:
    {"lufs": -10, "crossfade": 1.2,
     "sections": [{"from": "projects/my_jealousy_v4", "a": 8.05, "b": 56.05, "sync": [16.05, 32.05, 48.05], "name": "My Jealousy"},
                  {"from": "projects/caffeine_rush", "a": 23.88, "b": 74.17, "sync": [28.45, 37.6, 58.17]}]}
Cada sección es un tramo [a, b) de la canción de otro proyecto ya analizado (su song.mp3, grid.npy, hits.npy y, si
tiene, song.json). "sync" son sus momentos fuertes, en segundos de esa canción.

Deja en el proyecto lo mismo que deja analyze_song.py para una canción sola, así el resto del motor no cambia:
    song.mp3    las secciones a un mismo loudness, cada una entrando mientras la anterior se va (fundido de igual potencia)
    grid.npy, hits.npy, beats.npy   los beats de cada sección puestos en el tiempo de la mezcla
    song.json   duración, energía beat por beat, "sync" (los momentos fuertes en tiempo de la mezcla) y "mix": dónde
                empieza y termina cada sección, para ubicar los cambios de canción en el plan
Los cambios de tempo entre canciones no se disimulan: cada cambio es un momento del edit (transición fuerte + kill en el
drop de la canción que entra), por eso conviene que cada sección empiece unos beats antes de su drop.
"""
import json, os, re, subprocess, sys

import numpy as np

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
SR = 48000


def decode(path, a, b):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{max(0.0, a):.4f}', '-t', f'{b - max(0.0, a):.4f}', '-i', path, '-ac', '2', '-ar', str(SR),
                        '-f', 'f32le', '-'], capture_output=True)
    x = np.frombuffer(r.stdout, np.float32).reshape(-1, 2).astype(np.float64)
    if a < 0: x = np.vstack([np.zeros((int(-a * SR), 2)), x])
    return x


def lufs(x):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-', '-af', 'ebur128', '-f', 'null', '-'],
                       input=x.astype(np.float32).tobytes(), capture_output=True).stderr.decode('utf-8', 'replace')
    m = re.findall(r'I:\s+(-?[\d.]+) LUFS', r)
    return float(m[-1]) if m else None


def soft_limit(x, ceiling=0.97):
    """Limitador suave: lo que pasa de 0.8 se curva hasta el techo (una sección subida de volumen no recorta)."""
    k = 0.8; a = np.abs(x); over = a > k
    y = x.copy()
    y[over] = np.sign(x[over]) * (k + (ceiling - k) * np.tanh((a[over] - k) / (ceiling - k)))
    return y


def build(project):
    project = os.path.abspath(project)
    spec = json.load(open(os.path.join(project, 'mix.json'), encoding='utf-8'))
    xf = float(spec.get('crossfade', 1.2)); target = float(spec.get('lufs', -10)); h = xf / 2
    parts, grid, hits, energy, sync, sections = [], [], [], [], [], []
    t0 = 0.0                                  # dónde cae el "a" de la sección en la mezcla
    N = len(spec['sections'])
    for k, s in enumerate(spec['sections']):
        src = s['from'] if os.path.isabs(s['from']) else os.path.join(ROOT, s['from'])
        a, b = float(s['a']), float(s['b'])
        pre = h if k > 0 else 0.0; post = h if k < N - 1 else 0.0        # medio fundido de cada lado
        x = decode(os.path.join(src, 'song.mp3'), a - pre, b + post)
        core = x[int(pre * SR):int((pre + b - a) * SR)]
        L = lufs(core)
        if L is not None: x = soft_limit(x * 10 ** ((target - L) / 20))
        n = len(x); env = np.ones(n)
        if k > 0: m = int(xf * SR); env[:m] = np.sin(np.linspace(0, np.pi / 2, m))
        if k < N - 1: m = int(xf * SR); env[-m:] *= np.cos(np.linspace(0, np.pi / 2, m))
        parts.append((int(round((t0 - pre) * SR)), x * env[:, None]))
        g = np.load(os.path.join(src, 'grid.npy')); hh = np.load(os.path.join(src, 'hits.npy'))
        keep = (g >= a - 1e-6) & (g < b - 1e-6)
        grid += list(g[keep] - a + t0); hits += list(hh[keep] - a + t0)
        info = json.load(open(os.path.join(src, 'song.json'), encoding='utf-8')) if os.path.exists(os.path.join(src, 'song.json')) else {}
        eb = info.get('energy_beats') or []
        idx = np.nonzero(keep)[0]
        energy += [float(eb[i]) if i < len(eb) else 0.7 for i in idx]
        mine = [round(float(t) - a + t0, 3) for t in s.get('sync', []) if a <= t < b]
        sync += mine
        sections.append(dict(name=s.get('name') or os.path.basename(src), t0=round(t0, 3), t1=round(t0 + b - a, 3), song_a=a, song_b=b,
                             bpm=info.get('bpm'), lufs_in=L, sync=mine))
        t0 += b - a
    total = t0
    out = np.zeros((int(total * SR) + 2, 2))
    for i0, x in parts:
        a_ = max(0, i0); x = x[a_ - i0:]; n = min(len(x), len(out) - a_)
        out[a_:a_ + n] += x[:n]
    out = soft_limit(out)
    wav = os.path.join(project, 'song_mix.wav')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-', wav], input=out.astype(np.float32).tobytes(), check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav, '-b:a', '320k', os.path.join(project, 'song.mp3')], check=True)
    os.remove(wav)
    grid = np.array(grid); hits = np.array(hits)
    for f, v in (('grid.npy', grid), ('hits.npy', hits), ('beats.npy', grid)): np.save(os.path.join(project, f), v)
    # el mp3 agrega un retardo de codificación de unos milisegundos: se mide y queda anotado
    info = dict(song='song.mp3', duration=round(total, 3), bpm=sections[0]['bpm'], tempo=[dict(t0=s['t0'], t1=s['t1'], bpm=s['bpm']) for s in sections],
                tempo_fixed=False, sync=sorted(sync), energy_beats=[round(e, 3) for e in energy], mix=sections,
                suggest=dict(start=0.0, drop1=sync[0] if sync else float(grid[16]), drop2=sorted(sync)[len(sync) * 2 // 3] if sync else float(grid[-64])),
                sections=[dict(t0=s['t0'], t1=s['t1'], energy=round(float(np.mean([e for g_, e in zip(grid, energy) if s['t0'] <= g_ < s['t1']] or [0.7])), 3),
                               label=s['name']) for s in sections])
    json.dump(info, open(os.path.join(project, 'song.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    json.dump([dict(t=t, tipo='momento fuerte de la mezcla', fuerza=10.0) for t in sorted(sync)], open(os.path.join(project, 'sync.json'), 'w', encoding='utf-8'), indent=1)
    return info


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    if len(sys.argv) < 2: raise SystemExit(__doc__)
    info = build(sys.argv[1])
    print(f"Mezcla: {len(info['mix'])} secciones, {int(info['duration'] // 60)}:{info['duration'] % 60:04.1f}")
    for s in info['mix']:
        print(f"  {s['t0']:6.1f}s - {s['t1']:6.1f}s  {s['name']:22} {s['bpm']} BPM  (era {s['lufs_in']} LUFS)  momentos: {', '.join(f'{t:.2f}' for t in s['sync'])}")
