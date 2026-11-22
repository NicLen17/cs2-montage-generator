# edit.json — formato, anclas y cómo cuadrarlo

**Leé este archivo entero antes de escribir o modificar el plan de un edit.** Las reglas de edición (qué mostrar, mínimos, drops) están en `SKILL.md`; acá está cómo se expresan en el plan.

Desde el 21/11/2026 el plan es **`projects/<nombre>/edit.json`** (solo datos); la lógica que antes se copiaba en cada `plan.py` vive en `engine/planner.py`. Los proyectos anteriores con `plan.py` siguen andando igual y se corrigen en su `plan.py` (mismos nombres de campos, en Python); si hay que hacerles un cambio grande, `python engine/migrate.py projects/<nombre> --write` los pasa a `edit.json` comprobando que den el mismo edit. Referencia completa de campos: `docs/edit-json.md`.

## Punto de partida
- **Lo más rápido:** `python engine/auto.py projects/<nombre> --plan-only` arma un `edit.json` válido con las plays elegidas por puntaje (apertura en el primer drop, la mejor en el drop principal, cierre con cola para la cámara). Es un borrador: después se aplican a mano las reglas de `SKILL.md` (kills dudosas revisadas, drops confirmados a oído, `kill_at` en cada momento de `song.sync`, títulos con arma o mapa, `hard`, `ctx`, orden por intensidad).
- **O a mano**, copiando `projects/my_jealousy_v3/edit.json` y cambiando los datos. Ese edit trae `"reveal": false` y dos ráfagas que fueron pedidos especiales de "My Jealousy" (una kill por sílaba): en un edit nuevo poné `"reveal": true` y no copies las ráfagas salvo que el usuario las pida.

## Nivel superior
```json
{"version": 1,
 "song": {"title": "PAPARAZZI", "start": 27.25, "drop1": 35.82, "drop2": 96.68, "sync": [35.80, 69.25, 82.99, 96.68], "frantic": [[96.7, 118.5]]},
 "open": {"clip": 8, "end": 4.6}, "close": {"clip": 26, "len": 7.0}, "outro_len": 5.0, "ace_clip": 21,
 "cam": {"8": [0, 0, 461, 259], "26": [17, 256, 440, 496]},
 "reveal": true,
 "act1": [...], "act2": [...],
 "audio": {"GAME_GAIN": 0.54}}
```
- `song.start`: segundo de la canción donde arranca el video (antes `SONG_A0`): si la intro no tiene batería, salteá parte para que el logo dure 6 a 8 s, empezando en un compás. `song.drop1` (antes `IDX_DROP`): primer drop, ahí cae la primera kill de la apertura. `song.drop2` (antes `I_DROP2`): el momento más importante de la canción, el de la revelación. `analyze_song.py` sugiere los tres en `song.json`; **confirmalos con la tira beat por beat**.
- `song.sync` (antes `SYNC`): los momentos con buen ritmo elegidos y confirmados; `check_kills.py` exige una kill exacta en cada uno. **Ponelo siempre** en un edit hecho con este skill: si falta, el planificador toma solo los que el análisis eligió por su cuenta (aciertan el beat 4 de cada 5 veces) y `check_kills.py` los trata como avisos.
- `song.frantic` (antes `FRANTIC`): tramos frenéticos en tiempo de canción (los techos de tiempo muerto se multiplican por 0.75).
- `open` (antes `OPEN_CLIP` y `OPEN_END`), `close` (antes `END_CLIP` y `END_LEN`), `outro_len`, `ace_clip` (uno solo: el que recibe los golpes fuertes de ACE; elegí el del drop principal).
- `cam` (antes `CAM`): rectángulo de la cámara, solo para el clip de apertura y el de cierre, medido en cada clip.
- `transitions` (antes `BT`) y `kill_fx` (antes `KILL_FX`): rotaciones propias del edit; si faltan, las del preset. Con `kill_bright.json` en el proyecto, el bloom y el destello se cambian solos en los cuadros claros.
- `audio`: los mismos nombres de siempre, solo si el usuario pide otro balance (abajo).
- `style` / `preset`: estilo solo para este proyecto (`docs/presets.md`). El nombre del canal, el link y el logo salen del preset, no del plan.

## Formato de una play
```json
{"clip": 9, "cap": ["4K", "MIRAGE"], "kill_at": 69.252, "hard": [1, 2, 3], "tin": "mega",
 "segs": [{"kill": 0, "end": 3.95, "lead": 1.2, "kills": [0]}, {"kill": 1, "end": 22.05, "lead": 1.2, "kills": [1, 2]}],
 "flash": [3], "tech": {"2": 20.4}, "ctx": {"0": [2.4, 1.0]}, "kill_at_seg": {"1": 82.99}, "keep_cut": [1],
 "beats": [null, [1, 3]], "slowmo": [22.05, 22.6, 1.8], "start_at": 64.06, "smax": {"0": 1.2}}
```
- `segs`: cada tramo es la kill clave (`kill`), dónde corta en el clip (`end`), el lead pedido (`lead`) y las kills que muestra (`kills`). Los números de kill son la posición en `shots.json` (0 = la primera del clip).
  **Un corte entre dos tramos de la misma play tiene que saltear más de 1 s del clip** (inicio del tramo nuevo − `end` del anterior); si saltea menos, uní los dos tramos en uno con todas sus kills (SKILL.md §3). Unirlos alarga la play lo que salteaba el corte: compensalo antes de la próxima ancla (colas que sobran, o un beat menos de lead donde el redondeo sumó de más). `keep_cut: [i]` justifica un corte corto que sí hace falta (una sincronía).
