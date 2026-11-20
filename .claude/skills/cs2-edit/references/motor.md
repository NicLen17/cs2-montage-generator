# Motor: fórmulas y parámetros ya implementados

**Leé esto solo si vas a modificar `engine/analyze_song.py`, `engine/render.py` o `engine/audio.py`, o si algo de eso falla.** Para un edit normal no hace falta: los scripts ya lo hacen. Cambiar `render.py` invalida la caché de pedazos (el primer render después tarda el tiempo completo). Todo efecto nuevo se activa **solo desde el plan**, sin cambiar el resultado de los proyectos viejos.

## Análisis de la canción (`analyze_song.py`)
- Onset percusivo preciso por beat: envolvente de RMS de 2 ms sobre `bp 35-160 Hz + 0.6*bp 1.5-8 kHz`, en una ventana de ±90 ms. Retroceder hasta el 30 % del pico da `hits`.
- Grilla regular (`polyfit` robusto con recorte de outliers) sobre `hits`; `TGT = where(|hits-grid| < 30 ms, hits, grid)`.
- Mapa de bombo por beat: energía < 130 Hz.
- Momentos vocales fuertes: envolvente armónica (HPSS, 300-3000 Hz).
- Golpes vocales dobles (pares separados 0.12-0.32 s) y repeticiones de sílabas (`projects/my_jealousy_v2/vocal_reps.py`): solo para pedidos especiales (ver `plan.md`).

## Imagen (`render.py`)
- **Dispositivo** (`WAKO_DEVICE` = `cpu` | `gpu` | `auto`, lo pone `build.py --device`): una sola lógica del edit. En GPU,
  al final de `render.py` se reemplazan las operaciones de imagen por las de `engine/gpu.py` (ModernGL, OpenGL 4.3):
  `grade`, `bloom`, `streak`, `affine/zoom/shift`, `hblur`, `radial_blur`, `rgb_split`, `leak`, `ring`, `blit`, `darken`,
  `logo_ring`, `paste_avatar`, `orbs` y las ayudas `clip`, `chmean`, `zeros`, `center_mean`, `to_u8`. `gpu.G` es una imagen en
  la VRAM (RGBA float32, BGR) que se usa como un array de numpy (`G + G`, `255 - G`, `máscara * G`, `G * np.array([b,g,r])`).
  - Las cuentas imitan a OpenCV: LUT + HSV de 8 bits con las tablas enteras de OpenCV, gaussianos con su tamaño de kernel
    (`round(sigma*4*2+1)|1` en float, `*3*2` en 8 bits) y borde REFLECT_101, `warpAffine` con coordenadas cuantizadas a
    1/32 y bicúbico A=-0.75 con borde REFLECT, `resize` lineal/área con las reglas de borde de OpenCV, redondeo `roundEven`.
  - **Regla para efectos nuevos:** escribí la versión numpy en `render.py` usando solo las ayudas (`clip`, `chmean`, `zeros`,
    nada de `f *=` sobre el cuadro de otro, nada de `f[a:b] = ...` fuera de `blit/darken/paste_avatar`) y, si usa una
    operación de OpenCV nueva, su shader en `gpu.py`. Compará los dos modos con `render.py <proyecto> raw t1,t2,... <carpeta>`
    con `WAKO_DEVICE=cpu` y `WAKO_DEVICE=gpu` (PSNR ≥ 45 dB en los cuadros del efecto).
  - **Lectura de clips en GPU (`HWReader`):** ffmpeg con `-hwaccel auto -fps_mode passthrough -pix_fmt nv12` (sin
    `passthrough` ffmpeg duplica cuadros en los clips con marcas de tiempo irregulares), salto con `-ss (idx-0.5)/fps`.
    El color se pasa a BGR en el shader `grade` con la cuenta exacta de swscale (BT.601 rango limitado, croma del vecino,
    punto fijo: `yv=((Y*8-128)*9539)>>16`, coeficientes 16525 / -3209 / -6660 / 13074). Verificado contra OpenCV en
    188 clips (1128 cuadros, saltos incluidos): idénticos. Quedan como mucho 6 lectores abiertos por proceso.
    `WAKO_HWDEC=0` vuelve a leer con OpenCV.
  - Salida en GPU: `to_nv12()` (BT.601 rango limitado, croma promedio 2x2) → el codificador de la placa la toma sin
    conversión en la CPU.
- Medido en my_jealousy_v3: motor viejo 330 s · CPU 281 s · GPU 55 s (6 procesos; 3 → 73 s, 4 → 62 s). Un proceso GPU hace
  ~110 cuadros/s; con varios, el límite es el motor de video de la placa (decodificar + codificar) al 100 %.
