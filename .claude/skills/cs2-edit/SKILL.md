---
name: "cs2-edit"
description: "Reglas y flujo del edit largo del proyecto wako-edits: arma, corrige y renderiza en esta PC (GPU local) montajes de CS2 estilo WAKO TV con cortes al beat, efectos de kill, transiciones con luz, intro con logo y cierre con reacción. Se carga siempre que se arma un video (también dentro de cs2-pack, que es el arranque por defecto cuando llegan clips y canción). Usala sola cuando el usuario pida solo el video largo ('solo el edit', 'sin shorts', /cs2-edit) o cambios a un edit ya hecho ('en el 1:23 no se ve la kill', 'subí el juego', 'hacé una v4'). Usala en lugar de anthropic-skills:cs2-edit."
---

# CS2 Edit — montaje de plays estilo WAKO TV

Entrada: clips .mp4 de Twitch (1080p60, cámara del streamer arriba a la izquierda) y un archivo de audio con la canción. Salida: un MP4 1080p a 60 fps, de 2 a 3:30 según el tema, guardado en `output/<nombre>/video/`.
Este skill corre **en la PC del usuario** con Claude Code, dentro del proyecto `wako-edits`. Cada video es una carpeta `projects/<nombre>/` (clips copiados como `clips/c1.mp4…`, `song.mp3`). Nunca muevas ni modifiques los originales del usuario. Los scripts están en `engine/` (ver CLAUDE.md).
Esta es la versión del proyecto y la única que se actualiza. La de la cuenta (`anthropic-skills:cs2-edit`) quedó congelada: no la uses.

**Archivos de apoyo (leelos en el paso indicado, no antes):**
- `references/plan.md` — **obligatorio antes de escribir o modificar `plan.py`** (formato de plays, anclas, cómo cuadrar residuos).
- `references/errores.md` — repasalo antes del render final y cuando el usuario marque un error.
- `references/motor.md` — solo si vas a tocar `render.py`, `audio.py`, `reactions.py` o `analyze_song.py`.

## 0. Antes de empezar
- Si falta la canción, pedila: YouTube no se puede bajar. Si el usuario no adjuntó el logo, se usa `engine/assets/logo.png` (círculo con el avatar del canal).
- Datos del canal (por defecto): **WAKO TV**, `twitch.tv/el_wako`, cámara en `(25,18)-(490,278)` y a veces abajo a la izquierda, en `(25,802)-(490,1062)` o arriba a la derecha. Verificalo en un fotograma de cada clip.
- Nunca escribas la letra de la canción en pantalla: tiene derechos de autor. Tampoco hay frases ni palabras animadas sobre las plays (ver §7).
- Armá una lista de tareas: análisis → plan → chequeo de kills → preview → render → revisión → entrega.
- **Catálogo de clips** (skill `clip-catalog`): antes de analizar, `python engine/catalog.py scan` y, después de copiar los clips, `python engine/catalog.py prefill projects/<nombre>`. Los clips ya verificados en otro edit traen sus kills y disparos y no se vuelven a verificar. Usá `python engine/catalog.py list` para elegir plays (puntaje, arma, mapa, si ya se usó).

## 1. Analizar la canción
`python engine/analyze_song.py projects/<nombre>` guarda `beats.npy`, `hits.npy` y `grid.npy` (onset real de cada golpe, grilla regular, `TGT`). Las kills clave se alinean a `TGT`, nunca al beat estimado.
- Mapa de bombo por beat: encontrá el **drop** (donde entra la batería) y el **corte de batería** (break) que va antes del segundo drop. La estructura sale de ahí.
- Si la canción arranca con muchos segundos sin batería, `SONG_A0` saltea parte de esa intro (empezando en un compás) para que el logo dure 6 a 8 s.
- Marcá momentos vocales fuertes (una nota sostenida): sirven para la transición "mega" y para un flick destacado.
- Contrabeats (beats impares respecto del drop, los chasquidos o palmas): la última play debe caer ahí.
- **Momentos para sincronizar (obligatorio, pedido del 20/11/2026):** `analyze_song.py` lista los candidatos (`sync.json`): **entra la batería**, **vuelve el bombo después de un corte**, **sube la energía**, **entra o se corta la voz**. No todos son drops o estribillos: también cuentan las secciones con buen ritmo que arrancan después de un corte o de un valle. **Cada uno que se oiga como un cambio fuerte lleva una kill exacta o el arranque de una buena play.** El usuario marcó secciones "que simplemente están sonando" en My Jealousy, I Don't Like, Castlevania (la que más) y Faster N Harder.
  - **Confirmá el beat exacto con la tira beat por beat** que imprime el análisis (volumen total / graves): el drop es el beat donde el bajo vuelve o el primero que suena con todo, **no siempre el primer tiempo del compás**. En "Faster N Harder" el bajo se corta en 78.42 y vuelve con todo en 78.91 (2.º tiempo): ese era el drop de 1:12 que quedó sin kill. Si el bombo vuelve suave y crece, el drop es el golpe fuerte que sigue.
  - Los elegidos van en `SYNC = [tiempos de canción]` del plan; `check_kills.py` marca como problema cada uno sin kill exacta. Se anclan con `kill_at` / `kill_at_seg`.
