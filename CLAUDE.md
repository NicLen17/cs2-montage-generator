# WAKO TV — edits de CS2 en esta PC

Este proyecto arma montajes de CS2 con música (estilo WAKO TV) y los renderiza **en esta computadora**
(Ryzen 5 7600X, 32 GB, RX 7900 XT). Todo corre local: análisis, render y exportación.

## Cómo se pide un video
El usuario adjunta o deja los clips y la canción (o escribe `/cs2-pack`, `/cs2-edit`, "hacé un edit").
**Por defecto se hace el paquete completo** con `.claude/skills/cs2-pack/SKILL.md`: edit largo + shorts + miniatura + textos.
El edit en sí sigue el skill **del proyecto** `.claude/skills/cs2-edit/SKILL.md` de punta a punta. Resumen del flujo:

1. Crear `projects/<nombre>/` con `clips/c1.mp4, c2.mp4, ...` (copias, nunca mover los originales del usuario),
   `clips_map.txt`, `song.mp3` y opcionalmente `logo.png` (si no, se usa `engine/assets/logo.png`).
   `python engine/catalog.py scan` y `python engine/catalog.py prefill projects/<nombre>` → los clips ya verificados
   en otros edits traen sus kills y no se vuelven a verificar.
2. `python engine/analyze_song.py projects/<nombre>` → BPM, drops, cortes de batería, golpes vocales y **momentos para
   sincronizar** (`sync.json`): cada sección con buen ritmo lleva una kill exacta (`SYNC` del plan, lo controla `check_kills.py`).
   Separar voz y música (`python -m demucs --two-stems=vocals -n htdemucs -o stems song.mp3`) para el mapa de secciones,
   y los golpes de voz aislados ("stop").
3. `python engine/analyze_clips.py projects/<nombre>` → lee el killfeed (fuente de verdad: nombre del jugador a la
   izquierda de una entrada roja = kill; el jugador se deduce de cada play) y deja `kf_auto.json`/`kf.json`,
   `kf_conf.json` (confianza por kill) y `sheets/kf_resumen.txt`. Mirar a ojo **solo** `sheets/kf_dudosos.jpg`
   (kills dudosas y clips con la cámara tapando el killfeed), corregir `kf.json`, después
   `python engine/analyze_clips.py projects/<nombre> --shots` y
   `python engine/catalog.py import projects/<nombre>` (guardar lo verificado en el catálogo) y
   `python engine/reactions.py projects/<nombre> --all` (festejos grupales al final de cada play, con Demucs; ver skill §8).
4. Escribir `projects/<nombre>/plan.py` copiando `projects/my_jealousy_v3/plan.py` y cambiando solo los datos
   (leer antes `.claude/skills/cs2-edit/references/plan.md`). Correr `python projects/<nombre>/plan.py` y revisar residuos y avisos.
5. `python engine/check_kills.py projects/<nombre>` → sin problemas, sin avisos de TIEMPO MUERTO sin justificar y con
   los avisos del KILLFEED revisados (kills que el killfeed muestra y no están en `kf.json`).
6. Previews: `python engine/build.py projects/<nombre> --preview t1,t2,...` → mirar `projects/<nombre>/previews/`.
   Si el usuario quiere ver el video entero antes del final: `--draft` (borrador 960x540 a 30 fps en `projects/<nombre>/borrador.mp4`).
7. Render final (en segundo plano): `python engine/build.py projects/<nombre>` → `output/<nombre>/video/<nombre>.mp4`.
   Al terminar corre solo `check_render.py` y lo guarda en `projects/<nombre>/check_render.txt`: leelo.
8. Paquete completo (skill `cs2-pack`): `python engine/short.py projects/<nombre> --count auto --dur 35`, miniatura y textos
   con `yt-publish`, `publish/redes.md`, y `python engine/pack.py projects/<nombre>` → completa `output/<nombre>/info/`.
9. Revisiones: `python engine/locate.py projects/<nombre> 1:23,2:05` traduce los minutos que marca el usuario a clip,
   kill y transición, con tiras de cuadros en `projects/<nombre>/insp/`.

## Skills del proyecto
| Skill | Cuándo |
|---|---|
| `cs2-pack` | **Por defecto** cuando llegan clips + canción, `/cs2-pack`, "hacé un edit", "hacé todo": edit + 2-4 shorts + miniatura + textos de YouTube y redes, en `output/<nombre>/` (`video/`, `shorts/`, `info/`). Encadena las demás skills. |
| `cs2-edit` | Las reglas del edit (siempre se cargan, también dentro de `cs2-pack`). Sola, solo si el usuario pide **únicamente** el video largo ("solo el edit", `/cs2-edit`) o para corregir un edit ya hecho. |
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
- Si el usuario adjunta clips y una canción en el chat, o dice "hacé un edit" sin más, **arrancá sin preguntar con
  `cs2-pack`** (pedido del usuario del 17/11/2026: siempre el paquete completo, no solo el video largo).
  Los archivos están en lo que adjuntó, en la carpeta que nombró o, si no dio ninguna, en `entrada/`.
  Elegí el nombre del proyecto a partir del título de la canción (minúsculas, guiones bajos).
