"""Short vertical 9:16 (TikTok, Reels, YouTube Shorts) a partir del edit terminado.

    python engine/short.py projects/<nombre>                       -> elige solo el mejor tramo (~45 s) y renderiza
    python engine/short.py projects/<nombre> --list                -> solo muestra los tramos candidatos con su puntaje
    python engine/short.py projects/<nombre> --start 1:52 --dur 40 -> tramo fijo
    opciones: --dur 45  --layout fit|cam  --video output/x.mp4  --name x_short.mp4  --no-text

Toma la imagen y el audio del video final (output/<nombre>.mp4), así que conserva efectos, sincronía y mezcla.
  fit (por defecto): fondo desenfocado + el cuadro completo a 1080 de ancho en el centro (se ve todo, killfeed incluido),
                     "WAKO TV" y el tema arriba, twitch.tv/el_wako abajo.
  cam: cámara del streamer arriba (zoom 2x, el máximo permitido) y el centro del gameplay abajo a tamaño real.
       Solo sirve si en todo el tramo la cámara está en la posición por defecto (25,18)-(490,278).
El tramo empieza después de una transición y termina antes de la siguiente; nunca corta una play por la mitad.
Salida: output/<nombre>_short.mp4 (1080x1920, 60 fps) y projects/<nombre>/short_sheet.jpg para revisarlo.
"""
import os, sys, argparse, subprocess, importlib.util, io, contextlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)
from encoders import video_encoder_args

FD = os.path.join(ENGINE, 'assets', 'fonts')
F800, F600 = os.path.join(FD, 'montserrat-latin-800-normal.woff'), os.path.join(FD, 'montserrat-latin-600-normal.woff')
CAM_DEF = (25, 18, 490, 278)


def load_plan(project):
    spec = importlib.util.spec_from_file_location('plan', os.path.join(project, 'plan.py'))
    cwd = os.getcwd(); os.chdir(project); sys.path.insert(0, project)
    m = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(m)
    os.chdir(cwd)
    return m


def parse_t(s):
    if ':' in s:
        a, b = s.split(':'); return int(a) * 60 + float(b)
    return float(s)


def fmt(t):
    return f'{int(t // 60)}:{t % 60:05.2f}'


def candidates(p, dur):
    """Tramos que arrancan al inicio de una play y terminan al final de otra, cerca de `dur` segundos."""
    segs = p.segments
    starts = [s['o0'] for s in segs if s['kind'] in ('play', 'zoom_out') and s.get('first', True) and s['play'] >= 0]
    starts += [s['o1'] for s in segs if s['kind'] == 'interlude']          # el drop después del negro
    ends = sorted({s['o1'] for s in segs if s['kind'] in ('play', 'slowmo', 'face_out')})
    bounds = [b[0] for b in getattr(p, 'boundaries', [])]
    outro = next((s['o0'] for s in segs if s['kind'] == 'outro'), p.TOTAL)
    inter = [(s['o0'], s['o1']) for s in segs if s['kind'] == 'interlude']
    kills = np.array(p.kills); caps = [o for o, _ in p.captions]
    drops = [P['kill_at'] - p.SONG_A0 for P in list(p.ACT1) + list(p.ACT2) if 'kill_at' in P] + [ib for ia, ib in inter]
    out = []
    for a in sorted(set(starts)):
        ok_end = [e for e in ends if dur - 10 <= e - a <= dur + 10 and e <= outro + 0.01]
        if not ok_end: continue
        e = min(ok_end, key=lambda x: abs(x - a - dur))
        if any(ia < e and ib > a + 0.5 for ia, ib in inter): continue         # no meter el negro del interludio en el medio
        a2 = a + 0.2 if any(abs(b - a) < 0.05 for b in bounds) else a          # salir de la transición de entrada
        e2 = e - 0.15 if any(abs(b - e) < 0.05 for b in bounds) else e
        nk = int(((kills >= a2) & (kills <= e2)).sum()); nc = sum(a2 <= c <= e2 for c in caps)
        first_k = kills[kills >= a2].min() if (kills >= a2).any() else e2
        hook = max(0.0, first_k - a2)                                         # segundos hasta la primera kill (gancho)
        drop = any(a2 <= d_ <= a2 + 2.5 for d_ in drops)                     # arranca con un drop: mejor gancho
        score = nk / (e2 - a2) * 30 + 2.5 * nc - 1.5 * max(0, hook - 1.5) + (3 if drop else 0)
        out.append(dict(a=a2, e=e2, kills=nk, caps=nc, hook=hook, drop=drop, score=score))
    return sorted(out, key=lambda c: -c['score'])


