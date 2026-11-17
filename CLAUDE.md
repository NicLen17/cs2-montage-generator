# WAKO TV — edits de CS2 en esta PC

Este proyecto arma montajes de CS2 con música (estilo WAKO TV) y los renderiza **en esta computadora**
(Ryzen 5 7600X, 32 GB, RX 7900 XT). Todo corre local: análisis, render y exportación.

## Cómo se pide un video
El usuario escribe `/cs2-edit` (o "hacé un edit") y deja los clips y la canción en una carpeta.
Seguí el skill **del proyecto** `.claude/skills/cs2-edit/SKILL.md` de punta a punta. Resumen del flujo:

1. Crear `projects/<nombre>/` con `clips/c1.mp4, c2.mp4, ...` (copias, nunca mover los originales del usuario),
   `clips_map.txt`, `song.mp3` y opcionalmente `logo.png` (si no, se usa `engine/assets/logo.png`).
   `python engine/catalog.py scan` y `python engine/catalog.py prefill projects/<nombre>` → los clips ya verificados
   en otros edits traen sus kills y no se vuelven a verificar.
2. `python engine/analyze_song.py projects/<nombre>` → BPM, drops, cortes de batería, golpes vocales.
   Separar voz y música (`python -m demucs --two-stems=vocals -n htdemucs -o stems song.mp3`) para el mapa de secciones,
   los golpes de voz ("stop") y las repeticiones de sílabas.
3. `python engine/analyze_clips.py projects/<nombre>` → mirar `sheets/*.jpg`, corregir `kf.json` (kills propias reales,
   verificadas a ojo), después `python engine/analyze_clips.py projects/<nombre> --shots` y
   `python engine/catalog.py import projects/<nombre>` (guardar lo verificado en el catálogo).
4. Escribir `projects/<nombre>/plan.py` copiando `projects/my_jealousy_v3/plan.py` y cambiando solo los datos
   (leer antes `.claude/skills/cs2-edit/references/plan.md`). Correr `python projects/<nombre>/plan.py` y revisar residuos y avisos.
5. `python engine/check_kills.py projects/<nombre>` → sin problemas y sin avisos de TIEMPO MUERTO sin justificar.
6. Previews: `python engine/build.py projects/<nombre> --preview t1,t2,...` → mirar `projects/<nombre>/previews/`.
7. Render final (en segundo plano): `python engine/build.py projects/<nombre>` → `output/<nombre>.mp4`.
   Al terminar corre solo `check_render.py` y lo guarda en `projects/<nombre>/check_render.txt`: leelo.
8. Revisiones: `python engine/locate.py projects/<nombre> 1:23,2:05` traduce los minutos que marca el usuario a clip,
   kill y transición, con tiras de cuadros en `projects/<nombre>/insp/`.

## Skills del proyecto
| Skill | Cuándo |
|---|---|
| `cs2-edit` | **Por defecto.** Siempre que haya clips + canción, "hacé un edit", o cambios a un edit ya hecho. |
| `clip-catalog` | Elegir plays, ver qué clips ya se usaron o están verificados, cargar clips nuevos. Lo usa `cs2-edit`. |
| `cs2-short` | Short vertical 9:16 (TikTok, Reels, Shorts) a partir de un edit terminado. |
| `yt-publish` | Miniatura, título, descripción con capítulos y tags para subir un edit a YouTube. |
| `edit-style-learner` | El usuario adjunta un edit de referencia **descargado** ("hacé uno así", "aprendé este estilo"). |

- La referencia de estilo va en `projects/<nombre>/ref/`. Los estilos guardados quedan como `.claude/skills/cs2-edit-<estilo>/`.
- Hay una copia vieja de las reglas en `backup/skills_2026-11-17/` (antes de reorganizar la skill): no se usa, es solo respaldo.

## Skills del proyecto vs. las de la cuenta
- **Usá siempre `cs2-edit` y `edit-style-learner` del proyecto.** Las de la cuenta con el mismo nombre
  (`anthropic-skills:cs2-edit`, `anthropic-skills:edit-style-learner`) quedaron congeladas y no se actualizan: no las cargues.
- Las demás de la cuenta (`anthropic-skills:*`) están escritas para la nube (`~/comp/`, SendUserFile, "sin GPU"):
  de ellas tomá solo las reglas de edición, nunca las partes de entorno, hardware o entrega.

## Arranque automático (el usuario solo adjunta clips y canción)
- Si el usuario adjunta clips y una canción en el chat, o dice "hacé un edit" sin más, **arrancá sin preguntar**:
  los archivos están en lo que adjuntó, en la carpeta que nombró o, si no dio ninguna, en `entrada/`.
  Elegí el nombre del proyecto a partir del título de la canción (minúsculas, guiones bajos).
- Cargá **los dos skills** al empezar: `cs2-edit` del proyecto (flujo y preferencias del canal) y
  `anthropic-skills:montage-editing-craft` (criterio general de edición). Si chocan, manda `cs2-edit`.
- Solo frená para preguntar lo que el skill pide confirmar (golpes vocales tipo "bang bang", frases épicas sí/no,
  armas dudosas). Todo lo demás: decidí vos y avisá al final.
- Al terminar, no borres nada de `entrada/`: esos archivos son del usuario.

## Comandos largos
- La herramienta de terminal corta a los 10 minutos. Corré `engine/build.py` (render final), `engine/short.py`
  y cámaras lentas **en segundo plano** (`run_in_background`) y esperá el aviso; nunca con un timeout que corte el video.
- Después verificá: `check_render.txt` (duración vs `TOTAL` del plan, 60 fps, tirones, volumen) y una hoja de fotogramas.

## Hardware y velocidad
- `engine/build.py` divide el video en pedazos de 6 s y los renderiza en paralelo (núcleos lógicos − 2 procesos).
- Codifica con la GPU si está disponible (AMD AMF en la RX 7900 XT); si no, con la CPU. Ver: `python engine/encoders.py`.
- **Caché de pedazos:** al corregir, solo se vuelven a renderizar los pedazos cuyo contenido cambió. Una corrección chica tarda segundos o pocos minutos.
- Si un render falla por memoria, bajar `--workers`.

## Reglas
- Las preferencias del usuario están en el skill (reglas de corte, efectos, texto, audio). No las cambies sin que lo pida.
- No poner letras de canciones en pantalla.
- Verificar siempre el resultado: duración, 60 fps, y mirar previews de los momentos cambiados.
- Los videos terminados quedan en `output/`. Los clips originales del usuario no se tocan.
