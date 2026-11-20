# plan.py — formato, anclas y cómo cuadrarlo

**Leé este archivo entero antes de escribir o modificar un `plan.py`.** Las reglas de edición (qué mostrar, mínimos, drops) están en `SKILL.md`; acá está cómo se expresan en el plan.

## Punto de partida
Copiá **`projects/my_jealousy_v3/plan.py`** (el plan más completo: apertura con varias kills, `kill_at` en drops, golpes secos) y cambiá solo los datos: canción (`SONG_TITLE`, `SONG_A0`, `IDX_DROP`, `I_DROP2`, `MEGA_AT`), `ACT1`/`ACT2`, `CAM`, `OPEN_CLIP`/`END_CLIP`/`ACE_CLIP` y títulos. **Ojo:** ese plan trae dos efectos que fueron pedidos especiales de "My Jealousy" (las ráfagas `B1`/`B2` en las sílabas de "jea-lou-sy" y su `VOC`): no los copies a un plan nuevo salvo que el usuario los pida.

## Formato de una play
```python
dict(clip, segs=[(kill_idx, src_end, lead, [kills]), ...], cap, tin, flash, hard, tech, slowmo=(a, b, dur),
     ctx={i: (pre_max, post_max)}, kill_at=song_t, kill_at_seg={i: song_t},
     start_at=song_t, smax={i: max_src_start}, beats=[{0}, {1, 3}, ...])
```
- `segs`: cada tramo es `(kill clave, fin en el clip, lead pedido, kills que muestra)`.
- `cap=('ACE', 'USP-S')`: título y subtítulo. `tin='mega'`: transición de entrada.
- `flash=[i]`: "flashing light" en esas kills. `hard=[i]`: poco visible. `tech={i: inicio_del_movimiento}`. `ctx={i: (pre_max, post_max)}`: tiempo muerto justificado.
- `beats=[ANY, BACK, ...]`: en qué tiempos del compás puede caer la kill clave de cada tramo (`DOWN={0}`, `BACK={1,3}` contrabeats).

## Cómo calcula los tiempos
- `schedule()`: `B = primer TGT ≥ cursor + lead`, `s0 = shot − (B − cursor)`. La kill clave cae **exactamente** en un `TGT`; el lead real puede salir hasta 0.5 s más largo que el pedido (pedí leads en el piso: 1.2 / 0.8).
- Imprime el desfase de cada kill a su hit, los residuos de las anclas (`RESID`) y avisos `WARN tight lead` cuando un lead queda por debajo de 0.35 s.

## Anclas (para revisiones y drops)
- `kill_at` / `kill_at_seg` fijan una kill a un tiempo exacto de la canción (sincronía que el usuario marcó como intocable, downbeats de drops y estribillos). La toma arranca en el `cursor`, así que el lead es `kill_at − cursor`. Si es mayor que el tiempo del disparo en el clip, `s0` se recorta a 0 y la kill sale fuera del drop; si es muy chico, la kill no tiene contexto. Acomodá las plays de antes hasta que el lead quede entre ~1.2 y 2 s.
- `start_at` fija dónde empieza una play (transición mega) y absorbe la diferencia en la cola del tramo anterior. Un residuo negativo recorta el tramo anterior y puede comerse la última kill.
- El interludio queda anclado al beat −8 antes del segundo drop.

## Cuadrar la primera parte
- `LEAD_PLUS` suma lead a cada play del primer acto. Ajustalo junto con la cantidad de plays hasta que `RESID['interlude']` quede entre 0 y 1 s y el residuo de `start_at` (mega) sea chico y positivo.
- Si la kill clave está a menos de ~1 s del inicio del clip, el lead no alcanza y `s0` se recorta a 0 (la kill sale fuera del beat): tomá como clave la kill siguiente e incluí la primera en ese tramo.

## Casos especiales
- **Cámara lenta:** `slowmo=(a, b, dur)` empieza exactamente donde termina el tramo (`src_end` = inicio de la cámara lenta); si no, repite cuadros. `SLOWMO_SRC = {clip: (archivo, t0)}` y `build.py` la genera.
- **Golpes secos después del interludio:** una kill de la misma play en cada golpe, sin mostrar el viaje entre kills:
  `dict(burst=[(clip, 0), (clip, 1), ...], at=[golpes en tiempo de canción], pre=0.25, sync=0.0, fx=False, tail=0.9, cap=(...))`.
- `CAM = {clip: (x0, y0, x1, y1)}` solo para `OPEN_CLIP` y `END_CLIP`, medida en cada clip. `ACE_CLIP` es uno solo (el que recibe los golpes fuertes de ACE): elegí el del segundo drop.
- `FRANTIC = [(song_a, song_b), ...]`: tramos frenéticos (los techos de tiempo muerto se multiplican por 0.75).
- `PHRASES` y `WORDS` quedan vacíos (el usuario dio de baja las frases).
- **Reacciones (solo grupales):** para que se oiga el festejo del final de una play, poné como `src_end` del último tramo el "fin de tramo" que sugiere `check_kills.py` (o `reactions.py`). No hace falta `ctx`: la cola queda justificada sola. Alargar ese tramo corre todo lo que viene después: compensalo con los leads de las plays siguientes (o `LEAD_PLUS`) para no mover las anclas. `REACTIONS = False` (todas) o `REACTIONS = {clip: False}` las apaga. Nunca se alarga solo el audio: la voz termina en el corte de su tramo.
- **Audio (solo si el usuario pide otro balance):** `GAME_VS_MUSIC` (−11.5 dB; de a 2 dB), `GAME_EMPH` (2.35), `GAME_PRESENCE` (0.25), `MUSIC_DUCK` (0.52), `MUSIC_CARVE` (0.35), `MUSIC_BED` (0.85), `REACT_GAIN` (1.3), `REACT_DUCK` (0.45), `REACT_HOLD` (0.6 s), `REACT_RELEASE` (0.5 s), `REACT_KINDS` (`('grupal',)`), `AUDIO_MIX = 1` (mezcla vieja). Ver SKILL.md §8.

## Pedidos especiales (solo si el usuario los pide para ese video)
No son parte del estilo: fueron efectos atados a una canción puntual. El motor los sigue soportando:
- **Cortes dobles en un golpe vocal** ("bang bang"): `bang=(tA, tB, kA, kB, fin, [extras])` en la play: kill A en el primer golpe, corte seco, kill B en el segundo. `analyze_song.py` lista pares de golpes vocales candidatos.
- **Una kill por sílaba repetida** ("jealousy, jealousy"): `dict(burst=[(clip, kill), ...], at=[sílabas], pre=0.14, sync=VOC, fx='burst', tail=0.95)`, con kills de clips distintos y efecto casi nulo (`fx='burst'`). Detección de sílabas: `projects/my_jealousy_v2/vocal_reps.py`.

## Versiones
Para cada video grande nuevo hacé una carpeta de versión (`<nombre>_v2`, `_v3`): la anterior queda intacta para comparar.