def overlay_png(path, title, layout, text=True):
    im = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
    if text and layout == 'fit':
        d = ImageDraw.Draw(im)
        def center(txt, font, y, fill, spacing=0):
            w = sum(font.getlength(ch) for ch in txt) + spacing * (len(txt) - 1); x = (1080 - w) / 2
            sh = Image.new('RGBA', im.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(sh); xx = x
            for ch in txt: ds.text((xx, y + 4), ch, font=font, fill=(0, 0, 0, 170)); xx += font.getlength(ch) + spacing
            im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
            for ch in txt: d.text((x, y), ch, font=font, fill=fill); x += font.getlength(ch) + spacing
        center('WAKO TV', ImageFont.truetype(F800, 96), 360, (255, 255, 255, 255), 10)
        center(title.upper(), ImageFont.truetype(F600, 40), 485, (225, 205, 255, 255), 8)
        center('twitch.tv/el_wako', ImageFont.truetype(F600, 40), 1380, (255, 255, 255, 235), 4)
    im.save(path)


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    ap = argparse.ArgumentParser()
    ap.add_argument('project'); ap.add_argument('--start'); ap.add_argument('--dur', type=float, default=45.0)
    ap.add_argument('--layout', default='fit', choices=['fit', 'cam']); ap.add_argument('--video'); ap.add_argument('--name')
    ap.add_argument('--list', action='store_true'); ap.add_argument('--no-text', action='store_true')
    a = ap.parse_args()
    project = os.path.abspath(a.project); name = os.path.basename(project); p = load_plan(project)
    video = a.video or os.path.join(ROOT, 'output', name + '.mp4')
    if not os.path.exists(video): raise SystemExit(f'No existe {video}: renderizá primero el edit (engine/build.py).')

    if a.start:
        t0 = parse_t(a.start); t1 = min(p.TOTAL, t0 + a.dur)
    else:
        cs = candidates(p, a.dur)
        if not cs: raise SystemExit('No encontré un tramo que empiece y termine en límites de play; usá --start y --dur.')
        print('Tramos candidatos (mejor primero):')
        for c in cs[:6]:
            print(f'  {fmt(c["a"])} → {fmt(c["e"])}  ({c["e"] - c["a"]:.1f} s)  kills={c["kills"]}  títulos={c["caps"]}  '
                  f'primera kill a {c["hook"]:.1f} s{"  arranca en drop" if c["drop"] else ""}  puntaje={c["score"]:.1f}')
        if a.list: return
        t0, t1 = cs[0]['a'], cs[0]['e']
    D = t1 - t0
    if D > 60: print(f'Aviso: {D:.0f} s pasa de 60 s (algunas plataformas lo toman como video normal).')
    print(f'Short: {fmt(t0)} → {fmt(t1)} ({D:.1f} s), layout {a.layout}')

    ov = os.path.join(project, 'short_overlay.png'); overlay_png(ov, getattr(p, 'SONG_TITLE', ''), a.layout, not a.no_text)
    fo = max(0.0, D - 1.0)
    if a.layout == 'fit':
        fc = ('[0:v]split[a][b];'
              '[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2,eq=brightness=-0.10:saturation=1.15[bg];'
              '[b]scale=1080:-2:flags=lanczos[fg];'
              '[bg][fg]overlay=0:(H-h)/2[v1];[v1][1:v]overlay=0:0')
    else:
        x0, y0, x1, y1 = CAM_DEF; cw, ch = x1 - x0, y1 - y0
        fc = ('[0:v]split=3[a][b][c];'
              '[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2,eq=brightness=-0.15[bg];'
              f'[b]crop={cw}:{ch}:{x0}:{y0},scale={2 * cw}:{2 * ch}:flags=lanczos[cam];'
              '[c]crop=1080:1080:420:0[gp];'
              f'[bg][cam]overlay=(W-w)/2:{(840 - 2 * ch) // 2}[v1];[v1][gp]overlay=0:840[v2];[v2][1:v]overlay=0:0')
    fc += f',fade=t=in:st=0:d=0.2,fade=t=out:st={fo:.3f}:d=1.0,format=yuv420p[v]'
    out = os.path.join(ROOT, 'output', a.name or f'{name}_short.mp4')
    cmd = ['ffmpeg', '-v', 'error', '-y', '-ss', f'{t0:.3f}', '-t', f'{D:.3f}', '-i', video, '-loop', '1', '-i', ov,
           '-filter_complex', fc, '-map', '[v]', '-map', '0:a',
           '-af', f'afade=t=in:st=0:d=0.25,afade=t=out:st={fo:.3f}:d=1.0',
           *video_encoder_args('final', 16), '-r', str(p.FPS), '-c:a', 'aac', '-b:a', '256k', '-shortest', '-movflags', '+faststart', out]
    r = subprocess.run(cmd)
    if r.returncode != 0: raise SystemExit('Falló ffmpeg')
    os.remove(ov)
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out],
                               capture_output=True, text=True).stdout or 0)
    sheet = os.path.join(project, 'short_sheet.jpg')
    step = max(1.0, dur / 8)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', out, '-vf', f'fps=1/{step:.3f},scale=270:480,tile=8x1', '-frames:v', '1', sheet])
    print(f'Listo: {out}  ({dur:.1f} s, {os.path.getsize(out) / 2**20:.0f} MB)\nHoja para revisar: {sheet}')


if __name__ == '__main__':
    main()
