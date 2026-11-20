---
name: "yt-publish"
description: "Prepara todo para subir un edit de CS2 a YouTube: miniatura 1280x720 (4 tipos basados en las miniaturas más vistas de canales de CS: jugada, reacción, limpia, versus), título, descripción con capítulos válidos, tags y aviso de derechos de la canción (Content ID). No sube nada. Usala cuando el usuario pida 'la miniatura', 'título y descripción', 'prepará la subida', 'paquete para YouTube' o 'capítulos' de un edit terminado."
---

# Paquete para subir un edit a YouTube

Todo queda en `projects/<nombre>/publish/`. **No se sube ni se publica nada**: el usuario sube el video desde YouTube Studio. Los scripts están en `engine/publish.py`.

## Pasos
1. Confirmá que existe `output/<nombre>/video/<nombre>.mp4` y que es la versión final (sin correcciones pendientes).
2. **Datos:** `python engine/publish.py projects/<nombre> info` → `publish/info.json` con duración, plays con título, cantidad de kills, canción (tags del mp3) y **capítulos ya validados** (primero en 0:00, al menos 3, cada uno de 10 s o más; si no, YouTube los ignora).
3. **Cuadros y caras:** `python engine/publish.py projects/<nombre> frames` → un cuadro por kill de las plays con título y por cada drop (`thumbs_sheet.jpg`, números `cand`), y la cara del streamer recortada de su cámara en el cierre y ~0.8 s después de cada kill (`reacciones_sheet.jpg`, números `reac`). Mirá las dos hojas y elegí:
   - **cand:** el enemigo se ve claro y cerca (mejor si está cayendo o con el marcador de headshot), el arma visible; sin quemar por un efecto, sin transición a medias, sin los rectángulos blancos u overlays del stream en el centro; de la play más fuerte (ACE, clutch, 4K).
   - **reac:** la cara con más expresión (sorpresa, boca abierta, festejo). Descartá las que muestran el minimapa o un pedazo de juego (en esos clips la cámara está en otro lugar) o la cámara vacía.
4. **Miniaturas:** antes de la primera, leé `references/miniaturas.md` (análisis de las miniaturas más vistas de FURI, realFURI y Dareh: qué se repite y de dónde sale cada tipo). **No preguntes el tipo:** generá las tres y elegí vos según el video.
   `python engine/publish.py projects/<nombre> thumb --type todas --frame N --cam M --text "ACE" --sub "M4A1-S" --arrow x1,y1,x2,y2`
   | Tipo | Cuándo es la recomendada |
   |---|---|
   | `jugada` | **por defecto en montajes** y edits de plays (`thumbnail.jpg` sale de esta salvo `--pick`) |
   | `reaccion` | cuando la reacción del streamer es el gancho (clutch increíble, momento gracioso, "casi 5K") |
   | `limpia` | funny moments o videos de curiosidad donde el título hace la gracia (sin texto ni gráficos) |
   | `versus` | antes/después o "X vs Y" (`--type versus --frame A --frame2 B --text "ANTES\|DESPUÉS"`); no entra en `todas` |
   - Texto **de 0 a 3 palabras** que complementa el título, nunca lo repite ("ACE", "1v4", "4K AWP"); `|` parte en renglones. Subtítulo en pastilla de color (`--accent amarillo|rojo|verde|violeta|cian`) con el arma o el mapa. Nunca letra de la canción.
   - `--arrow x1,y1,x2,y2` o `--circle x,y,r` (coordenadas de 1280×720) señalan al enemigo o al detalle clave; solo se dibujan en `jugada` (y en `reaccion` o `versus` si se generan solos). `--side` pone el texto del lado contrario al enemigo; `--focus x,y` y `--zoom 1.3` acercan hacia el foco (máximo 2x); `--angle 4` inclina el texto; `--logo` suma el logo del canal arriba.
   - Revisá `publish/thumbs_compare.jpg` (las tres a 320 px, como en el celular): el foco y el texto se tienen que entender en ese tamaño. Corregí si el texto tapa al enemigo o la cara queda chica. Si otra salió mejor que la recomendada, usá `--pick <tipo>`.
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
La miniatura elegida y por qué ese tipo (mostrá también `thumbs_compare.jpg` para que el usuario pueda pedir otra), el título recomendado, los capítulos y el aviso de derechos en dos líneas. El resto queda en `publish/youtube.md`.