- **Mapa de secciones:** energía de la pista sin voz compás por compás (separá voz y música con Demucs: `python -m demucs --two-stems=vocals -n htdemucs -o stems song.mp3`). Cada subida fuerte después de un compás "valle" es un **drop o estribillo**; anotalos todos (en "My Jealousy": 16, 32, 64, 80, 96 y 112 s) y clasificalos: **movido** (batería completa, frenético) o **de un golpe** (entra suave o con un solo impacto).
- **Golpes de voz aislados** ("stop", un grito, una palabra seca con silencio después), casi siempre en el compás valle justo antes de un drop: van con una kill exacta. Buscalos con la voz separada (ataque fuerte + silencio después) y confirmá con el usuario si hay dudas.
- **Golpes secos de la música** (los picos más fuertes de onset en la pista sin voz dentro de un drop): ahí el video también corta.
- **Efectos atados a una canción concreta** (cortes dobles en un "bang bang", una kill por cada sílaba repetida, etc.) **no se hacen por defecto**: fueron pedidos especiales de canciones puntuales. Solo si el usuario los pide para ese video (cómo se arman: `references/plan.md`, "Pedidos especiales").

## 2. Analizar los clips
0. **Preparar los clips:** copiá cada original a `clips/cN.mp4` en orden de fecha y guardá la correspondencia en `clips_map.txt` (`c3 <- archivo_original.mp4`). **Clips de CS:GO** (antes de fines de septiembre de 2023, HUD viejo): no se usan; marcalos como DEPRECADO en `clips_map.txt` (el catálogo ya los marca `csgo`). Si un clip no es de 60 fps (los viejos vienen a 50), en la copia pasalo a 60 con `minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1` (en segundo plano: es lento). Armá una grilla con un cuadro por clip y anotá dónde está la cámara en cada uno (a veces va arriba a la derecha y tapa el killfeed). El nick del streamer cambia entre clips ("Wako", "ElWako", "El pana piolin").
1. `python engine/analyze_clips.py projects/<nombre>` lee el killfeed y deja en `sheets/` hojas de contexto a 1 fps (192×108, 10 columnas: mapa, arma, run boost, humo, giro), `kf_resumen.txt`, `kf_dudosos.jpg` y `kf*.jpg`. Los clips que `prefill` marcó como verificados (`verified.json`) no se vuelven a escanear.
2. **Kills propias = el killfeed es la fuente de verdad** (`engine/killfeed.py`). Cada entrada con borde rojo (las que involucran al jugador) se sigue en el tiempo y se lee quién mató: **nombre del jugador a la izquierda = kill**, a la derecha = muerte, en el medio ("Compañero + jugador") = asistencia. **El jugador se deduce de cada play**: es el nombre que se repite en sus entradas rojas (no hay nicks fijos; si un clip tiene una sola entrada, se usan los nombres deducidos de los otros clips del proyecto). Salen `kf_auto.json` (mismo formato de siempre: `{clip: [tiempos]}`, que también arranca `kf.json`) y `kf_conf.json` (cada kill con confianza 0-1 y motivo, más las muertes, asistencias y entradas repetidas descartadas). Medido contra 150 kills verificadas del catálogo (`python engine/eval_kills.py --baseline`): precisión 83 % y recall 87 % a ±0.35 s, 89 % y 93 % a ±0.7 s (el primer detector daba 36 % y 63 %); las seguras aciertan 96 % y quedan unas 14 dudosas en 150 kills. Lee bien las entradas que suben cuando vence la de arriba, el ícono de cegado antes del nombre, "Jugador + Compañero" (kill) contra "Compañero + Jugador" (asistencia), las muertes propias y la bomba, y no acepta kills después de que el jugador murió. El tiempo es el de la entrada en el killfeed (0.1-0.45 s después del disparo).
3. **Mirá a ojo solo lo dudoso** (salvo los clips verificados que vienen del catálogo): `sheets/kf_resumen.txt` dice por clip cuántas kills seguras y dudosas hay, y `sheets/kf_dudosos.jpg` muestra solo las dudosas (borde rojo, con el motivo) y los clips **SIN KILLFEED LEGIBLE** (la cámara del streamer encima del killfeed, ver abajo: esos se revisan enteros). En `sheets/kf*.jpg` está cada kill (verde = segura). Lo que el detector no ve: entradas que aparecen con fondo rojo o en plena pantalla roja de muerte, y la animación de entrada contra el cielo (a veces la toma 0.3-0.5 s tarde). Para buscar el instante exacto de una kill que falte: conteo por cuadro (`cntN.npy`) o una tira a 10 fps. Dos líneas que aparecen juntas con AWP suelen ser un collateral, y las líneas de compañeros no cuentan ("Compañero + Wako → X" es una asistencia, el detector ya la descarta).
   - **Contá las kills de cada clip contra el killfeed final** (cuántas entradas propias hay al terminar la ronda). Si tu lista tiene menos, falta una: las kills muy seguidas o tapadas por un humo se pierden en la detección automática. Ese fue el error más repetido: plays con 4 kills mostradas como 3. Arriba a la izquierda, debajo del dinero, las calaveras cuentan las kills de la ronda.
   - **Si la cámara tapa el killfeed:** los retratos de arriba (el enemigo muerto se pone gris) y el audio sirven solo como pista: el gris llega tarde o se confunde con destellos, y en el audio se mezclan los tiros enemigos. **Confirmá cada kill cuadro a cuadro** (tira a 20 fps: fogonazo de tu arma + enemigo cayendo). En el clutch de Mirage las kills estimadas por retratos salían 0.3-1.6 s antes y el video terminó mostrando un tiro errado y sin la kill con pistola.
   - Si el disparo detectado cae a menos de 0.05 s del killfeed o más de 0.46 s antes, es sospechoso: revisalo con una tira de cuadros cada 0.1 s (fogonazo del arma, retroceso) y corregilo a mano.
   - Kills a través de paredes o humo: dejá más cola después (1 a 1.5 s), para que se entienda que murió alguien. Si el tiro es a través de humo, dale también más lead.
   - Escribí la lista final en `kf.json` y corré `python engine/analyze_clips.py projects/<nombre> --shots`.
   - Después, **reacciones**: `python engine/reactions.py projects/<nombre> --all` (Demucs, ~10-20 s por clip; en segundo plano si son muchos). Anotá qué plays traen un festejo **grupal** al final: suman para elegirlas y ordenarlas (ver §8).
