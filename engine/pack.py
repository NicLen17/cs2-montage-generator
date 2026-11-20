"""Deja lista la entrega de un edit en su carpeta de output/ (una por proyecto):

    output/<nombre>/video/   el edit largo (lo escribe engine/build.py)
    output/<nombre>/shorts/  los shorts verticales (lo escribe engine/short.py)
    output/<nombre>/info/    miniaturas, youtube.md, redes.md, info.json, check_render.txt y LEEME.md (este script)

    python engine/pack.py projects/<nombre>          -> completa info/ y escribe LEEME.md (qué subir a cada lado)
    python engine/pack.py projects/<nombre> --check  -> solo dice qué falta, sin escribir nada

Espera encontrar:
  output/<nombre>/video/<nombre>.mp4          video principal (engine/build.py)
  projects/<nombre>/shorts.json               shorts (engine/short.py --count auto)
  projects/<nombre>/publish/thumbnail*.jpg    miniaturas (engine/publish.py thumb)
  projects/<nombre>/publish/youtube.md        título, descripción, capítulos y tags (lo escribe Claude)
  projects/<nombre>/publish/redes.md          textos de cada short para TikTok, Reels y YouTube Shorts (lo escribe Claude)
Si encuentra el video o los shorts en el lugar viejo (sueltos en output/), los mueve a su carpeta.
"""
import os, sys, json, shutil, subprocess

ENGINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE)
import paths


def dur(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path], capture_output=True, text=True)
    try: return float(r.stdout)
    except ValueError: return 0.0


def adopt(src, dst):
    """Mueve un archivo del lugar viejo (suelto en output/) a su carpeta nueva."""
    if os.path.abspath(src) != os.path.abspath(dst) and os.path.exists(src) and not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
    return dst


def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    project = os.path.abspath(sys.argv[1]); name = os.path.basename(project)
    pub = os.path.join(project, 'publish')
    check = '--check' in sys.argv
    video = paths.find_video(name)
    sj = os.path.join(project, 'shorts.json')
    shorts = json.load(open(sj, encoding='utf-8')) if os.path.exists(sj) else []
    thumbs = sorted(f for f in os.listdir(pub) if f.startswith('thumbnail') and f.endswith('.jpg')) if os.path.isdir(pub) else []
    texts = {f: os.path.join(pub, f) for f in ('youtube.md', 'redes.md', 'info.json')}
    missing = []
    if not os.path.exists(video): missing.append(f'video principal ({video}) → engine/build.py')
    if not shorts or not all(os.path.exists(s['archivo']) for s in shorts): missing.append('shorts → engine/short.py --count auto')
    if 'thumbnail.jpg' not in thumbs: missing.append('miniatura → engine/publish.py thumb')
    for f in ('youtube.md', 'redes.md'):
        if not os.path.exists(texts[f]): missing.append(f'{f} → lo escribe Claude (skill yt-publish / cs2-pack)')
    if missing:
        print('Falta:'); [print('  -', m) for m in missing]
    if check or missing:
        return 1 if missing else 0

    # video y shorts en su carpeta (los de proyectos viejos estaban sueltos en output/)
    video = adopt(video, os.path.join(paths.video_dir(name), f'{name}.mp4'))
    for s in shorts:
        s['archivo'] = adopt(s['archivo'], os.path.join(paths.shorts_dir(name), os.path.basename(s['archivo'])))
    json.dump(shorts, open(sj, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)

    info = paths.info_dir(name); os.makedirs(info, exist_ok=True)
    for f in thumbs: shutil.copy2(os.path.join(pub, f), os.path.join(info, f))
    if os.path.exists(os.path.join(pub, 'thumbs_compare.jpg')): shutil.copy2(os.path.join(pub, 'thumbs_compare.jpg'), info)
    for f, pth in texts.items():
        if os.path.exists(pth): shutil.copy2(pth, info)
    chk = os.path.join(project, 'check_render.txt')
    if os.path.exists(chk): shutil.copy2(chk, info)

    L = [f'# Entrega: {name}', '', '## Carpetas', '',
         '| Archivo | Para | Duración |', '|---|---|---|',
         f'| `video/{os.path.basename(video)}` | YouTube (video largo, 1920×1080) | {dur(video):.0f} s |']
    for s in shorts:
        L.append(f'| `shorts/{os.path.basename(s["archivo"])}` | TikTok · Instagram Reels · YouTube Shorts (1080×1920) — tramo {s["desde"]}-{s["hasta"]} del edit | {s["dur"]:.0f} s |')
    L += ['| `info/thumbnail.jpg` | miniatura del video largo (1280×720) | |',
          '| `info/thumbs_compare.jpg` | las otras opciones de miniatura, a tamaño celular | |',
          '| `info/youtube.md` | título, descripción con capítulos y tags | |',
          '| `info/redes.md` | texto y hashtags de cada short por plataforma | |', '',
          '## Orden recomendado para subir', '',
          '1. **YouTube (largo):** subilo primero como *privado* o *no listado*, poné la miniatura y los textos de `youtube.md`, '
          'y mirá la pestaña "Comprobaciones" (Content ID por la canción) antes de publicarlo.',
          '2. **Shorts:** uno por día, del más fuerte al más flojo (el 1 es el de mejor puntaje), con los textos de `redes.md`. '
          'En YouTube Shorts vinculá el video largo ("video relacionado").',
          '3. **TikTok e Instagram Reels:** el mismo archivo de cada short; en Instagram elegí la portada desde el video.', '']
    if os.path.exists(chk):
        L += ['## Chequeo técnico del video largo', '', '```', open(chk, encoding='utf-8').read().strip(), '```', '']
    open(os.path.join(info, 'LEEME.md'), 'w', encoding='utf-8').write('\n'.join(L))
    out = paths.project_dir(name)
    print(f'Entrega lista en {out}')
    for sub in ('video', 'shorts', 'info'):
        d = os.path.join(out, sub)
        if os.path.isdir(d): print(f'  {sub}/: ' + ', '.join(sorted(os.listdir(d))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
