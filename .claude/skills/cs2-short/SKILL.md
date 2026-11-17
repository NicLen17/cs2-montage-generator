---
name: "cs2-short"
description: "Arma un short vertical 9:16 (TikTok, Instagram Reels, YouTube Shorts) de 30 a 60 s a partir de un edit de CS2 ya renderizado en output/, conservando efectos, sincronía y mezcla. Usala cuando el usuario pida 'un short', 'un tiktok', 'un reel', 'versión vertical' o 'un recorte para redes' de un edit."
---

# Short vertical de un edit

El short sale del **video final ya renderizado** (`output/<nombre>.mp4`): no se vuelve a renderizar el edit, así que hereda la sincronía, los efectos y la mezcla que el usuario ya aprobó. Todo pasa por `engine/short.py`.

## Pasos
1. Confirmá que existe `output/<nombre>.mp4` y que `check_render.txt` del proyecto está limpio. Si el edit todavía tiene correcciones pendientes, hacé el short después.
2. **Elegir el tramo:** `python engine/short.py projects/<nombre> --list`. Lista los candidatos con kills, títulos, segundos hasta la primera kill y si arranca en un drop. Siempre empiezan después de una transición y terminan antes de la siguiente: nunca cortan una play por la mitad.
   - Criterio: **gancho en los primeros 2 s** (una kill o un drop; en redes se decide ahí si se sigue mirando), muchas kills por segundo, plays con título (ACE, 4K, clutch) y sin el negro del interludio en el medio. El primer candidato suele ser el bueno; si el usuario pidió una play concreta, usá `--start m:ss --dur N`.
   - Duración: 30 a 45 s por defecto (`--dur`). Más de 60 s algunas plataformas lo toman como video normal: avisá.
3. **Render** (en segundo plano si el tramo es largo; tarda ~1-2 min): `python engine/short.py projects/<nombre>` (o con `--start/--dur`). Salida: `output/<nombre>_short.mp4` (1080×1920, 60 fps) y una hoja `projects/<nombre>/short_sheet.jpg`.
4. **Revisá la hoja** con la herramienta de lectura de imágenes: el gameplay entero visible, el texto sin tapar nada, y que el primer cuadro no sea una transición a medias.

## Layouts
- `fit` (por defecto): fondo desenfocado del mismo video, el cuadro completo a 1080 de ancho en el centro (se ve todo, killfeed incluido), "WAKO TV" y el nombre del tema arriba, `twitch.tv/el_wako` abajo. Funciona con cualquier clip.
- `cam`: cámara del streamer arriba con zoom 2x (el máximo de `cs2-edit` §6: más pixela) y el centro del gameplay abajo a tamaño real (sin killfeed). Usalo solo si en **todo** el tramo la cámara está en la posición por defecto `(25,18)-(490,278)`; si en algún clip está en otro lado, se vería un pedazo de juego en su lugar. Verificalo con `engine/locate.py` en 2 o 3 momentos del tramo.
- `--no-text` saca los textos (por si el usuario los agrega en la app de la plataforma).

## Reglas
- Las mismas de `cs2-edit`: nada de letra de la canción en pantalla, sin frases épicas, zoom máximo 2x, nunca acelerar el gameplay.
- No cambies el tramo para que "entre" una play cortada: si la mejor play no entra completa, elegí otro tramo o alargá `--dur`.
- El short no reemplaza al edit: queda al lado, en `output/`.

## Respuesta
Una línea con el tramo usado (de qué minuto a qué minuto del edit), duración, plays que incluye y dónde quedó el archivo.
