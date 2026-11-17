---
name: "clip-catalog"
description: "Catálogo de los clips de CS2 del usuario (catalog/clips.json): kills ya verificadas, disparos, arma, mapa, puntaje, etiquetas y en qué edits se usó cada clip. Usala para elegir plays para un edit ('qué ACEs tengo', 'qué clips no usé', 'los mejores con AWP'), cuando el usuario deja clips nuevos en entrada/, y dentro de cs2-edit para no volver a verificar a ojo clips ya verificados."
---

# Catálogo de clips

Verificar las kills de un clip a ojo es el paso más largo de un edit y donde más errores hubo. El catálogo guarda lo verificado **una vez** y lo reusa en todos los edits. Todo pasa por `engine/catalog.py` (sin dependencias nuevas). El catálogo vive en `catalog/clips.json`; la clave de cada clip es su slug de Twitch, así que el mismo clip descargado dos veces (`... (1).mp4`) es la misma entrada.

## Dentro de un edit (`cs2-edit`)
1. **Clips nuevos:** `python engine/catalog.py scan` (por defecto `entrada/`; o `scan <carpeta>`). Agrega fecha, duración, fps y era. Los de antes del 27/09/2023 quedan como `csgo` y no se usan.
2. **Elegir plays:** `python engine/catalog.py list` (ordenado por puntaje). Filtros: `--unused`, `--min-rating 4`, `--tag ace`, `--weapon awp`, `--map mirage`, `--all` (incluye CS:GO). Las mejores plays rápidas van a los drops (ver `cs2-edit` §4). Preferí clips que no se usaron en el edit anterior, salvo que el usuario pida repetir.
3. **Después de copiar los clips y escribir `clips_map.txt`:** `python engine/catalog.py prefill projects/<nombre>`. Escribe en `kf.json` y `shots.json` las kills y disparos de los clips ya verificados y crea `verified.json`. `analyze_clips.py` saltea esos clips (no los escanea ni recalcula sus disparos) y solo arma hojas de los clips a revisar.
4. **Después de verificar los clips nuevos y correr `--shots`:** `python engine/catalog.py import projects/<nombre>`. Guarda kills y disparos, marca en qué edit se usó cada clip y, para las plays con título, carga etiqueta (`ace`, `4k`, `clutch`…), arma o mapa y un puntaje inicial.
5. **Completar datos de los clips nuevos** (lo que viste en las hojas de contexto):
   `python engine/catalog.py set <parte_del_nombre> weapon=AK-47 map=Mirage rating=4 tags=3k,flick notes="360 al final"`
   También se puede apuntar a un clip por proyecto: `set c12@my_jealousy_v3 rating=5`.

## Reglas
- **Solo se marca `verified` lo que se verificó a ojo** contra el killfeed final (las reglas de `cs2-edit` §2). `import` lo hace con lo que hay en `kf.json`: no lo corras con un `kf.json` sin revisar.
- Si en un edit descubrís que una kill del catálogo estaba mal (faltaba una, tiempo corrido), corregí `kf.json` del proyecto y volvé a correr `import`: el catálogo se actualiza.
- Si un clip del catálogo se pasó de 50 a 60 fps al copiarlo, los tiempos siguen valiendo (la conversión no cambia la duración).
- **Puntaje (1-5):** 5 = ACE, clutch o play que puede abrir un drop movido; 4 = 4K o técnica (360, flick, run boost); 3 = 3K limpia; 2 = dos kills; 1 = one tap sin nada especial. 0 = sin puntuar.
- El catálogo es del usuario: no borres entradas. Si un archivo ya no está en `entrada/`, la entrada queda (sirve para saber que se usó).

## Consultas típicas
- "¿Qué ACEs tengo sin usar?" → `list --tag ace --unused`
- "Los mejores con AWP" → `list --weapon awp --min-rating 3`
- "¿Dónde usé este clip?" → `show <parte_del_nombre>`
