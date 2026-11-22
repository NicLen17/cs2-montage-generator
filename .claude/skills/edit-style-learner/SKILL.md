---
name: "edit-style-learner"
description: "Analiza un edit de referencia DESCARGADO (archivo de video adjunto, en entrada/ o en una carpeta) y extrae su estilo (ritmo de cortes, sincronía, transiciones, efectos, color, texto, audio) para recrearlo con los clips del usuario en esta PC. Usala cuando el usuario adjunte un edit y diga 'hacé uno así', 'aprendé este estilo', 'copiá esta edición'. Si solo pasa un link, pedile el archivo descargado. Usala en lugar de anthropic-skills:edit-style-learner."
---

# Aprender el estilo de un edit y recrearlo

Usá este skill cuando el usuario adjunta un edit que le gustó y pide "aprendé este estilo" o "hacé uno así con mis clips". El resultado tiene dos partes: un **perfil de estilo** escrito y medido, y después el **montaje** con los clips del usuario siguiendo ese perfil. Para todo lo que el perfil no defina (detección de kills, visibilidad de cada kill, render, entrega), seguí `cs2-edit` del proyecto.

Corre **en esta PC**, dentro del repo del proyecto. Todo lo de la referencia va en `projects/<nombre>/ref/` (el mismo proyecto del montaje nuevo). El análisis usa Python local (`numpy`, `opencv`, `librosa`, ya instalados) y ffmpeg.

## 1. Conseguir la referencia (siempre un archivo)
- **La referencia tiene que ser un video descargado:** adjunto en el chat, en `entrada/` o en una carpeta que nombre el usuario. Copialo a `projects/<nombre>/ref/ref.mp4` (nunca muevas el original).
- **Si el usuario pasa solo un link** (YouTube, TikTok, Twitch): no lo analices desde el navegador (la imagen de esos reproductores no se puede leer cuadro por cuadro y se pierde el audio). Pedile que lo descargue y lo deje en `entrada/`, en una sola línea, y esperá el archivo.
- Verificá con `ffprobe` que tenga video y audio; anotá resolución, fps y duración. Si no tiene audio, avisá: la sincronía se estima solo con la imagen.
- Si el edit es largo, analizá un tramo representativo de 30 a 60 s (el que tenga un drop) y avisá cuál.

## 2. Medir
Guardá todo en `ref/analysis/`. Los comandos largos (flujo óptico sobre todo el video) van en segundo plano.
1. **Cortes:** diferencia de histograma HSV entre cuadros consecutivos; un salto grande es un corte. Reportá la duración de cada plano (promedio, mediana, mín, máx) y si se acorta hacia el clímax.
2. **Sincronía con la música:** beats y onsets del audio de la referencia (`librosa`, igual que `engine/analyze_song.py`). Medí qué porcentaje de cortes y de kills cae a ±40 ms de un beat, en qué tiempo del compás (bombo, contrabeat, palma) y si sigue golpes vocales.
3. **Transiciones:** para cada corte, mirá los 10 cuadros alrededor y clasificá: corte seco, whip (desenfoque direccional y desplazamiento), zoom (escala con desenfoque radial), destello blanco o de color, fundido a negro, luz o light leak, glitch o separación RGB, máscara o barrido, giro. Anotá duración y frecuencia de cada tipo.
4. **Efectos en las kills:** alrededor de cada kill, medí picos de brillo medio (destellos), cambio de escala con flujo óptico (`cv2.calcOpticalFlowFarneback`: zoom punch), desplazamiento global oscilante (shake), separación entre canales R y B (aberración cromática), desenfoque (varianza del Laplaciano), saturación o contraste momentáneos. Anotá intensidad y cuánto duran.
5. **Velocidad:** compará el movimiento por cuadro con el de un clip normal para detectar cámara lenta, aceleraciones, rampas, congelados o reversa.
6. **Color:** histogramas por canal y curva de tonos promedio (sombras, medios, luces), saturación media, temperatura (relación R/B en sombras y en luces), viñeta, bloom, grano y nitidez. Traducilo a parámetros concretos: puntos de la curva, saturación, tinte de sombras y luces.
7. **Encuadre y texto:** zooms o reencuadres, barras de cine, formato vertical. Texto: cuándo aparece, dónde, tamaño, tipografía (geométrica, serif, script, mono), animación y qué dice (títulos de play, letra, nada). Gráficos: logos, intro y outro.
8. **Audio:** relación entre música y juego, si la música baja en los tiros, SFX en transiciones (whoosh, impactos, risers), cortes de audio y fundidos.
9. **Estructura:** intro, construcción, pausa o break, clímax, cierre. Dónde pone las mejores plays y cómo termina.

## 3. Perfil de estilo
Escribí `ref/style.md` (para el usuario) y `ref/style.json` (parámetros para el motor):
- Una frase que resuma el estilo (por ejemplo "cortes cada 0.8 s, todo en el bombo, glitch RGB en cada kill, color frío desaturado, sin texto").
- Cada aspecto de §2 con su medición y la regla que se deduce ("85 % de las kills en el bombo → kill clave siempre en un golpe").
- 2 o 3 hojas con cuadros de ejemplo de la referencia (transición típica, efecto de kill, color) en `ref/analysis/`.
- **Diferencias con `cs2-edit`:** qué cambia respecto del estilo propio (por ejemplo, si la referencia acelera el gameplay o usa letra en pantalla) y una pregunta corta al usuario sobre las que choquen con sus reglas fijas. La letra de canciones no se pone nunca, aunque la referencia lo haga: proponele una alternativa.
Mostrale el resumen al usuario antes de editar si el estilo es muy distinto al propio; si es parecido, seguí y contale después.

