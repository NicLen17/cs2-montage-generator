# plan.py — formato, anclas y cómo cuadrarlo

**Leé este archivo entero antes de escribir o modificar un `plan.py`.** Las reglas de edición (qué mostrar, mínimos, drops) están en `SKILL.md`; acá está cómo se expresan en el plan.

## Punto de partida
Copiá **`projects/my_jealousy_v3/plan.py`** (el plan más completo: apertura con varias kills, `kill_at` en drops, ráfagas `burst`, golpes secos) y cambiá solo los datos: canción (`SONG_TITLE`, `SONG_A0`, `IDX_DROP`, `I_DROP2`, `MEGA_AT`), `ACT1`/`ACT2`, `CAM`, `OPEN_CLIP`/`END_CLIP`/`ACE_CLIP`, ráfagas y títulos.

## Formato de una play
```python
dict(clip, segs=[(kill_idx, src_end, lead, [kills]), ...], cap, tin, flash, hard, tech, slowmo=(a, b, dur),
     bang=(tA, tB, kA, kB, fin, [extras]), ctx={i: (pre_max, post_max)}, kill_at=song_t, kill_at_seg={i: song_t},
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
- **Ráfagas:** `dict(burst=[(clip, kill), ...], at=[tiempos de canción], pre=0.14, sync=VOC, fx='burst', tail=0.95, cap=None)`. `fx=False` usa los efectos normales (o los de ACE si el clip es `ACE_CLIP`); `sync=0.0` para golpes secos de la música en vez de sílabas (`pre=0.25`). La primera entrada es la kill del clip que viene antes.
- **Bang bang:** `bang=(tA, tB, kA, kB, fin, [extras])`: kill A en el primer golpe, corte seco, kill B en el segundo.
- `CAM = {clip: (x0, y0, x1, y1)}` solo para `OPEN_CLIP` y `END_CLIP`, medida en cada clip. `ACE_CLIP` es uno solo (el que recibe los golpes fuertes de ACE): elegí el del segundo drop.
- `FRANTIC = [(song_a, song_b), ...]`: tramos frenéticos (los techos de tiempo muerto se multiplican por 0.75).
- `PHRASES` y `WORDS` quedan vacíos (el usuario dio de baja las frases).

## Versiones
Para cada video grande nuevo hacé una carpeta de versión (`<nombre>_v2`, `_v3`): la anterior queda intacta para comparar.