4. **Disparo exacto** = onset en el audio del clip, banda 1.5-9 kHz, ventana `[kf-0.45, kf+0.06]`. El killfeed aparece entre 0.1 y 0.45 s después del tiro. Si el desfase es mayor a 0.46 s o coincide con el de la kill anterior, usá `kf-0.12`.
5. Por clip, anotá: kills con sus tiempos, qué la hace especial (360, flick, cambio de arma, enemigo cayendo, a través del humo, collateral, run boost, ACE), si al final el jugador muere y dónde aparece la reacción en cámara.
6. **Guardá lo verificado en el catálogo:** `python engine/catalog.py import projects/<nombre>` y completá arma, mapa, puntaje y etiquetas de los clips nuevos con `catalog.py set` (ver skill `clip-catalog`). El próximo edit los reusa.

## 3. Visibilidad de cada kill (la corrección más repetida)
En los tres primeros edits, la mayoría de las correcciones fueron por kills que faltaban o no se llegaban a ver. Antes de cualquier preview, cada kill tiene que cumplir estos mínimos. Son pisos, no valores fijos: si la play lo pide, dale más.

| Tipo de kill | Antes del disparo | Después del disparo |
|---|---|---|
| Normal, enemigo visible | 0.8 s | 0.6 s |
| Primera kill de una play | 1.2 s | 0.6 s |
| Poco visible: a través de pared o humo, lejana, enemigo que cae fuera de cuadro, estando flasheado, no scope | 1.2 s | 1.2 s |
| Movimiento técnico (360, flick, cambio de arma, run boost, salto) | desde que empieza el movimiento + 0.3 s | 0.8 s |
| Última kill de una play (antes de transición) | 0.8 s | 0.7 s **más** la mitad de la transición |

- **Ninguna kill dentro de una transición:** el disparo tiene que estar al menos a la mitad de la transición + 0.15 s del centro del corte (whip ±0.13 → 0.28 s; light ±0.17 → 0.32 s; mega ±0.30 → 0.45 s). La transición tapaba kills ("hice la transición rápido y no se ve que disparé").
- **Kills seguidas en un mismo tramo** (menos de 1.5 s entre sí): no se cortan entre ellas; van en el mismo tramo continuo.
- **El título manda el conteo:** si dice 4K o ACE, tienen que verse 4 o 5 kills completas con los mínimos de arriba. Si no entran, cambiá el título o sumá tramos, nunca al revés.
- **Chequeo automático:** `python engine/check_kills.py projects/<nombre>` recorre todas las kills de `kf.json` de cada clip usado e imprime una tabla con pre, post y distancia a la transición más cercana. Marca las kills que faltan en el video y las que quedan debajo del mínimo. Las kills poco visibles o con movimiento técnico se declaran en el plan con `hard=[i]` y `tech={i: inicio_del_movimiento}`. **No renderices hasta que la tabla salga limpia.** Al final cruza `kf.json` con el killfeed (`kf_conf.json`): **avisos del KILLFEED** = kills del jugador que el killfeed muestra y no están en `kf.json` (la tabla no las controla, así que pueden quedar cortadas o fuera del video) y kills de `kf.json` sin entrada en el killfeed. Resolvé cada aviso a ojo antes del render.
- Si hace falta tiempo para cumplir los mínimos, sacalo de tiempos muertos (pre-rolls largos sin acción, colas después del "RONDA GANADA") o descartá la play más floja. Nunca recortes una kill.