- `cap`: título y subtítulo. `tin`: transición de entrada (`"mega"`, `"light"`...).
- `flash: [i]`: "flashing light" en esas kills. `hard: [i]`: poco visible. `tech: {"i": inicio_del_movimiento}`. `ctx: {"i": [pre_max, post_max]}`: tiempo muerto justificado. Las claves de `tech`, `ctx`, `kill_at_seg` y `smax` van entre comillas (es JSON).
- `beats`: en qué tiempos del compás puede caer la kill clave de cada tramo: `null` cualquiera, `[0]` el primero, `[1, 3]` contrabeats.

## Cómo calcula los tiempos
- `planner.py`: `B = primer golpe ≥ cursor + lead`, inicio del tramo `= disparo − (B − cursor)`. La kill clave cae **exactamente** en un golpe de la canción; el lead real puede salir hasta 0.5 s más largo que el pedido (pedí leads en el piso: 1.2 / 0.8).
- `python engine/planner.py projects/<nombre>` imprime los tramos, el desfase de cada kill a su golpe, los residuos de las anclas (`RESID`), los avisos (`AVISO tight lead` cuando un lead queda por debajo de 0.35 s) y `TOTAL`. Un `edit.json` mal armado da un error que dice qué play y qué campo.

## Anclas (para revisiones y drops)
- `kill_at` / `kill_at_seg` fijan una kill a un tiempo exacto de la canción (sincronía que el usuario marcó como intocable, downbeats de drops y estribillos). La toma arranca en el `cursor`, así que el lead es `kill_at − cursor`. Si es mayor que el tiempo del disparo en el clip, el inicio se recorta a 0 y la kill sale fuera del drop; si es muy chico, la kill no tiene contexto. Acomodá las plays de antes hasta que el lead quede entre ~1.2 y 2 s.
- `start_at` fija dónde empieza una play (transición mega) y absorbe la diferencia en la cola del tramo anterior. Un residuo negativo recorta el tramo anterior y puede comerse la última kill.
- **Revelación** (`"reveal": true`, el estándar desde el 20/11/2026): sin segmento de negro; el primer acto termina 8 golpes antes de `song.drop2` (fundido `black_in`) y la primera play de `act2` arranca ahí, achicada y oscura, con su primera kill en el drop. El título se mueve al drop solo. Dale a esa play `"ctx": {"0": [4.2, 0.9]}`. `"reveal": false` es el negro con luces viejo: no lo uses en edits nuevos.

## Cuadrar la primera parte
- `lead_plus` (nivel superior) suma lead a cada play del primer acto. Ajustalo junto con la cantidad de plays hasta que `RESID['interlude']` quede entre 0 y 1 s y el residuo de `start_at` (mega) sea chico y positivo.
- Si la kill clave está a menos de ~1 s del inicio del clip, el lead no alcanza y el inicio se recorta a 0 (la kill sale fuera del beat): tomá como clave la kill siguiente e incluí la primera en ese tramo.

## Casos especiales
- **Cámara lenta:** `"slowmo": [a, b, dur]` empieza exactamente donde termina el tramo (`end` = inicio de la cámara lenta); si no, repite cuadros. `"slowmo_src": {"clip": [archivo, t0]}` en el nivel superior y `build.py` la genera.
- **Golpes secos después de la revelación:** una kill de la misma play en cada golpe, sin mostrar el viaje entre kills:
  `{"burst": [[clip, 0], [clip, 1], ...], "at": [golpes en tiempo de canción], "pre": 0.25, "sync": 0.0, "fx": false, "tail": 0.9, "cap": [...]}`.
- Sin frases ni palabras animadas: `words` no se usa (el usuario las dio de baja).
- **Reacciones (solo grupales):** para que se oiga el festejo del final de una play, poné como `end` del último tramo el "fin de tramo" que sugiere `check_kills.py` (o `reactions.py`). No hace falta `ctx`: la cola queda justificada sola. Alargar ese tramo corre todo lo que viene después: compensalo con los leads de las plays siguientes (o `lead_plus`) para no mover las anclas. `"audio": {"REACTIONS": false}` (todas) o `{"REACTIONS": {"12": false}}` las apaga. Nunca se alarga solo el audio: la voz termina en el corte de su tramo.
- **Audio (solo si el usuario pide otro balance)**, dentro de `"audio"`: `GAME_VS_MUSIC` (−11.5 dB; de a 2 dB), `GAME_GAIN`, `GAME_EMPH` (2.35), `GAME_PRESENCE` (0.25), `MUSIC_DUCK` (0.52), `MUSIC_CARVE` (0.35), `MUSIC_BED` (0.85), `REACT_GAIN` (1.3), `REACT_DUCK` (0.45), `REACT_HOLD` (0.6 s), `REACT_RELEASE` (0.5 s), `REACT_KINDS` (`["grupal"]`), `AUDIO_MIX: 1` (mezcla vieja). Ver SKILL.md §8.

## Pedidos especiales (solo si el usuario los pide para ese video)
No son parte del estilo: fueron efectos atados a una canción puntual. El motor los sigue soportando:
- **Cortes dobles en un golpe vocal** ("bang bang"): `"bang": [tA, tB, kA, kB, fin, [extras]]` en la play: kill A en el primer golpe, corte seco, kill B en el segundo. `analyze_song.py` deja los pares de golpes vocales candidatos en `vocal_hits.json`.
- **Una kill por sílaba repetida** ("jealousy, jealousy"): `{"burst": [[clip, kill], ...], "at": [sílabas], "pre": 0.14, "fx": "burst", "tail": 0.95}`, con kills de clips distintos y efecto casi nulo. Detección de sílabas: `projects/my_jealousy_v2/vocal_reps.py` (`engine/words.py` no detecta sílabas recortadas).

## Versiones
Para cada video grande nuevo hacé una carpeta de versión (`<nombre>_v2`, `_v3`): la anterior queda intacta para comparar.
