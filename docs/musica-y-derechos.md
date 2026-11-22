# Música y derechos

El motor no trae música ni la descarga: **la canción la ponés vos y sos responsable de tener derecho a usarla.**

## Qué pasa al subir un edit con una canción comercial

- **YouTube (Content ID):** casi cualquier canción publicada por un sello está registrada. Al subir el video llega un
  *reclamo*: no es una falta (strike), pero el dueño de la canción decide qué pasa. Lo habitual es que el video quede
  público y **los ingresos por anuncios vayan al titular**; a veces se bloquea en algunos países o en todos.
- **TikTok, Reels y Shorts:** pueden silenciar o bajar un video cuyo audio no salga de su propia biblioteca.
- **Twitch (VOD y clips):** el audio con música registrada puede quedar silenciado.
- Un reclamo no es lo mismo que una infracción, pero varias infracciones sí ponen en riesgo el canal.

## Cómo evitar problemas

- Usá música con licencia para creadores (bibliotecas que lo digan expresamente) o con una licencia Creative Commons
  que permita tu uso; leé si pide atribución y ponela en la descripción.
- Pedile permiso al artista si es independiente: muchos lo dan a cambio del crédito.
- Antes de armar el paquete completo, subí el video como **no listado**: YouTube muestra los reclamos antes de publicarlo.
- Guardá la licencia o el permiso de cada canción junto al proyecto.

## Qué hace y qué no hace el motor

- `engine/publish.py` deja en la descripción el crédito de la canción (título y artista de las etiquetas del archivo) y
  un aviso de Content ID. No sube nada.
- **Nunca escribe la letra en pantalla.** `engine/words.py` transcribe la voz solo para saber en qué instante cae cada
  palabra y sincronizar kills; ese archivo queda en tu proyecto y no se publica.
- Los clips, canciones y videos de `projects/`, `entrada/` y `output/` no se suben al repositorio (`.gitignore`).

Tus clips también tienen reglas: el contenido de CS2 hecho por fans está permitido dentro de las condiciones de Valve
para video. Si en tus clips aparecen otras personas (cámara, voz), pediles permiso.

Esto es información general, no asesoramiento legal.
