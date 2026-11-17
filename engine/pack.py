"""Junta toda la entrega de un edit en una carpeta lista para subir: video, shorts, miniatura y textos por plataforma.

    python engine/pack.py projects/<nombre>       -> output/<nombre>_pack/  (+ LEEME.md con qué subir a cada lado)
    python engine/pack.py projects/<nombre> --check  -> solo dice qué falta, sin armar nada

Los videos se enlazan (hardlink) en vez de copiarse cuando el disco lo permite: no ocupan el doble.
Espera encontrar:
  output/<nombre>.mp4                         video principal (engine/build.py)
  projects/<nombre>/shorts.json               shorts (engine/short.py --count auto)
  projects/<nombre>/publish/thumbnail*.jpg    miniaturas (engine/publish.py thumb)
  projects/<nombre>/publish/youtube.md        título, descripción, capítulos y tags (lo escribe Claude)
  projects/<nombre>/publish/redes.md          textos de cada short para TikTok, Reels y YouTube Shorts (lo escribe Claude)
"""
import os, sys, json, shutil, subprocess

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)


def link(src, dst):
    if os.path.exists(dst): os.remove(dst)
    try: os.link(src, dst)
    except OSError: shutil.copy2(src, dst)


def dur(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path], capture_output=True, text=True)
    try: return float(r.stdout)
    except ValueError: return 0.0


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    project = os.path.abspath(sys.argv[1]); name = os.path.basename(project)
    pub = os.path.join(project, 'publish')
    video = os.path.join(ROOT, 'output', name + '.mp4')
    shorts = json.load(open(os.path.join(project, 'shorts.json'), encoding='utf-8')) if os.path.exists(os.path.join(project, 'shorts.json')) else []
    thumbs = sorted(f for f in os.listdir(pub) if f.startswith('thumbnail') and f.endswith('.jpg')) if os.path.isdir(pub) else []
    texts = {f: os.path.join(pub, f) for f in ('youtube.md', 'redes.md', 'info.json')}
    missing = []
    if not os.path.exists(video): missing.append(f'video principal ({video}) → engine/build.py')
    if not shorts or not all(os.path.exists(s['archivo']) for s in shorts): missing.append('shorts → engine/short.py --count auto')
    if 'thumbnail.jpg' not in thumbs: missing.append('miniatura → engine/publish.py thumb')
    for f in ('youtube.md', 'redes.md'):
        if not os.path.exists(texts[f]): missing.append(f'{f} → lo escribe Claude (skill yt-publish / cs2-pack)')
    chk = os.path.join(project, 'check_render.txt')
    if missing:
        print('Falta:'); [print('  -', m) for m in missing]
    if '--check' in sys.argv or missing:
        return 1 if missing else 0

    out = os.path.join(ROOT, 'output', f'{name}_pack'); os.makedirs(out, exist_ok=True)
    link(video, os.path.join(out, f'01_youtube_{name}.mp4'))
    for s in shorts:
        link(s['archivo'], os.path.join(out, f'02_short{s["n"]}_{name}.mp4'))
    for f in thumbs: shutil.copy2(os.path.join(pub, f), os.path.join(out, f))
    if os.path.exists(os.path.join(pub, 'thumbs_compare.jpg')): shutil.copy2(os.path.join(pub, 'thumbs_compare.jpg'), out)
    for f, pth in texts.items():
        if os.path.exists(pth): shutil.copy2(pth, out)

    L = [f'# Entrega: {name}', '', '## Archivos', '',
         f'| Archivo | Para | Duración |', '|---|---|---|',
         f'| `01_youtube_{name}.mp4` | YouTube (video largo, 1920×1080) | {dur(video):.0f} s |']
    for s in shorts:
        L.append(f'| `02_short{s["n"]}_{name}.mp4` | TikTok · Instagram Reels · YouTube Shorts (1080×1920) — tramo {s["desde"]}-{s["hasta"]} del edit | {s["dur"]:.0f} s |')
    L += [f'| `thumbnail.jpg` | miniatura del video largo (1280×720) | |',
          f'| `thumbs_compare.jpg` | las otras opciones de miniatura, a tamaño celular | |',
          f'| `youtube.md` | título, descripción con capítulos y tags | |',
          f'| `redes.md` | texto y hashtags de cada short por plataforma | |', '',
          '## Orden recomendado para subir', '',
          '1. **YouTube (largo):** subilo primero como *privado* o *no listado*, poné la miniatura y los textos de `youtube.md`, '
          'y mirá la pestaña "Comprobaciones" (Content ID por la canción) antes de publicarlo.',
          '2. **Shorts:** uno por día, del más fuerte al más flojo (el 1 es el de mejor puntaje), con los textos de `redes.md`. '
          'En YouTube Shorts vinculá el video largo ("video relacionado").',
          '3. **TikTok e Instagram Reels:** el mismo archivo de cada short; en Instagram elegí la portada desde el video.', '']
    if os.path.exists(chk):
        L += ['## Chequeo técnico del video largo', '', '```', open(chk, encoding='utf-8').read().strip(), '```', '']
    open(os.path.join(out, 'LEEME.md'), 'w', encoding='utf-8').write('\n'.join(L))
    print(f'Entrega lista en {out}')
    for f in sorted(os.listdir(out)): print('  ', f)
    return 0


if __name__ == '__main__':
    sys.exit(main())