### Tiempos muertos (techos, el otro lado de los mínimos)
Los mínimos de arriba evitan que una kill no se entienda; estos techos evitan que el edit pierda ritmo. En un edit frenético hasta unos décimos de más mirando la nada se sienten largos, y el usuario los marcó varias veces.
- **Decidí con el contexto de la ronda:** antes de la primera kill de cada toma mostrá solo lo que la explica (el enemigo apareciendo, el peek, el giro, el salto, el apuntado del flick). Después de la última kill, solo lo que hace falta para entender que murió. Si no aporta, se corta.
- **Techos por defecto** (desde el inicio de la toma hasta su primera kill / después de su última kill, sin contar la media transición):

| Caso | Antes, máximo | Después, máximo |
|---|---|---|
| Primera kill de una play | 1.6 s | — |
| Primera kill de un tramo siguiente (después de un corte dentro de la play) | 1.3 s | — |
| Última kill de una toma, normal | — | 0.9 s |
| Poco visible (humo, pared, lejana, cae fuera de cuadro) | 1.8 s | 1.6 s |
| Entre dos kills dentro de la misma toma | 2.0 s | |
| Tramos frenéticos (los drops movidos, `FRANTIC` en el plan) | ×0.75 | ×0.75 |

- **Más tiempo solo con razón concreta:** wallbang o kill a través de humo (se tiene que entender que murió alguien), movimiento técnico (el giro entero), un enemigo que se acerca a la vista, una rotación que explica la jugada, **una reacción grupal (festejo de varios) después de la kill que cierra la play** (§8: `check_kills.py` la justifica sola). Declaralo en el plan con `hard=[i]`, `tech={i: inicio}` o `ctx={i: (pre_max, post_max)}`.
- **Siempre se corta:** mirar a la nada, caminar o esperar sin enemigos, recargar, cambiar de arma sin amenaza, el cartel de "RONDA GANADA" (salvo en el cierre con la reacción), el scope vacío, un tiro errado antes de la kill (en el clutch de Mirage se veía un tiro de AWP fallado y el usuario lo pidió sacar).
- **Huecos dentro de una play:** si entre dos kills de la misma toma pasan más de ~2 s sin nada, partí la toma en dos tramos con un corte corto en vez de mostrar el viaje.
- **Ojo con el redondeo al beat:** la kill clave cae en el *siguiente* `TGT` después de `cursor + lead`, así que el lead real puede ser hasta 0.5 s más largo que el pedido. Pedí leads en el piso (1.2 / 0.8) y dejá que el redondeo complete; si el chequeo marca tiempo muerto, bajá el lead pedido o cambiá el orden de las plays.
- `engine/check_kills.py` lista estos avisos (**TIEMPO MUERTO**) debajo de la tabla. Resolvelos o justificalos antes del render, igual que los mínimos.

## 4. Reglas de corte (las que más pidió el usuario)
- **Nunca acelerar ni hacer rampas de velocidad en el gameplay.** Los tiempos muertos se sacan con cortes, siempre a velocidad 1x.
- **Mostrar la play completa:** todas las kills del clip y el contexto que la hace impactante (el giro entero del 360, el enemigo cayendo desde antes, el cambio rápido a la Deagle, el salto del run boost, el apuntar abajo antes del flick). Nunca terminar un tramo mirando a la nada y nunca cortar antes de la última kill.
- Si un clip es ACE o 4K, venderlo así: las 5 o 4 kills y el título correcto. El arma del título sale del ícono del killfeed de esas kills (y de la lista de armas del HUD), no de adivinarla (una vez se puso "DEAGLE" en una Glock y "4K" en un ACE; una M4 con silenciador y asa es M4A1-S). Si la play cambia de arma, poné el mapa como subtítulo.
- Si el clip termina con el jugador a punto de morir, cortar justo después de la última kill propia, no en el momento ambiguo.
- Lead antes de la kill clave del primer tramo: entre 1.0 y 2.0 s, más contexto si la play lo pide. Tramos siguientes de la misma play: unos 0.5 s. Cola después de la última kill: de 0.5 a 0.7 s. **Siempre respetando los mínimos de §3**, que mandan sobre estos valores.
- **Kill clave de cada tramo exactamente en un `TGT`** (0 ms). Las kills seguidas quedan donde ocurrieron en la partida.
- **La canción suena de corrido, sin saltos.** Ajustá la cantidad de plays y los leads para que la primera parte llegue justo al break. Si es inevitable, el único salto permitido es dentro del negro del interludio, con crossfade de 25 ms.
- Si no alcanzan las plays, sumá contexto (leads más largos) antes de cortar la canción. Si sobran, descartá las de menor impacto (una sola kill sin nada especial).
- Orden: la intensidad va subiendo. Primera parte: one taps y 3K. Cierre de la primera parte: un collateral y un ACE. Segunda parte (después del drop): las plays más fuertes. **La play con zoom a la reacción del streamer siempre va última.**

