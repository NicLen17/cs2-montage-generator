# Cómo extender el motor

Antes de tocar nada, y de nuevo al terminar:

```
python -m pytest                                        rápido: planificador, presets, editor web
python engine/regress.py projects/<proyecto> --save     una vez: guarda la referencia de imagen de un proyecto tuyo
python engine/regress.py projects/<proyecto>            compara contra la referencia (--device gpu, --cross)
python -m pytest --slow                                 suma el detector de kills y la regresión de imagen
```

Un cambio que no busca alterar la imagen tiene que dar 99 dB en CPU contra la referencia.

## Dónde está cada cosa

| Archivo | Qué hace |
|---|---|
| `engine/analyze_song.py` | Beats, golpes, grilla, momentos de sincronía, energía (`song.json`) |
| `engine/killfeed.py`, `analyze_clips.py`, `nick.py` | Lee el killfeed de CS2 y el disparo en el audio (`kf.json`, `shots.json`) |
| `engine/score.py` | Puntaje automático de cada play |
| `engine/planner.py` | De `edit.json` al timeline: cada kill en su golpe, intro, revelación, cierre, transiciones |
| `engine/auto.py` | Arma `edit.json` solo a partir del análisis |
| `engine/render.py`, `gpu.py` | Dibuja cada cuadro (CPU con OpenCV, GPU con shaders: tienen que dar lo mismo) |
| `engine/audio.py` | Mezcla juego, música, transiciones y reacciones |
| `engine/build.py` | Reparte el render en pedazos, usa caché, une y verifica |
| `engine/preset.py`, `presets/` | El estilo como datos |
| `engine/ui/` | Editor web local |

## Sumar un preset

Es lo más fácil de aportar y no toca código: ver `docs/presets.md`. Mandalo sin logo ni datos de tu canal.

## Sumar una transición

1. `presets/default.json`: su duración en `transitions.durations` (la mitad de lo que dura, en segundos).
2. `engine/render.py`, en `render_f`: una rama más en el bloque de transiciones. Recibe los cuadros `A` (el que sale) y
   `B` (el que entra) y `p` de 0 a 1. Usá solo las operaciones que existen en los dos modos (`zoom`, `shift`, `hblur`,
   `radial_blur`, `bloom`, `leak`, `rgb_split`, sumas y productos): así anda en CPU y en GPU sin escribir un shader.
3. Multiplicá su fuerza por `TI` para que respete `transitions.intensity`.
4. Usala en un proyecto con `"tin": "<nombre>"` en una play o agregándola a `transitions.rotation`.
5. `python engine/regress.py projects/<proyecto> --cross` tiene que dar más de 45 dB entre CPU y GPU.

## Sumar un efecto de kill

Igual que una transición, en el bloque `# kill effects` de `render_f`: el efecto suma a los acumuladores (`z` zoom,
`split` separación de color, `white` destello, `bl` bloom, `dx`/`dy` sacudida) según `e`, que decae desde la kill.
Agregá su nombre a `kill_fx.rotation` del preset.

## Si necesitás una operación de imagen nueva

Va en los dos lados: la función en `render.py` (numpy/OpenCV) y su gemela en `gpu.py` (shader), con el mismo nombre y
los mismos argumentos, y se enchufa en la lista de reemplazos al final de `render.py`. La regla del proyecto es que
los dos modos den el mismo cuadro: medilo con `--cross`.

## Otros HUD, resoluciones y juegos

El detector está hecho para el killfeed de CS2 en 16:9 con la escala de HUD de fábrica; `killfeed.layout()` calcula el
recorte para otros aspectos y escalas, pero solo 16:9 está probado con clips reales. Si tenés clips en 4:3 o 16:10,
lo más útil que podés aportar es correr `python engine/eval_kills.py` con ellos y contar qué da. Otros juegos no están
soportados: harían falta su propio lector de kills y sus propias reglas de corte.
