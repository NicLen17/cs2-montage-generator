"""Short vertical 9:16 (TikTok, Reels, YouTube Shorts) a partir del edit terminado.

    python engine/short.py projects/<nombre>                       -> elige solo el mejor tramo (~45 s) y renderiza
    python engine/short.py projects/<nombre> --list                -> solo muestra los tramos candidatos con su puntaje
    python engine/short.py projects/<nombre> --start 1:52 --dur 40 -> tramo fijo
    python engine/short.py projects/<nombre> --count auto --dur 35 -> varios shorts que no se pisan (2 a 4): <nombre>_short1.mp4, ...
    opciones: --dur 45  --layout fit|cam  --video output/x.mp4  --name x_short.mp4  --no-text

Toma la imagen y el audio del video final (output/<nombre>.mp4), así que conserva efectos, sincronía y mezcla.
  fit (por defecto): fondo desenfocado + el cuadro completo a 1080 de ancho en el centro (se ve todo, killfeed incluido),
                     "WAKO TV" y el tema arriba, twitch.tv/el_wako abajo.
  cam: cámara del streamer arriba (zoom 2x, el máximo permitido) y el centro del gameplay abajo a tamaño real.
       Solo sirve si en todo el tramo la cámara está en la posición por defecto (25,18)-(490,278).
El tramo empieza después de una transición y termina antes de la siguiente; nunca corta una play por la mitad.
Salida: output/<nombre>_short.mp4 (o _short1, _short2... con --count) a 1080x1920 y 60 fps, una hoja por short en
projects/<nombre>/ y projects/<nombre>/shorts.json con tramos, kills y títulos de cada uno.
"""
import os, sys, json, argparse, subprocess, importlib.util, io, contextlib
from concurrent.futures import ThreadPoolExecutor
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
    # solo el final de una play completa: el final de una toma interna (corte dentro de la misma play) dejaba
    # afuera kills de la play (un ACE mostrado con 3 de 5 kills)
    ends = sorted({s['o1'] for i, s in enumerate(segs) if s['kind'] in ('play', 'slowmo', 'face_out')
                   and (i == len(segs) - 1 or segs[i + 1]['play'] != s['play'] or segs[i + 1]['kind'] in ('interlude', 'outro'))})
    bounds = [b[0] for b in getattr(p, 'boundaries', [])]
    outro = next((s['o0'] for s in segs if s['kind'] == 'outro'), p.TOTAL)
    inter = [(s['o0'], s['o1']) for s in segs if s['kind'] == 'interlude']
    kills = np.array(p.kills); caps = [o for o, _ in p.captions]
    drops = [P['kill_at'] - p.SONG_A0 for P in list(p.ACT1) + list(p.ACT2) if 'kill_at' in P] + [ib for ia, ib in inter]
    rev = getattr(p, 'REVEAL', False) and hasattr(p, 'O_DROP2')                # revelación: la play arranca chica y oscura
    if rev: drops.append(p.O_DROP2)
    drops += [x - p.SONG_A0 for x in getattr(p, 'SYNC', [])]
    out = []
    for a in sorted(set(starts)):
        ok_end = [e for e in ends if dur - 10 <= e - a <= dur + 10 and e <= outro + 0.01]
        if not ok_end: continue
        e = min(ok_end, key=lambda x: abs(x - a - dur))
        if any(ia < e and ib > a + 0.5 for ia, ib in inter): continue         # no meter el negro del interludio en el medio
        a2 = a + 0.2 if any(abs(b - a) < 0.05 for b in bounds) else a          # salir de la transición de entrada
        if (any(abs(ib - a) < 0.01 for ia, ib in inter) or (rev and abs(a - p.INTER[0]) < 0.01)) and hasattr(p, 'O_DROP2'):
            a2 = max(a2, p.O_DROP2 - 0.9)                                     # después del negro: arrancar ya revelado, 0.9 s antes de la kill del drop
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
    ap.add_argument('--count', default='1', help="cantidad de shorts sin pisarse, o 'auto' (2 a 4, los buenos)")
    a = ap.parse_args()
    project = os.path.abspath(a.project); name = os.path.basename(project); p = load_plan(project)
    video = a.video or os.path.join(ROOT, 'output', name + '.mp4')
    if not os.path.exists(video): raise SystemExit(f'No existe {video}: renderizá primero el edit (engine/build.py).')

    if a.start:
        picks = [dict(a=parse_t(a.start), e=min(p.TOTAL, parse_t(a.start) + a.dur), kills=0, caps=0)]
    else:
        cs = candidates(p, a.dur)
        if not cs: raise SystemExit('No encontré un tramo que empiece y termine en límites de play; usá --start y --dur.')
        print('Tramos candidatos (mejor primero):')
        for c in cs[:8]:
            print(f'  {fmt(c["a"])} → {fmt(c["e"])}  ({c["e"] - c["a"]:.1f} s)  kills={c["kills"]}  títulos={c["caps"]}  '
                  f'primera kill a {c["hook"]:.1f} s{"  arranca en drop" if c["drop"] else ""}  puntaje={c["score"]:.1f}')
        picks = pick_shorts(cs, a.count)
        if a.list:
            print('Se elegirían:', ', '.join(f'{fmt(c["a"])}-{fmt(c["e"])}' for c in picks)); return
    multi = len(picks) > 1 or a.count != '1'
    jobs = []
    for i, c in enumerate(picks, 1):          # short1 = el de mejor puntaje (el primero que conviene publicar)
        suf = f'_short{i}' if multi else '_short'
        out = os.path.join(ROOT, 'output', a.name if (a.name and not multi) else f'{name}{suf}.mp4')
        sheet = os.path.join(project, f'short{i if multi else ""}_sheet.jpg')
        jobs.append((c, out, sheet))
    def run(job):
        c, out, sheet = job
        return render_short(p, project, video, c['a'], c['e'], a.layout, not a.no_text, out, sheet)
    with ThreadPoolExecutor(min(3, len(jobs))) as ex:
        res = list(ex.map(run, jobs))
    info = [dict(n=i + 1, desde=fmt(c['a']), hasta=fmt(c['e']), dur=round(d, 1), kills=c.get('kills'), titulos=[cp for o, cp in p.captions if c['a'] <= o <= c['e']],
                 archivo=out, hoja=sheet) for i, ((c, out, sheet), d) in enumerate(zip(jobs, res))]
    json.dump(info, open(os.path.join(project, 'shorts.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False, default=str)
    print(f'\n{len(info)} short(s). Detalle en {os.path.join(project, "shorts.json")}')


def pick_shorts(cs, count):
    """Elige tramos que no se pisan entre sí. count: un número, o 'auto' (los buenos: puntaje >= 60 % del mejor, 2 a 4)."""
    chosen = []
    for c in cs:
        if all(c['e'] <= o['a'] or c['a'] >= o['e'] for o in chosen): chosen.append(c)
    if count == 'auto':
        best = chosen[0]['score']
        good = [c for c in chosen if c['score'] >= 0.6 * best][:4]
        return good if len(good) >= 2 else chosen[:2]
    return chosen[:max(1, int(count))]


def render_short(p, project, video, t0, t1, layout, text, out, sheet):
    D = t1 - t0
    if D > 60: print(f'Aviso: {D:.0f} s pasa de 60 s (algunas plataformas lo toman como video normal).')
    print(f'Short: {fmt(t0)} → {fmt(t1)} ({D:.1f} s), layout {layout} → {os.path.basename(out)}', flush=True)
    ov = os.path.join(project, f'short_overlay_{os.path.basename(out)}.png'); overlay_png(ov, getattr(p, 'SONG_TITLE', ''), layout, text)
    fo = max(0.0, D - 1.0)
    if layout == 'fit':
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
    cmd = ['ffmpeg', '-v', 'error', '-y', '-ss', f'{t0:.3f}', '-t', f'{D:.3f}', '-i', video, '-loop', '1', '-i', ov,
           '-filter_complex', fc, '-map', '[v]', '-map', '0:a',
           '-af', f'afade=t=in:st=0:d=0.25,afade=t=out:st={fo:.3f}:d=1.0',
           *video_encoder_args('final', 16), '-r', str(p.FPS), '-c:a', 'aac', '-b:a', '256k', '-shortest', '-movflags', '+faststart', out]
    r = subprocess.run(cmd)
    os.remove(ov)
    if r.returncode != 0: raise SystemExit('Falló ffmpeg')
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out],
                               capture_output=True, text=True).stdout or 0)
    step = max(1.0, dur / 8)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', out, '-vf', f'fps=1/{step:.3f},scale=270:480,tile=8x1', '-frames:v', '1', sheet])
    print(f'Listo: {out}  ({dur:.1f} s, {os.path.getsize(out) / 2**20:.0f} MB)  hoja: {sheet}', flush=True)
    return dur


if __name__ == '__main__':
    main()