### Drops y estribillos (pedido explícito del usuario)
- **Todo drop y todo estribillo arranca con una kill exactamente en su golpe** (anclala con `kill_at`), con un efecto acorde al impacto. Nunca una transición en el drop y la kill un segundo después, ni la kill un poco antes del drop.
- **Lo mismo para cualquier sección con buen ritmo** (vuelta del bombo después de un corte, subida de energía, entrada o corte de la voz; todos los de `SYNC`): una kill exacta, un tiro destacado con su efecto, o el arranque de una buena play. Ninguna sección fuerte puede quedar "sonando sola" en medio de una play cualquiera. Si una play larga cruza un momento de `SYNC`, anclá a ese momento la kill de la play que mejor quede (`kill_at_seg`).
- **La play del drop tiene que estar a la altura del drop:**
  - Drop **movido** (batería completa, frenético, como "My Jealousy"): play frenética, idealmente **3 kills o más en 3-4 s** (spray, ACE rápido, triple con pistola). Dos taps tranquilos no alcanzan.
  - Drop **de un golpe** o suave: alcanza un one tap o una o dos kills limpias.
- Reservá las mejores plays rápidas para los drops y armá el resto alrededor de esos anclajes. Si un drop queda sin una play digna, reorganizá clips o leads antes de aceptar una kill floja.
- **Golpes de voz aislados ("stop"):** una kill exacta en el golpe. Si el golpe está en el compás antes de un drop, buscá una play que tenga kills tanto en el golpe como en el drop (por ejemplo un ACE de pistola cuya 4.ª kill cae en el drop y la 2.ª en el "stop").
- **Drop principal (después de la revelación, §5):** la mejor play arranca su primera kill exactamente en el drop. Si el drop trae golpes secos seguidos, se puede cortar en cada uno (ráfaga de la misma play con `sync=0.0`, ver `references/plan.md`).
- **Colas:** después de la última kill de una play, cortá a la transición apenas se cumple el mínimo de §3. Unos décimos de más mirando a la nada se notan. **Excepción:** si la play trae una reacción grupal al final (§8), la cola llega hasta que se oiga el festejo.
- **Leads del primer tramo:** si el clip tiene mucho tiempo sin acción antes de la primera kill, no pases de ~1.2-1.6 s (el usuario marcó esperas largas antes de empezar a matar).

## 5. Estructura del video
1. **Intro con logo** (de 0 a un compás antes del drop): avatar circular con anillo degradado violeta, magenta y cian que se dibuja y rota, luz que late con el beat, "WAKO TV" (Montserrat 800, con brillo) y debajo "<NOMBRE DEL TEMA> · M O N T A G E". Sale con un estallido de brillo.
2. **Primera play:** arranca con zoom a 2x sobre la cámara y se abre hacia la play. La primera kill cae en el drop.
3. **Primera parte:** plays hasta la revelación.
4. **Revelación antes del drop principal** (`REVEAL = True` en el plan; **el negro con orbes de luz quedó dado de baja el 20/11/2026**: se sentía seco). La primera parte se funde a negro (1.4 s) y la mejor play del video (un ACE, un clutch) aparece **chica, oscura y casi sin color, como vista de lejos**; durante los 8 beats previos al drop se acerca e ilumina hasta llenar la pantalla **justo en el drop**, donde cae su primera kill (el título aparece recién ahí). El audio del juego entra a la par de la imagen.
   - **Siempre antes del momento más importante de la canción** (el drop más fuerte, el estribillo principal o la sección con más ritmo; el que se siente como "el drop", no necesariamente el segundo) y **siempre con una muy buena play**. `I_DROP2` es ese momento.
   - La play revelada necesita ~4 s de clip antes de su primera kill (los 8 beats de la revelación): elegí una que lo tenga. Su primera toma se justifica con `ctx={0: (4.2, 0.9)}`.
5. **Segunda parte:** las plays más fuertes, con la última en los contrabeats.
6. **Cierre:** la última play sigue hasta la reacción del streamer con un zoom suave (1.75x máximo) y un fundido. Después, sobre negro: "NOS VEMOS EN EL STREAM", tres puntos que aparecen de a uno y `twitch.tv/el_wako` debajo. La música se apaga hasta el negro total.