- Lectores perezosos por clip (`Reader`): leen en orden y saltan con `seek()` verificado (lee un cuadro, pregunta la
  posición real y, si se pasó, salta más atrás). Recién abierto, `s.i = -1`. Hasta el 19/11/2026 era -10, y si el primer
  cuadro pedido caía en los primeros 2 s del clip, todo ese tramo salía 9 cuadros (0.15 s) adelantado a la música y
  al efecto de kill. Los edits renderizados antes de esa fecha tienen tramos así.
- Modos: `preview t1,t2,...` (JPG de 640×360), `raw` (cuadros sin comprimir), `part a b salida [bitrate] [paso]` y
  `serve` (proceso fijo que recibe pedazos por stdin; lo usa `build.py`). Paso 2 = borrador (30 fps, 960×540).
- **Velocidad en CPU:** limitada por la RAM (cuadros float32 de 25 MB, decenas de pasadas por cuadro): con 5 procesos ya
  rinde lo mismo que con 10 o 12 (~30 cuadros/s en total). Cola de pedazos de 2 s + unión sin recodificar: 330 s → 281 s.
- **Color:** curva en S (`0.42*sigmoide + 0.58*lineal`), sombras frías y luces cálidas, saturación ×1.15, enfoque suave (`1.25*f − 0.25*blur(1.2)`), bloom leve (umbral 205), viñeta suave y un 30 % del cuadro anterior como motion blur leve.
- **Transiciones:** `whip_lr`/`whip_rl` (desplazamiento del 55 % del ancho, desenfoque horizontal de hasta 240 px, ±0.13 s), `light` (bloom y luz que cruza de izquierda a derecha, ±0.17 s), `zoom` (desenfoque radial, ±0.13 s), versiones cortas dentro de una play (`whip_short` ±0.075, `light_short` ±0.085), `black_in` (±0.70), `cut`.
- **Mega:** punch-in a 1.6x con desenfoque radial, separación RGB de 24 px, luz horizontal, destello blanco solo en el centro (±7 %) y B que sale de la luz. Whoosh y golpe grave en el audio.
- **Efectos de kill** (`KILL_FX` rota): `bloom`, `chroma_zoom`, `shake_blur`, `flash`, `radial_zoom`, `pop`. Decaimiento entre 0.11 y 0.2 s, rampa de entrada de ~3 cuadros, sacudida como oscilación suave (nunca ruido por cuadro).
- **Flashing light:** destello de 0.22, bloom de 0.5, luz horizontal **normalizada** (dividir por `max*1.6` y multiplicar por 120, nunca por 255) y un anillo.
- **Cámara lenta (x4, 60 → 240 fps) sobre una ventana corta, desaturación leve.** Con RIFE instalado (`tools/rife/`, `python engine/setup_rife.py`): `rife-ncnn-vulkan -n 4N -m rife-v4.6 -j 2:4:4` en la GPU sobre los cuadros extraídos con `-fps_mode passthrough`; cada 4.º cuadro es el original exacto, ~10 s por cámara lenta (medido en my_jealousy c26). Sin RIFE: `minterpolate=fps=240:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1` (CPU, ~70 s por segundo). `WAKO_RIFE_GPU=N` elige la placa si hay varias.
- **Títulos:** Montserrat 800 de 54 px más subtítulo Montserrat 300 de 24 px, en `y = H−205`, 1.5 s con fade y sombra suave.
- Encoder elegido por `encoders.py` (AMF en la RX 7900 XT). Salida final 30 Mbps, AAC 320k.

## Audio (`audio.py`)
- Decodificación: `decode_all()` baja la canción y el audio de todos los clips del plan con **una sola** llamada a ffmpeg y `dec()` recorta en memoria (abrir ffmpeg cuesta ~0.5 s en Windows: antes eran ~50 llamadas, 27 de los 38 s de la mezcla; ahora ~12 s). Además el salto `-ss` de ffmpeg en el mp3 dejaba 25-100 ms de basura del decodificador al principio de cada tramo de la canción; el recorte en memoria no.
- Todo a 48 kHz. Crossfade en los cortes siguiendo la superposición de las transiciones.
- **Mezcla 2 (por defecto desde el 20/11/2026; `AUDIO_MIX = 1` en el plan vuelve a la vieja).** Re-renderizar un proyecto viejo ya le cambia el audio (el audio se regenera en cada `build.py`; no hay caché).
  - Nivel por clip: percentil 90 del RMS de 400 ms (pasa altos 120 Hz) de todos sus tramos; ganancia hacia la mediana de los clips, limitada a ×0.6-×1.8.
  - Nivel contra la música: `game_lift = 10^((GAME_VS_MUSIC − (dB(game) − dB(song*MUSIC_BED)))/20)` medido solo en las plays, limitado a ×1-×6 (en my_jealousy_v3 salió ×1.74). `GAME_VS_MUSIC = −11.5` (punto medio aprobado; −6 se sintió muy alto).
  - Juego: `GAME_GAIN = 1.0` (0.55 en el cierre, 0.5 en cámara lenta), `game += GAME_PRESENCE*bp(2-6 kHz)(game)` (0.25), `game *= 1 + GAME_EMPH*tr` con `GAME_EMPH = 2.35`.
  - Música: `hold = maxfilter60ms(tr)`; `duck = 1 − MUSIC_DUCK*clip(smooth100ms(hold)*2.5)` con `MUSIC_DUCK = 0.52`; ecualizador dinámico `song −= bp(1.2-6 kHz)(song) * MUSIC_CARVE*clip(smooth80ms(hold)*2.5)` (0.35); `MUSIC_BED = 0.85` debajo del gameplay y 0.92 en logo, interludio y outro (rampa de 350 ms).
  - Normalización al pico real (sobremuestreo 4x) en −1.5 dBTP y después una prueba en AAC 320k: el códec sumaba ~1.4 dB en los tiros (salía −0.1 dBFS); si el pico codificado pasa de −1.3, se baja y se repite. Queda en unos −9.6 LUFS (mezcla 1: pico de muestra 0.89, −9.3 LUFS).
