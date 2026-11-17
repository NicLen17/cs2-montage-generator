# Motor: fórmulas y parámetros ya implementados

**Leé esto solo si vas a modificar `engine/analyze_song.py`, `engine/render.py` o `engine/audio.py`, o si algo de eso falla.** Para un edit normal no hace falta: los scripts ya lo hacen. Cambiar `render.py` invalida la caché de pedazos (el primer render después tarda el tiempo completo). Todo efecto nuevo se activa **solo desde el plan**, sin cambiar el resultado de los proyectos viejos.

## Análisis de la canción (`analyze_song.py`)
- Onset percusivo preciso por beat: envolvente de RMS de 2 ms sobre `bp 35-160 Hz + 0.6*bp 1.5-8 kHz`, en una ventana de ±90 ms. Retroceder hasta el 30 % del pico da `hits`.
- Grilla regular (`polyfit` robusto con recorte de outliers) sobre `hits`; `TGT = where(|hits-grid| < 30 ms, hits, grid)`.
- Mapa de bombo por beat: energía < 130 Hz.
- Momentos vocales fuertes: envolvente armónica (HPSS, 300-3000 Hz).
- Golpes vocales dobles: picos vocales de a pares separados 0.12-0.32 s.
- Repeticiones de sílabas: ataques vocales seguidos con timbre parecido sobre la voz separada (`vocal_reps.py` de `projects/my_jealousy_v2`).

## Imagen (`render.py`)
- Lectores perezosos por clip, que se reabren al saltar. Modo `preview t1,t2,...` que guarda JPG de 640×360.
- **Color:** curva en S (`0.42*sigmoide + 0.58*lineal`), sombras frías y luces cálidas, saturación ×1.15, enfoque suave (`1.25*f − 0.25*blur(1.2)`), bloom leve (umbral 205), viñeta suave y un 30 % del cuadro anterior como motion blur leve.
- **Transiciones:** `whip_lr`/`whip_rl` (desplazamiento del 55 % del ancho, desenfoque horizontal de hasta 240 px, ±0.13 s), `light` (bloom y luz que cruza de izquierda a derecha, ±0.17 s), `zoom` (desenfoque radial, ±0.13 s), versiones cortas dentro de una play (`whip_short` ±0.075, `light_short` ±0.085), `black_in` (±0.70), `cut`.
- **Mega:** punch-in a 1.6x con desenfoque radial, separación RGB de 24 px, luz horizontal, destello blanco solo en el centro (±7 %) y B que sale de la luz. Whoosh y golpe grave en el audio.
- **Efectos de kill** (`KILL_FX` rota): `bloom`, `chroma_zoom`, `shake_blur`, `flash`, `radial_zoom`, `pop`. Decaimiento entre 0.11 y 0.2 s, rampa de entrada de ~3 cuadros, sacudida como oscilación suave (nunca ruido por cuadro).
- **Flashing light:** destello de 0.22, bloom de 0.5, luz horizontal **normalizada** (dividir por `max*1.6` y multiplicar por 120, nunca por 255) y un anillo.
- **Cámara lenta:** `minterpolate=fps=240:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1` sobre una ventana corta, desaturación leve.
- **Títulos:** Montserrat 800 de 54 px más subtítulo Montserrat 300 de 24 px, en `y = H−205`, 1.5 s con fade y sombra suave.
- Encoder elegido por `encoders.py` (AMF en la RX 7900 XT). Salida final 30 Mbps, AAC 320k.

## Audio (`audio.py`)
- Todo a 48 kHz. Juego con ganancia 0.78 (0.40 en el cierre), crossfade en los cortes siguiendo la superposición de las transiciones.
- **Énfasis de transitorios:** `hf = bp 1.2-9 kHz`; `tr = clip(rms3ms/rms80ms − 1.2, 0, 3)/3`, máximo de 10 ms y suavizado de 50 ms, multiplicado por el nivel. `game *= 1 + 1.7*tr` y `music *= 1 − 0.42*clip(smooth120ms(tr)*2.5)`.
- Whoosh paneado de izquierda a derecha en cada whip, shimmer agudo en las de luz, whoosh en el zoom de apertura y en el de cierre.
- Fundido de entrada de la música de 0.8 s, de salida durante el cierre. Saturación suave con `tanh`, pico en −1 dBFS, unos −10 LUFS integrados.
