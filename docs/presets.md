# Presets: el estilo de tu canal

Un preset es un archivo JSON con el estilo de un canal: nombre y logo, colores, look de la imagen, títulos,
transiciones, efectos de kill, reglas de corte y mezcla de audio. El motor trae `presets/default.json` con **todas**
las claves y su valor de fábrica; tu preset solo nombra lo que cambia.

## Crear el de tu canal

```
presets/
  default.json            estilo base (no lo edites: es la referencia)
  micanal/
    preset.json
    logo.png              cuadrado, 500 px o más (se recorta en círculo)
```

`presets/micanal/preset.json`:

```json
{
 "name": "micanal",
 "description": "Mi Canal (twitch.tv/micanal)",
 "channel": {
  "name": "MI CANAL",
  "link": "twitch.tv/micanal",
  "url": "https://twitch.tv/micanal",
  "outro_text": "NOS VEMOS EN EL STREAM",
  "logo": "logo.png",
  "player": "MiNick"
 },
 "colors": {"ring": ["#FF5A1F", "#FFD23C", "#FF2E63"]}
}
```

Y en la raíz del repo, `config.json` para que todos tus proyectos lo usen:

```json
{"preset": "micanal"}
```

`python engine/preset.py` lista los presets y marca el del canal; `python engine/preset.py micanal` lo muestra ya
mezclado con el default. Una clave mal escrita da error con la lista de las válidas.

## Qué manda sobre qué

1. `"style"` en `projects/<nombre>/edit.json`: valores sueltos, solo para ese proyecto.
2. `"preset"` en `projects/<nombre>/edit.json`: otro preset para ese proyecto.
3. `"preset"` en `config.json`: el del canal.
4. `presets/default.json`.

`projects/<nombre>/logo.png`, si existe, reemplaza al logo del preset en ese proyecto.

## Grupos

| Grupo | Qué controla |
|---|---|
| `channel` | Nombre en la intro, texto y link del cierre, logo, nick del jugador en el killfeed |
| `colors.ring` | Los tres colores del anillo del logo (`#RRGGBB`) |
| `look` | Contraste de la curva, saturación, nitidez, bloom, viñeta |
| `captions` | Tamaño, posición y duración de los títulos de las plays ("ACE / AK-47") |
| `camera` | Zoom a la cámara del streamer en la apertura y en el cierre |
| `transitions` | Rotación entre plays, duración de cada tipo e `intensity` (1 = normal, 0.5 = más suave) |
| `kill_fx` | Rotación de efectos de kill, `intensity`, `decay` (cuánto duran) y colores de las kills de un ACE |
| `cuts` | Mínimos y techos de tiempo antes y después de cada kill (los usa `check_kills.py`), largo del cierre y del outro |
| `audio` | Balance juego/música, cuánto se aparta la música en cada tiro, reacciones, loudness |
| `output` | Bitrate del video final (Mbps) |

Los valores de fábrica son los que dan la calidad de referencia del motor. Cambiá de a uno y mirá el resultado con
`python engine/build.py projects/<nombre> --preview 12.5,40` antes de renderizar entero.

## Compartir un preset

Un preset es su carpeta: `preset.json`, el logo y, si querés, una imagen `muestra.jpg`. Para aportarlo al repo, sacá
el logo y los datos de tu canal (dejá solo el estilo) y mandalo a `presets/` en un pull request.
