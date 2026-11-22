# edit.json: un edit como datos

`projects/<nombre>/edit.json` dice **qué** entra en el edit (clips, kills, dónde corta cada toma, títulos). **Cuándo**
cae cada cosa lo calcula `engine/planner.py`: cada kill clave en un golpe de la canción, la intro, la revelación antes
del drop, el cierre y las transiciones.

```
python engine/planner.py projects/<nombre>            diagnóstico: tramos, desfase de cada kill, avisos, TOTAL
python engine/planner.py projects/<nombre> --json     escribe timeline.json (lo que consume el render)
python engine/check_kills.py projects/<nombre>        que cada kill se vea y no haya tiempo muerto
python engine/migrate.py projects/<nombre> --write    pasa un plan.py viejo a edit.json (comprueba que dé lo mismo)
```

Los proyectos anteriores con `plan.py` siguen funcionando igual; si están los dos archivos, manda `edit.json`.

## Formato

```json
{
 "version": 1,
 "song": {"title": "MY JEALOUSY", "start": 8.05, "drop1": 16.05, "drop2": 112.06, "sync": [16.05, 32.05, 64.06, 112.06]},
 "open": {"clip": 12, "end": 17.55},
 "close": {"clip": 30, "len": 6.0},
 "ace_clip": 4,
 "cam": {"12": [0, 0, 461, 259], "30": [24, 18, 487, 288]},
 "reveal": true,
 "act1": [
  {"clip": 16, "hard": [0], "segs": [{"kill": 0, "end": 6.85, "lead": 1.6, "kills": [0, 1]}]},
  {"clip": 29, "cap": ["ACE", "USP-S"], "kill_at": 64.06, "segs": [{"kill": 3, "end": 19.1, "lead": 2.6, "kills": [0, 1, 2, 3, 4]}]}
 ],
 "act2": [
  {"clip": 3, "cap": ["CLUTCH 1v4", "MIRAGE"], "flash": [3], "segs": [{"kill": 0, "end": 2.15, "lead": 1.0, "kills": [0]}]}
 ]
}
```

Los tiempos de `song` son segundos **de la canción**; los de cada tramo (`end`), segundos **del clip**. Los números de
clip son los de `clips/cN.mp4`; los de kill, la posición en `shots.json` (0 = primera kill del clip).

### Nivel superior

| Clave | Qué es |
|---|---|
| `song.start` | Segundo de la canción donde arranca el video (el logo dura hasta 4 golpes antes de `drop1`) |
| `song.drop1` | Primer drop: ahí cae la primera kill de la apertura |
| `song.drop2` | Drop principal: ahí cae la primera kill de `act2`; `act1` termina 8 golpes antes |
| `song.sync` | Momentos con buen ritmo que tienen que llevar una kill exacta (lo controla `check_kills.py`) |
| `open` | Clip de apertura (sale del logo con zoom desde la cámara) y hasta qué segundo del clip se muestra |
| `close` | Clip de cierre (termina con zoom a la cámara) y cuántos segundos dura esa cola |
| `ace_clip` | El clip cuyas kills llevan el efecto especial de ACE (un color por kill) |
| `cam` | Rectángulo de la cámara del streamer en cada clip que la usa: `[x0, y0, x1, y1]` en 1920x1080 |
| `reveal` | `true`: la primera play de `act2` se acerca y se ilumina hasta el drop. `false`: negro con luces |
| `transitions`, `kill_fx` | Rotaciones propias de este edit (si faltan, las del preset) |
| `preset`, `style` | Otro preset o valores sueltos solo para este proyecto: ver `docs/presets.md` |
| `audio` | Ajustes de mezcla de este edit: `GAME_GAIN`, `MUSIC_DUCK`, `REACTIONS`, ... |

### Una play

| Clave | Qué es |
|---|---|
| `clip` | Número de clip |
| `segs` | Tomas de la play, en orden. Cada una: `kill` (la kill que cae en el golpe), `end` (segundo del clip donde corta), `lead` (segundos mínimos antes de esa kill) y `kills` (todas las que se ven en la toma) |
| `cap` | Título y subtítulo: `["ACE", "AK-47"]` |
| `kill_at` | Segundo de la canción donde tiene que caer la kill clave de la primera toma (un drop, un golpe fuerte) |
| `kill_at_seg` | Lo mismo para otra toma: `{"1": 130.54}` |
| `hard` | Kills poco visibles (enemigo lejos, humo): piden más tiempo antes y después |
| `flash` | Kills con el destello especial |
| `tin` | Transición de entrada forzada (`"mega"`, `"light"`, ...) |
| `ctx` | Tiempo muerto justificado: `{"0": [2.4, 1.0]}` = hasta 2.4 s antes y 1.0 s después de la kill 0 |
| `beats` | Qué golpes del compás acepta cada toma: `null` (cualquiera), `[0]` (el primero), `[1, 3]` (contratiempos) |
| `slowmo` | Cámara lenta al final: `[desde, hasta, duración]` |

### Ráfaga

Una kill de un clip distinto en cada golpe (sílabas repetidas, golpes secos):

```json
{"burst": [[9, 1], [20, 0], [25, 0]], "at": [120.99, 121.34, 121.75], "pre": 0.14}
```

`burst` son pares `[clip, kill]` y `at` el segundo de la canción de cada una.