## 6. Efectos y transiciones
- **Zoom máximo 2x** en cualquier zoom sobre la cámara o la play: la fuente se pixela.
- **Corrección de color** fija del canal (curva en S, sombras frías y luces cálidas, saturación ×1.15, bloom y viñeta leves): ya está en `render.py`.
- **Transiciones entre plays:** `whip_lr`/`whip_rl`, `light` y `zoom`. Variá entre ellas (`BT` del plan). **Dentro de una misma play** usá versiones cortas (±0.075 s).
- **Transición "mega"** (una sola, en un hito de la canción como la entrada de una voz): punch-in con desenfoque radial, separación RGB, luz horizontal y destello solo en el centro. Lleva whoosh y un golpe grave.
- **Efectos de kill** que van rotando (`KILL_FX`): bloom, zoom con separación RGB, sacudida con desenfoque, destello breve, zoom radial y golpe de contraste. Todos sutiles, entre 0.11 y 0.2 s de decaimiento. **Nada que tape la play.** **Todos entran con una rampa de ~3 cuadros** y la sacudida es una oscilación suave, nunca ruido aleatorio por cuadro: un salto de zoom o de posición de un cuadro al otro se ve como un "tirón" del video (el usuario lo reportó como un error).
- **ACE:** golpe fuerte (destello, anillo, luz horizontal, sacudida) **solo en la primera y en la última kill**. Las del medio, un destello breve con un poco de brillo. Muchos pulsos seguidos marean. En mapas claros (Dust2 al sol) el golpe fuerte del ACE quemaba toda la pantalla: revisá el cuadro de la última kill; el enemigo tiene que verse.
- **"Flashing light"** (`flash=[i]`) para tiros especiales (a través del humo, flick, collateral, la kill que cierra una play): destello, bloom, luz horizontal normalizada y un anillo. Revisá en preview que no queden quemados.
- **Revisá cada efecto fuerte en preview sobre un mapa claro** (Dust2, Mirage al sol): los brillos, la luz horizontal y los destellos queman la imagen y hubo que bajarlos varias veces. Si la play no se lee en el cuadro del efecto, es demasiado.
- **Cámara lenta** solo con interpolación óptica (`build.py` la genera desde `SLOWMO_SRC`, con RIFE en la GPU si está instalado: ~10 s cada una). Va después de un tiro destacado (collateral, kill con cambio de arma) y dura hasta la transición siguiente, con desaturación leve y audio pasado por un filtro grave. Nunca para estirar tiempo, y no en finales de play comunes (en el "casi 5K" el usuario pidió sacarla). Como mucho 2 o 3 por video.

## 7. Texto
- **No poner letra de la canción ni narrar lo que pasa.**
- **Sin frases épicas ni palabras animadas** (las tipo "UNA USP-S / CINCO KILLS / CERO DUDAS"): el usuario las dio de baja. Ni sobre las plays ni en el interludio (`PHRASES` y `WORDS` quedan vacíos).
- **Títulos solo en las plays de más impacto** (ACE, 4K, CASI 5K, RUN BOOST, collateral, clutch): chicos, centrados abajo, con subtítulo (arma o mapa). Duran 1.5 s, aparecen y desaparecen con un fade y llevan una sombra suave.

## 8. Audio
### El juego bien presente, en el punto medio (pedido del usuario)
El usuario pidió subir las armas en tres videos seguidos y el 20/11/2026 volvió a decir que los tiros, los headshots y los efectos "siguen muy bajos, la música predomina demasiado". Medido en my_jealousy_v3 con la mezcla vieja: el juego quedaba **15.5 dB debajo de la música** y el tiro de cada kill, 19 dB abajo. Se probó una mezcla con el juego casi a la par de la música (−3.4 dB) y el usuario la sintió "un poco muy alta": pidió **un punto medio entre las dos**, que es la mezcla actual. Las canciones vienen masterizadas muy fuerte y el audio de Twitch no, así que una ganancia fija nunca alcanza. `audio.py` usa la **mezcla 2** por defecto:
- **El juego se nivela contra la música de cada video**: queda a −11.5 dB de ella en las plays antes del realce de los tiros (`GAME_VS_MUSIC`), y cada clip al mismo nivel que los demás (los clips grabados más bajos ya no quedan tapados).
- **Cada tiro y cada headshot saltan**: realce de transitorios ×2.35 (`GAME_EMPH`), un poco de presencia en 2-6 kHz (`GAME_PRESENCE` 0.25, donde viven el estallido y el "dink"), y en cada disparo la música se aparta un 52 % (`MUSIC_DUCK`) y libera en parte la banda de 1.2-6 kHz (`MUSIC_CARVE` 0.35) para que el tiro no compita con las guitarras o la voz.
- **La música queda un poco más baja debajo del gameplay** (0.85, `MUSIC_BED`) que en el logo, el interludio y el outro (0.92), donde manda sola.
- **Objetivo, medido en `audio_balance.txt`:** juego unos **−9.5 dB** respecto de la música en las plays (vieja −15.5; la que fue "muy alta" −3.4) y tiro de cada kill unos **−8 dB** (vieja −19; "muy alta" −2). Pico ≤ −1.3 dBFS ya codificado en AAC y unos −10 LUFS.
- **No cambies este balance sin que el usuario lo pida:** ni más bajo (fue el reclamo de cuatro videos) ni más alto (lo sintió excesivo). Si pide más o menos juego, movelo de a 2 dB desde el plan con `GAME_VS_MUSIC` (−9.5 más fuerte, −13.5 más suave). `AUDIO_MIX = 1` vuelve a la mezcla vieja (solo para comparar).
- Leé `audio_balance.txt` después de cada render: si el juego vs música se aleja más de 2 dB de −9.5, revisá por qué (clips muy bajos que topan el límite de nivelación ×6, una canción rara).