- **Énfasis de transitorios:** `hf = bp 1.2-9 kHz`; `tr = clip(rms3ms/rms80ms − 1.2, 0, 3)/3`, máximo de 10 ms y suavizado de 50 ms, multiplicado por el nivel. (Mezcla 1: `game *= 1 + 1.7*tr`, `music *= 1 − 0.42*clip(smooth120ms(tr)*2.5)`, juego 0.78 / 0.40 en el cierre.)
- **Reacciones** (`reactions.json` de `engine/reactions.py`): Demucs `htdemucs --two-stems=vocals` sobre el audio de cada clip → `clip_stems/cN/{vocals,no_vocals}.wav`. Envolvente de 60 ms en pasos de 10 ms; "charla" = mediana de los cuadros con voz (> p99 − 45 dB); umbral `max(charla + 8, min(p97, charla + 14) − 1)` dB; tramos ≥ 0.22 s (cerrados con 0.25 s) con planitud espectral 200-3000 Hz < 0.35 (voz, no un tiro colado); se extiende hasta que cae 10 dB del pico (máx 2.5 s). Solo si arranca en `[kill − 0.3, kill + 3.5]` de una kill que cierra racha (la siguiente a más de 3 s). Grupal o individual (`group_score`): cuadros de 128 ms en pasos de 20 ms, multi-f0 iterativo (suma de 10 armónicos con peso 0.84^(h−1), f0 de 80 a 900 Hz en cuartos de semitono; se quita la voz más fuerte y se busca otra, hasta 3, mientras la saliencia sea ≥45 % de la primera). Segunda voz = la que no está a octava, quinta, doceava ni a menos de 2 semitonos de la primera, y cuenta si sigue continua (<1 semitono) al cuadro siguiente. Grupal si es ≥20 % de los cuadros fuertes o un tramo ≥0.10 s. En `audio.py` cuenta solo si es grupal (`REACT_KINDS`), si esa kill es la última de ese clip que se ve en el video, y solo dentro de su tramo (termina en el corte, nunca suena sobre otro clip): se suma `vocals * REACT_GAIN (1.3) * ganancia del juego de ese clip` con rampas de 50/220 ms y la música baja `REACT_DUCK = 0.45`: entra en 50 ms, se mantiene hasta `REACT_HOLD = 0.6` s después del grito (sin pasar el corte del tramo) y vuelve con medio coseno en `REACT_RELEASE = 0.5` s (suavizado final de 80 ms).
- **Balance:** `audio_balance.txt` = dB(juego+reacciones) − dB(música) en las plays, y por kill el pico de 10 ms del juego contra el de la música en `[kill − 30 ms, kill + 150 ms]`. Mezcla 1 en my_jealousy_v3: −15.5 / −19.1 dB; prueba "muy alta": −3.4 / −1.9 dB; mezcla 2 actual (punto medio): −9.5 / −7.9 dB.
- Whoosh paneado de izquierda a derecha en cada whip, shimmer agudo en las de luz, whoosh en el zoom de apertura y en el de cierre.
- Fundido de entrada de la música de 0.8 s, de salida durante el cierre. Saturación suave con `tanh`, unos −10 LUFS integrados.
- Pruebas sin tocar el proyecto: `WAKO_AUDIO_MIX=1|2`, `WAKO_GAME_VS_MUSIC=<dB>`, `WAKO_AUDIO_OUT=<wav>` y `WAKO_AUDIO_LOG=<txt>` como variables de entorno de `audio.py`.
