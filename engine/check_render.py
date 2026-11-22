"""Revisión técnica del video renderizado (tirones, cuadros repetidos, volumen). Correr después de cada render final.

    python engine/check_render.py projects/<nombre> [output/<nombre>/video/<archivo>.mp4]

Reporta:
  - cuadros repetidos (imagen igual a la anterior mientras el resto se mueve) y en qué clip caen;
  - saltos bruscos de imagen fuera de los cortes: si caen sobre kills, el efecto de kill entra de golpe (tirón);
  - intervalos de tiempo irregulares (60 fps exactos) y duración contra el plan;
  - LUFS integrado y pico (meta: unos -9 a -10 LUFS, pico por debajo de -1 dBFS).
"""
import os, sys, subprocess, importlib.util
import numpy as np

ENGINE = os.path.dirname(os.path.abspath(__file__))


def load_plan(project):
    """edit.json (datos, lo arma planner.py) o, en proyectos anteriores, plan.py: ver engine/project.py."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import project as _project
    return _project.load_plan(project)


def frame_diffs(path):
    b = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vf', 'scale=160:90', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                       capture_output=True).stdout
    n = len(b) // (160 * 90)
    F = np.frombuffer(b[:n * 160 * 90], np.uint8).reshape(n, 90, 160).astype(np.float32)
    return np.abs(np.diff(F, axis=0)).mean((1, 2))


def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    project = os.path.abspath(sys.argv[1])
    sys.path.insert(0, ENGINE); import paths
    out = sys.argv[2] if len(sys.argv) > 2 else paths.find_video(os.path.basename(project))
    p = load_plan(project)
    d = frame_diffs(out)
    cuts = [s['o0'] for s in p.segments]
    kills = list(p.kills)
    def seg_at(t):
        for s in p.segments:
            if s['o0'] <= t < s['o1']: return s
    frozen, jumps = [], []
    for i in range(3, len(d) - 3):
        nb = np.median(np.r_[d[i - 3:i], d[i + 1:i + 4]])
        t = (i + 1) / p.FPS
        s = seg_at(t)
        if s is None or s['kind'] in ('logo', 'interlude', 'outro'): continue
        if nb > 1.5 and d[i] < 0.12 * nb: frozen.append((t, s['clip']))
        if d[i] > max(4 * nb, 6) and min(abs(t - c) for c in cuts) > 0.1: jumps.append(t)
    on_kill = [t for t in jumps if min([abs(t - k) for k in kills] or [9]) < 0.1]
    print(f'Cuadros repetidos: {len(frozen)}' + (f'  (ej: {[(round(t, 2), "c%d" % c) for t, c in frozen[:8]]})' if frozen else ''))
    print(f'Saltos fuera de cortes: {len(jumps)}, sobre kills: {len(on_kill)} de {len(kills)} kills'
          + (f'  (ej: {[round(t, 2) for t in on_kill[:10]]})' if on_kill else ''))
    if len(on_kill) > 0.3 * max(1, len(kills)):
        print('  ATENCIÓN: muchos saltos justo en las kills → algún efecto de kill entra de golpe (revisá la rampa de entrada en render.py).')
    pts = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'packet=pts_time', '-of', 'csv=p=0', out],
                         capture_output=True, text=True).stdout.split()
    tt = np.array(sorted(float(x) for x in pts if x)); dt = np.diff(tt)
    irregular = int((abs(dt - 1 / p.FPS) > 0.002).sum())
    dur = tt[-1] + 1 / p.FPS if len(tt) else 0
    print(f'Cuadros: {len(tt)}, intervalos irregulares: {irregular}, duración {dur:.2f}s (plan {p.TOTAL:.2f}s)'
          + ('  ATENCIÓN: no coincide' if abs(dur - p.TOTAL) > 0.5 else ''))
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', out, '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                       capture_output=True, text=True).stderr
    I = [l for l in r.splitlines() if l.strip().startswith('I:')]; P = [l for l in r.splitlines() if l.strip().startswith('Peak:')]
    if I and P:
        lufs = float(I[-1].split()[1]); peak = float(P[-1].split()[1])
        import preset
        tgt = preset.for_plan(p)['audio']['loudness']['target_lufs']
        print(f'Volumen: {lufs:.1f} LUFS, pico {peak:.1f} dBFS' + (f' (objetivo del preset: {tgt:g} LUFS)' if tgt is not None else '')
              + ('  → pico alto: bajá el audio con ffmpeg -c:v copy -af volume=-1.2dB' if peak > -1.0 else ''))


if __name__ == '__main__':
    main()