### Reacciones GRUPALES al cierre de una play
Cuando un clip trae una **reacción grupal** después de la jugada (el streamer y sus compañeros gritando a la vez después de un clutch, varios festejando, aliento), **se resalta**: la voz sube por encima de la música solo en ese momento, para que se sienta la emoción. No se corta ni la música ni el juego: la música baja un 45 % mientras dura el festejo y la voz separada del clip se suma encima. **La música no vuelve de golpe:** sigue baja 0.6 s después del grito (`REACT_HOLD`) y recién ahí sube en 0.5 s con una curva suave (`REACT_RELEASE`); el usuario la sentía volver demasiado rápido. Esa espera nunca pasa el corte del clip: si el festejo llega hasta el corte, la música empieza a subir ahí. El usuario lo aprobó a oído ("quedó espectacular").
- **Solo grupales** (pedido del 20/11/2026): un grito individual (una sola persona, aunque grite muy fuerte) **no se resalta**: suena como viene en el clip.
- **Detección:** `python engine/reactions.py projects/<nombre>` (después de `--shots`, paso 2.4). Separa voz y juego de cada clip con Demucs (`clip_stems/cN/`, se reusa) y busca tramos de voz claramente más fuertes que la charla normal del clip (+8 dB o más, ≥0.22 s, voz armónica: un tiro colado no cuenta). Después mide si hay **una segunda voz al mismo tiempo** (varias alturas por cuadro: otra voz con altura propia y continua, no un armónico ni la aspereza del grito de una sola persona). Grupal = segunda voz en ≥20 % del grito o sostenida ≥0.10 s. Calibrado en my_jealousy_v3: el festejo grupal de c30 da 0.42; los 11 gritos individuales, entre 0.00 y 0.07 (el usuario confirmó a oído que el de c16 era individual). Con una sola grupal de referencia el umbral es provisorio: si el usuario marca una que falló, recalibralo.
- **Solo en la culminación, nunca en medio de una play:** cuenta solo si arranca entre 0.3 s antes y 3.5 s después de la kill que **cierra** la play que se ve en el video (la última kill mostrada de ese clip).
- **La reacción vive dentro de su clip: nunca suena sobre otro.** Termina con un fundido en el corte de su tramo; si el festejo sigue después del corte, ese resto se pierde y nunca se arrastra a la play siguiente (el usuario lo marcó: un grito sobre otro clip rompe la consistencia del video). Para que se oiga entero hay que **alargar el video**, no el audio.
- **Alargar el tramo para que entre:** casi siempre llega 0.7-1.5 s después de la kill, y la cola normal (0.6-0.9 s) la corta. `check_kills.py` lista "Reacciones al cierre de las plays" con el fin de tramo sugerido. **Alargá el `src_end` del último tramo hasta ese fin** (corre el corte, así imagen y voz siguen juntas): es la excepción al techo de cola de §3 y `check_kills.py` la toma como justificada (hasta 0.9 s de festejo). Si alargar rompe la sincronía con la canción, dejala afuera.
- Si llega más de 1.8 s después de la kill, no se alarga la cola para buscarla (sería tiempo muerto); solo se resalta si ya entra (por ejemplo en el cierre con `face_out`).
- `audio_balance.txt` lista cada reacción resaltada (clip y minuto del video) y las grupales que quedaron afuera. Nombralas en la respuesta final para que el usuario las escuche: la detección no se puede oír desde acá. `REACTIONS = False` en el plan las apaga todas; `REACTIONS = {clip: False}`, una sola; `REACT_KINDS = ('grupal', 'individual')` vuelve a incluir las individuales (solo si el usuario lo pide).

### Lo demás
- Whoosh en cada whip, shimmer en las transiciones de luz y whoosh en el zoom de apertura y en el de cierre.
- Fundido de entrada de la música de 0.8 s y de salida durante el cierre. Pico ≤ −1.3 dBFS medido en el AAC final (`audio.py` lo corrige solo) y entre −10 y −12 LUFS integrados.

