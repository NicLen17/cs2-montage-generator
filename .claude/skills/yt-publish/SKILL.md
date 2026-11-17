---
name: "yt-publish"
description: "Prepara todo para subir un edit de CS2 a YouTube: miniatura 1280x720 desde la mejor kill, título, descripción con capítulos válidos, tags y aviso de derechos de la canción (Content ID). No sube nada. Usala cuando el usuario pida 'la miniatura', 'título y descripción', 'prepará la subida', 'paquete para YouTube' o 'capítulos' de un edit terminado."
---

# Paquete para subir un edit a YouTube

Todo queda en `projects/<nombre>/publish/`. **No se sube ni se publica nada**: el usuario sube el video desde YouTube Studio. Los scripts están en `engine/publish.py`.

## Pasos
1. Confirmá que existe `output/<nombre>.mp4` y que es la versión final (sin correcciones pendientes).
2. **Datos:** `python engine/publish.py projects/<nombre> info` → `publish/info.json` con duración, plays con título, cantidad de kills, canción (tags del mp3) y **capítulos ya validados** (primero en 0:00, al menos 3, cada uno de 10 s o más; si no, YouTube los ignora).
3. **Cuadros para la miniatura:** `python engine/publish.py projects/<nombre> frames` → un cuadro por kill de las plays con título y por cada drop, y una hoja `publish/thumbs_sheet.jpg` con números. Mirala y elegí el cuadro:
   - el enemigo se ve claro y cerca (mejor si está cayendo o con el marcador de headshot), el arma visible;
   - sin quemar por un efecto (destello, luz horizontal), sin transición a medias;
   - sin los rectángulos blancos u overlays del stream tapando el centro;
   - de la play más fuerte (ACE, clutch, 4K).
4. **Miniatura:** `python engine/publish.py projects/<nombre> thumb --frame N --text "ACE" --sub "M4A1-S" --side left`
   - Texto **corto** (1 a 3 palabras, lo que hace la play: "ACE", "1v4", "4K AWP"); subtítulo con el arma o el mapa. Nunca letra de la canción.
   - `--side` del lado contrario al enemigo para no taparlo; `--zoom 1.3` acerca hacia la mira (máximo 2x, como en el edit); `--size` cambia el tamaño del texto.
   - Mirá `publish/thumbnail.jpg` y corregí si el texto tapa la acción o no se lee en chico (imaginalo a 320 px de ancho).
5. **Textos:** escribí `publish/youtube.md` con:
   - **3 títulos** (≤ 70 caracteres, la play más fuerte primero, en el tono del canal), por ejemplo `ACE con la USP en Mirage 🔥 | MY JEALOUSY · CS2 Montage`.
   - **Descripción:** 1-2 líneas sobre el edit, `twitch.tv/el_wako`, crédito de la canción (`Música: <tema> — <artista>`), los capítulos de `info.json` tal cual (uno por línea, `0:00 Intro`), y 3 hashtags (`#CS2 #CounterStrike2 #WakoTV`).
   - **Tags** (≤ 500 caracteres en total): cs2, counter strike 2, cs2 montage, cs2 edit, el nombre de la canción y el artista, armas y mapas de las plays con título, wako tv, el_wako.
   - **Derechos de la canción:** si la canción es comercial, avisá que casi seguro va a tener un reclamo de Content ID (la monetización va a la discográfica o el video puede quedar bloqueado en algunos países) y que conviene subirlo primero como **privado** o **no listado** y mirar la pestaña "Comprobaciones" de YouTube Studio antes de publicarlo.
6. Si los tags del mp3 no traen el artista, preguntáselo al usuario en una línea (o dejalo como `<ARTISTA>` y avisá).

## Reglas
- No inventes datos de la play: el arma y el conteo salen de los títulos del plan (ya verificados en `cs2-edit`).
- Nada de letra de la canción en la miniatura, el título ni la descripción.
- Si el usuario pidió también el short (`cs2-short`), en la descripción del short va el link al video largo cuando el usuario lo tenga.

## Respuesta
La miniatura (mostrala con la ruta), el título recomendado, los capítulos y el aviso de derechos en dos líneas. El resto queda en `publish/youtube.md`.