### Formato de `style.json`
Usá estas claves. `plan` son variables que `plan.py` ya entiende y se copian tal cual; `motor_nuevo` son cosas que el motor **todavía no lee** y requieren el paso de §4.
```json
{
  "resumen": "cortes cada 0.9 s en el bombo, whip y zoom alternados, destello corto en cada kill, color frío",
  "medido": {
    "plano_mediana_s": 0.9, "plano_min_s": 0.35, "plano_max_s": 2.4,
    "cortes_en_beat_pct": 82, "kills_en_beat_pct": 90, "tiempo_del_compas": "bombo",
    "transiciones_pct": {"whip_lr": 40, "zoom": 30, "cut": 20, "light": 10},
    "efectos_kill_pct": {"flash": 50, "chroma_zoom": 30, "shake_blur": 20},
    "camara_lenta_por_minuto": 0.5, "texto": "títulos chicos abajo", "estructura": "intro 6 s, break a los 70 s"
  },
  "plan": {
    "BT": ["whip_lr", "zoom", "whip_rl", "zoom", "light"],
    "KILL_FX": ["flash", "chroma_zoom", "flash", "shake_blur"],
    "LEAD_PLUS": 0.0,
    "FRANTIC": [[64.0, 80.0]],
    "END_LEN": 6.0,
    "OUTRO_LEN": 4.4,
    "leads": {"primer_tramo": 1.2, "tramos_siguientes": 0.5, "cola": 0.6}
  },
  "motor_nuevo": {
    "color": {"curva": [[0, 0], [64, 52], [128, 128], [192, 205], [255, 250]], "saturacion": 0.95, "tinte_sombras": [0, 8, 20], "tinte_luces": [10, 5, 0]},
    "efectos": ["glitch_rgb_bloques"],
    "transiciones": ["giro_90"]
  },
  "choques_con_cs2_edit": ["la referencia acelera el gameplay x1.5 → no se hace (regla fija), se compensa con cortes más cortos"]
}
```
- Valores válidos: transiciones `whip_lr`, `whip_rl`, `light`, `zoom` (`mega` se pone por play con `tin='mega'`); efectos de kill `bloom`, `chroma_zoom`, `shake_blur`, `flash`, `radial_zoom`, `pop`. Si la referencia usa algo que no está en estas listas, va en `motor_nuevo`.
- `leads` se traduce a los `lead` de cada tramo del plan, **sin bajar nunca de los mínimos de visibilidad de `cs2-edit` §3**.

## 4. Recrear con los clips del usuario
- Armá el proyecto como en `cs2-edit`: catálogo, análisis de la canción y de los clips, detección y verificación de kills y los **mínimos de visibilidad de cada kill**, que valen en cualquier estilo.
- Copiá las claves de `style.json["plan"]` a `plan.py` **reemplazando la línea donde cada variable ya está definida** (`BT`, `KILL_FX`, `LEAD_PLUS`, `END_LEN`…). No las agregues al final: `plan.py` las usa a mitad del archivo (`BT` arma las transiciones, `LEAD_PLUS` entra en `schedule()`), así que un valor puesto al final no cambia nada. Si una variable aparece varias veces (en `my_jealousy_v3`, `LEAD_PLUS` se reasigna justo antes de `schedule(ACT1, ...)`), cambiá la asignación que queda inmediatamente antes de usarse. `FRANTIC` va junto a las demás constantes de arriba.
- **`motor_nuevo`:** implementá cada cosa en `engine/render.py` como una función nueva **que se active solo si el plan define la variable** (por ejemplo `GRADE = {...}` o un nombre nuevo en `KILL_FX`), leída con `globals().get('GRADE')`, para que los proyectos viejos den exactamente el mismo resultado. Revisala en preview antes de usarla en todo el video. Leé antes `.claude/skills/cs2-edit/references/motor.md`. Cambiar `render.py` invalida la caché de pedazos: el primer render después tarda el tiempo completo.
- **Previews lado a lado:** un cuadro de la referencia y uno del edit nuevo en el mismo momento del patrón (transición, kill, color) para comparar. Ajustá hasta que se parezcan.
- Render (`engine/build.py`, en segundo plano), verificación (`check_render.txt`) y entrega en `output/<nombre>/` como en `cs2-edit`.

## 5. Guardar el estilo
Al terminar, ofrecé guardar el perfil como un skill propio del proyecto en `.claude/skills/cs2-edit-<nombre-del-estilo>/SKILL.md`, con `style.json` copiado al lado, para pedirlo después por nombre. El skill nuevo describe solo lo que cambia respecto de `cs2-edit` y le delega todo lo demás. Crealo solo si el usuario dice que sí.

## 6. Respuesta
Resumí en pocas líneas qué define el estilo, qué se replicó, qué se adaptó y por qué (por ejemplo la letra), y qué conviene revisar.
