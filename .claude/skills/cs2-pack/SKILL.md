---
name: "cs2-pack"
description: "Skill POR DEFECTO del proyecto CS2 Montage Generator cuando llegan clips y una canción: arma el edit para YouTube, 2 a 4 shorts verticales para TikTok, Instagram Reels y YouTube Shorts, la miniatura, los textos de cada plataforma y una carpeta de entrega lista para subir, con un solo pedido. Usala SIEMPRE que el usuario adjunte o deje clips (.mp4) y una canción (en el chat, en entrada/ o en una carpeta), escriba /cs2-pack, diga 'hacé un edit', 'hacé todo', 'el paquete completo' o 'para YouTube y redes'. Solo si pide únicamente el video largo ('solo el edit', 'sin shorts', /cs2-edit) se usa cs2-edit sola."
---

# Paquete completo: edit + shorts + miniatura + textos

Un solo pedido y sale todo el contenido de un video. **Es el arranque por defecto** cuando el usuario manda clips y canción (lo pidió así: siempre el paquete completo). Esta skill **no tiene reglas propias de edición**: encadena las otras skills del proyecto y cada paso sigue la suya.

| Paso | Skill que manda | Resultado |
|---|---|---|
| 1. Edit largo | `cs2-edit` (y `clip-catalog`) | `output/<nombre>/video/<nombre>.mp4` 1920×1080 |
| 2. Shorts | `cs2-short` | `output/<nombre>/shorts/<nombre>_short1.mp4`, `_short2`… 1080×1920 |
| 3. Miniatura y textos de YouTube | `yt-publish` | `publish/thumbnail.jpg`, `publish/youtube.md` |
| 4. Textos de redes | esta skill (§4) | `publish/redes.md` |
| 5. Entrega | esta skill (§5) | `output/<nombre>/info/` con miniaturas, textos y un `LEEME.md` |

Antes de empezar, cargá `cs2-edit` (es la que tiene las reglas del canal) y `anthropic-skills:montage-editing-craft`, igual que en un edit normal. Leé `cs2-short` y `yt-publish` cuando llegues a esos pasos.

## Reglas de la corrida
- **Arrancá sin preguntar**, igual que `cs2-edit`: los archivos están en lo que el usuario adjuntó, en la carpeta que nombró o en `entrada/`.
- **Las únicas preguntas son las de `cs2-edit`** (armas dudosas, golpes de voz aislados si hay dudas) y el artista de la canción si el mp3 no lo trae. Juntalas en **un solo mensaje al principio**, apenas termines el análisis de la canción y de los clips, para que el resto corra sin frenar. Si el usuario no está, seguí con lo detectable y avisá al final qué quedó sin confirmar.
- **Todo lo demás lo decidís vos** (plays, cantidad de shorts, tipo de miniatura, textos) y lo contás al final.
- **Calidad antes que velocidad:** cada paso conserva sus chequeos (`check_kills` limpio, previews, `check_render.txt`, hojas de los shorts, comparación de miniaturas). No te saltees ninguno por ser una corrida larga.
- Los comandos largos (render, shorts) van **en segundo plano**; mientras corren, avanzá con lo que no depende de ellos.

## 1. Edit largo
Seguí `cs2-edit` de punta a punta hasta tener `output/<nombre>/video/<nombre>.mp4` y `projects/<nombre>/check_render.txt` limpio (si el pico pasa de -1 dBFS, aplicá la bajada de audio sin re-renderizar, como dice la skill). Guardá lo verificado en el catálogo (`catalog.py import`).

## 2. Shorts (en segundo plano)
`python engine/short.py projects/<nombre> --count auto --dur 35` (en segundo plano).
- Elige solo de 2 a 4 tramos que **no se pisan entre sí**, cada uno empieza después de una transición y termina antes de la siguiente, con gancho en los primeros segundos (kill o drop). Antes podés ver qué elegiría con `--list`.
- Si el edit es corto o un tramo no te convence, usá `--count 2` o tramos fijos con `--start/--dur` (un comando por short, con `--name`).
- Revisá la hoja de cada short (`projects/<nombre>/short1_sheet.jpg`, …) como pide `cs2-short`. Los datos quedan en `projects/<nombre>/shorts.json`.

## 3. Miniatura y YouTube (mientras renderizan los shorts)
Seguí `yt-publish` pasos 2 a 5: `publish.py info`, `publish.py frames`, `publish.py thumb --type todas ...` (elegís vos el tipo según el video; en un montaje, `jugada`), revisás `thumbs_compare.jpg` y escribís `publish/youtube.md`.

## 4. Textos de redes (`publish/redes.md`)
Un bloque por short (usá `shorts.json`: tramo, kills y títulos de cada uno):
```markdown
## Short 1 — 0:22-0:58 del edit (ACE con USP-S, drop)
**YouTube Shorts** (título ≤ 100 caracteres): ACE con la USP en el drop 🔥 #cs2 #shorts
**TikTok** (texto + 3-5 hashtags): este ACE con USP cayó justo en el drop 😳 #cs2 #counterstrike2 #cs2clips #fyp
**Instagram Reels** (texto + hasta 5 hashtags): ACE con USP-S en Mirage 🎯 Edit completo en YouTube (link en la bio) #cs2 #counterstrike #gaming
**Portada sugerida:** segundo 3 (la kill del drop)
```
- El texto dice **qué pasa en ese short** (la play, el arma, el conteo), sale de los títulos del plan: nada inventado y nada de letra de la canción.
- Cada short tiene texto distinto; no copies el mismo en todos.
- Mencioná `twitch.tv/el_wako` en TikTok e Instagram (en el texto o "link en la bio").
- Orden de publicación: del short con mejor puntaje al más flojo (el 1 es el mejor de `--count auto`).

## 5. Entrega
`python engine/pack.py projects/<nombre>` completa la carpeta del proyecto, `output/<nombre>/` (una por proyecto, nada suelto en `output/`):
- `video/<nombre>.mp4` (lo deja `build.py`), `shorts/<nombre>_short1.mp4`, … (los deja `short.py`) e `info/` con `thumbnail.jpg` y las otras opciones de miniatura, `youtube.md`, `redes.md`, `info.json`, `check_render.txt` y un `LEEME.md` con qué subir a cada plataforma y en qué orden.
- Si dice "Falta: …", completá ese paso y volvé a correrlo.

## Respuesta final
Una tabla corta con lo que quedó en `output/<nombre>/` (video largo con su duración, cada short con su tramo y la play que muestra, la miniatura elegida y por qué). Después, en pocas líneas, lo que pide el resumen de `cs2-edit` (plays, uso de la canción, qué se dejó afuera), lo que quedó sin confirmar y el aviso de Content ID. Mostrá la miniatura y `thumbs_compare.jpg` con sus rutas.

## Correcciones después de la entrega
- Si el usuario corrige el **edit largo**: corregí con `cs2-edit` (solo se re-renderiza lo que cambió) y después **volvé a correr los pasos 2, 3 y 5**: los shorts y la miniatura salen del video final, así que si no se rehacen quedan desactualizados.
- Si corrige **solo un short, la miniatura o un texto**: rehacé ese paso y el 5.