## 9. Pipeline (pasos y chequeos)
1. **`plan.py`:** copiado de `projects/my_jealousy_v3/plan.py`, cambiando solo los datos. **Leé `references/plan.md` antes de escribirlo.** Corré `python projects/<nombre>/plan.py` y revisá desfases, residuos y avisos `WARN`.
2. **Chequeo de kills** después de cada cambio del plan: `python engine/check_kills.py projects/<nombre>` limpio (mínimos, tiempo muerto, kills que faltan y **SINCRONÍA**: cada momento de `SYNC` con su kill exacta). Mirá también la lista "Reacciones al cierre de las plays" y alargá los tramos de las plays fuertes cuya reacción quedó afuera.
3. **Previews** antes del render completo: `python engine/build.py projects/<nombre> --preview t1,t2,...` (JPG en `projects/<nombre>/previews/`, miralos con la herramienta de lectura de imágenes). **Hoja mínima:** intro, transiciones, el cuadro de cada kill de drop o estribillo, cada corte de golpe seco, la última kill de cada ACE (sobre todo en mapas claros), una secuencia cuadro a cuadro alrededor de una kill (para ver que el efecto entra sin salto), la revelación (fundido, cuadro chico y oscuro, la mitad y el drop con su kill), cada momento de `SYNC`, el cierre con la reacción, el outro y **un cuadro por kill** de las plays con título (`check_kills.py --times` imprime la lista).
4. **Render:** repasá `references/errores.md` y corré `python engine/build.py projects/<nombre>` **en segundo plano** (la terminal corta a los 10 min). Por defecto todo el cuadro se procesa en la GPU (`--device auto`; `--device cpu` fuerza el procesador, mismo resultado): ~1 min un edit de 2:30 en la RX 7900 XT. Divide en pedazos de 2 s que toman procesos fijos en paralelo (los más pesados primero), reusa los pedazos y el audio que no cambiaron y une los pedazos sin recodificar. Si el usuario quiere ver el edit entero antes del final, primero `--draft` (borrador 960x540 a 30 fps en `projects/<nombre>/borrador.mp4`, la mitad de tiempo). En las correcciones solo se renderiza lo que cambió. Si falla por memoria, bajá `--workers`.
5. Nunca uses `timeout` en el render ni en ffmpeg: un `timeout` corta el video sin avisar (pasó una vez: salió de 2:25 en vez de 2:50).
6. **Chequeo final:** `build.py` corre solo `check_render.py` al terminar y lo guarda en `projects/<nombre>/check_render.txt` (cuadros repetidos, tirones sobre las kills, 60 fps exactos, duración contra `TOTAL`, LUFS y pico). Leelo siempre, junto con `audio_balance.txt` (juego vs música cerca de −9.5 dB, tiros, reacciones resaltadas; §8). Si el pico pasa de -1 dBFS, bajá solo el audio sin re-renderizar (`ffmpeg -i x.mp4 -map 0:v -map 0:a -c:v copy -af volume=-1.2dB -c:a aac -b:a 320k ...`). Mirá además una hoja final de fotogramas.
- Los rectángulos blancos u overlays del stream que aparecen en algunos clips vienen de los originales: no son del motor.

## 10. Revisiones
- Pedí o confirmá lo que no se puede detectar de forma confiable (armas dudosas, golpes de voz aislados si hay dudas). Verificá el arma de cada título (una vez se puso "DEAGLE" en una Glock).
- **El usuario marca timestamps del video:** `python engine/locate.py projects/<nombre> 1:23,2:05` dice para cada uno el tramo, el clip (y su archivo original), el tiempo en el clip, la kill y la transición más cercanas y el tiempo de canción, y arma tiras de cuadros del clip original y del video renderizado en `projects/<nombre>/insp/`. Miralas antes de cambiar nada.
- **No toques lo que el usuario llamó "core"** (secciones ya sincronizadas): anclalo por tiempo de canción (`kill_at`, `kill_at_seg`, `start_at`).
- Los cambios de tiempo se compensan con los leads de las plays vecinas (más contexto es preferible a cortar), no moviendo las anclas.
- Cuando el usuario marca una kill que no se ve, revisá también las otras plays del mismo video con el chequeo de §3: casi siempre hay más casos iguales.
- Re-render en el mismo proyecto: la caché hace que solo se rendericen los pedazos que cambiaron. Para un cambio grande o de estructura, nueva carpeta `_v2`, `_v3`.
- Si el usuario corrige algo que ya está en `references/errores.md`, es un error repetido: decíselo y revisá por qué la regla no alcanzó.

## 11. Respuesta final
Un resumen corto: duración y cantidad de plays, cómo se usó la canción, títulos puestos, qué se dejó afuera y por qué, y lo que el usuario debería revisar (por ejemplo el audio, que no se puede escuchar desde acá: el balance de `audio_balance.txt` y el minuto de cada reacción resaltada). Sin repetir paso por paso. Al final, en una línea, ofrecé el short vertical (`cs2-short`) y el paquete para YouTube (`yt-publish`).