- Solo el video largo si lo pide explícitamente ("solo el edit", "sin shorts", `/cs2-edit`).
- Cargá al empezar: `cs2-pack`, `cs2-edit` del proyecto (flujo y preferencias del canal) y
  `anthropic-skills:montage-editing-craft` (criterio general de edición). Si chocan, manda `cs2-edit`.
- Solo frená para preguntar lo que el skill pide confirmar (armas dudosas, golpes de voz aislados si hay dudas, artista de
  la canción si el mp3 no lo trae), todo junto en un mensaje al principio. Todo lo demás: decidí vos y avisá al final.
- Al terminar, no borres nada de `entrada/`: esos archivos son del usuario.

## Comandos largos
- La herramienta de terminal corta a los 10 minutos. Corré `engine/build.py` (render final), `engine/short.py`
  y cámaras lentas **en segundo plano** (`run_in_background`) y esperá el aviso; nunca con un timeout que corte el video.
- Después verificá: `check_render.txt` (duración vs `TOTAL` del plan, 60 fps, tirones, volumen), `audio_balance.txt`
  (juego vs música y reacciones resaltadas) y una hoja de fotogramas.

## Hardware y velocidad
- **Dos modos, uno u otro de punta a punta:** `python engine/build.py projects/<nombre> --device gpu|cpu|auto` (por defecto
  `auto`: GPU si hay OpenGL 4.3 y `moderngl`; si no, CPU). La lógica del edit es una sola (`render.py`); en GPU las
  operaciones de imagen corren como shaders (`engine/gpu.py`), los clips se decodifican con el decodificador de video de la
  placa y el cuadro baja ya en NV12 al codificador. Mismo resultado que en CPU (PSNR mínimo 48 dB en 94 momentos con cada
  efecto; 45 dB de mediana entre los videos codificados).
- **Medido en my_jealousy_v3 (2:22, RX 7900 XT, Ryzen 5 7600X):** motor viejo 330 s · CPU 281 s · **GPU 55 s**.
  Borrador GPU 45 s. En GPU el límite es el motor de video de la placa (decodifica y codifica en el mismo chip, al 100 %).
- **El render en CPU está limitado por la velocidad de la RAM, no por los núcleos:** 5 procesos rinden lo mismo que 10 o 12.
- `build.py` divide el video en pedazos de 2 s. Procesos de `render.py` fijos (CPU: núcleos − 2; GPU: hasta 6) toman pedazos
  de una cola, los más pesados primero. Cada pedazo sale con la calidad final y se unen sin recodificar.
- **Borrador:** `--draft` → `projects/<nombre>/borrador.mp4` (960x540, 30 fps, mismo look). Para que el usuario mire el edit
  entero antes del render final y marque minutos.
- **Cachés:** solo se vuelven a renderizar los pedazos que cambiaron, y el audio (`work_audio.wav`, ~40 s) se reusa si no
  cambió nada de lo que usa `audio.py` (`audio.key`). Un build sin cambios tarda ~6 s.
- Codifica con la GPU si está disponible (AMD AMF, NVIDIA NVENC, Intel QSV); si no, con la CPU. Ver: `python engine/encoders.py`.
- **Cámaras lentas con RIFE** en la GPU (`tools/rife/`, se instala con `python engine/setup_rife.py`): ~10 s cada una
  contra ~70 s por segundo con minterpolate (que queda de respaldo si RIFE no está).
- **Audio:** la mezcla decodifica todos los archivos con una sola llamada a ffmpeg (~12 s; antes ~40 s: abrir ffmpeg
  cuesta ~0.5 s en Windows y se abría ~50 veces).
- Si un render falla por memoria, bajar `--workers`.

## Reglas
- Las preferencias del usuario están en el skill (reglas de corte, efectos, texto, audio). No las cambies sin que lo pida.
- No poner letras de canciones en pantalla.
- Verificar siempre el resultado: duración, 60 fps, y mirar previews de los momentos cambiados.
- **Una carpeta por proyecto en `output/<nombre>/`** (pedido del 20/11/2026): `video/` (el edit largo y sus variantes), `shorts/` y
  `info/` (miniaturas, `youtube.md`, `redes.md`, `info.json`, `check_render.txt`, `LEEME.md`). Nada suelto en `output/`.
  Las rutas salen de `engine/paths.py`. Los clips originales del usuario no se tocan.
