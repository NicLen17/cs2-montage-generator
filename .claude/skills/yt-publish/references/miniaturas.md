# Miniaturas de CS que funcionan (referencias reales)

Análisis del 17/11/2026 de los videos más vistos (pestaña "Popular") y de los más recientes de tres canales de CS con éxito. Sirve para elegir el tipo de miniatura y para no inventar: cada regla de abajo sale de lo que se repite en las miniaturas con más vistas.

## Los tres canales

### FURI (`@FURI`, inglés): cara gigante + objeto + 2 palabras
- **Más vistos (2.7 M, 2.6 M, 2.1 M, 1.5 M):** "INHUMAN AIM + mouse cam" con una flecha roja enorme señalando la cámara del mouse; un solo ícono de headshot blanco sobre negro ("80% AVERAGE HEADSHOTS?!", 2.6 M); "CHEATER?" sobre la cara del jugador acusado y su nivel de FACEIT; la mira de un AWP sobre un auto ("FerrariPEEK").
- **Recientes (estilo actual, 100-650 k):** casi todas iguales: **la cara del youtuber recortada, enorme, a la derecha**, con expresión exagerada (boca abierta, manos en la cara, dedo en la boca); fondo de un mapa de CS2 desenfocado; **1 a 3 palabras** gigantes en blanco con contorno negro e inclinadas ("FINALLY BACK", "CS:GO IS BACK!", "BLIND x50", "SILENT RELOAD"); un objeto que explica el video (mouse, joystick, ícono de nivel 10 de FACEIT, una bala, cajas de skins) y **una flecha o círculo rojo** apuntándolo; a veces un número en una pastilla ("$1", "0.1 MS", "1 HP", "#1").

### realFURI (`@realFURI`, español): gameplay real + cámara agrandada + 1 palabra
- **Más vistos (408 k, 176 k, 130 k, 128 k, 105 k):** un **cuadro real de la partida** (arma con skin colorida, enemigo, sangre, killfeed visible) con **la cámara del streamer agrandada arriba a la izquierda**, con cara expresiva (mano en el mentón, sonrisa, sorpresa). Texto corto abajo a la izquierda, blanco con contorno negro grueso: "1080X1080", "1440X1080", "3600 ELO", "HE'S CHEATING". Con invitados, sus cámaras también aparecen.
- Variantes: comparación partida en dos ("1920X1080 0.79 KD" en rojo → "1024X768 1.79 KD" en verde, con flecha), íconos de rango o de temporada, banderas.

### Dareh (`@Dareh`, español rioplatense): un cuadro raro del juego, sin texto
- **Más vistos (1 M, 509 k, 500 k, 499 k):** **un solo cuadro del juego, sin texto ni caras**: un enemigo de cerca en una pose rara, una salpicadura de sangre enorme, alguien flotando, el nombre del jugador sobre la cabeza. El HUD casi no se ve, un solo protagonista en el centro, colores saturados. La gracia la lleva el título ("vos sos normal?", "planta pelado porque te mato"). Alguna excepción con meme encima (ojos láser) o el "50.000" de un especial.

## Lo que se repite en las que más funcionan
1. **Un solo foco claro**, legible a 320 px de ancho (como se ve en el celular): una cara, un enemigo, un objeto. Nada chico en el medio.
2. **Texto mínimo: 0 a 3 palabras**, mayúsculas, sans muy pesada, blanco con contorno negro grueso y sombra. Nunca repite el título: lo complementa ("ACE", "1v4", "3600 ELO").
3. **Un color de acento** para la palabra o el número clave (amarillo, rojo o verde) y **flechas o círculos rojos** que dirigen la mirada al detalle importante.
4. **Caras con emoción** cuando hay cámara: el youtuber/streamer reaccionando vende más que el gameplay solo (FURI y realFURI la usan en casi todo).
5. **Gameplay real y reconocible**: skins coloridas, killfeed, el enemigo visible. Contraste y saturación más altos que el video.
6. **Números concretos** cuando existen ("4K", "1v4", "3600 ELO", "$1", "0.1 MS").
7. Composición: texto de un lado, foco del otro; lo importante lejos de la esquina de abajo a la derecha (ahí YouTube pone la duración).

## Tipos de miniatura del proyecto (de qué referencia sale cada uno)
| Tipo | Inspirado en | Cuándo usarlo | Qué lleva |
|---|---|---|---|
| `jugada` (**por defecto en montajes**) | realFURI | edits de plays, montajes con canción | cuadro de la mejor kill + cámara del streamer agrandada con su reacción + 1-2 palabras ("ACE", "1v4") + subtítulo en pastilla de color |
| `reaccion` | FURI actual | videos donde la reacción es el gancho (clutch increíble, momento gracioso, "casi 5K") | cara del streamer grande a la derecha + fondo de la jugada desenfocado + texto grande a la izquierda + flecha roja opcional |
| `limpia` | Dareh | funny moments, videos de curiosidad, cuando el título hace la gracia | un solo cuadro llamativo sin texto, con zoom hacia el foco y color subido |
| `versus` | realFURI (comparaciones) | antes/después, ajustes, "X vs Y" | dos cuadros partidos en diagonal + "VS" + etiqueta en cada lado (el que gana en verde, el que pierde en rojo) |

## Lo que no se copia
- Ni caras, ni logos, ni arte de esos canales: solo los patrones de composición. La cara es siempre la del streamer del propio canal (sale de su cámara en los clips).
- Nada de "clickbait" que el video no cumple: si dice ACE, el video tiene el ACE (regla de `cs2-edit`).
