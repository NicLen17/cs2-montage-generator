# Errores que ya pasaron (historial)

Cada uno ya tiene su regla en `SKILL.md` (sección entre paréntesis). Repasá esta lista antes del render final y cuando el usuario marque un error, para ver si es uno que ya se había corregido antes.

- Kills que faltaban: la detección automática junta kills seguidas o las tapadas por humo. Se arregla contando contra el killfeed final y con la tabla de visibilidad (§2, §3).
- Kills cortadas o tapadas por la transición, o con 0.5 s de cola que no alcanzan para entender un wallbang (§3).
- Plays que arrancaban tarde y perdían lo que las hace épicas: el giro del 360, el enemigo cayendo, el salto del run boost, el cambio a la Deagle (§4).
- Título con el arma o el conteo equivocados: "DEAGLE" en una Glock, "4K" en un ACE (§4).
- Tramos que terminan mirando a la nada o en el momento ambiguo de la muerte (§4).
- Aceleraciones de velocidad en el gameplay; cámara lenta usada para estirar (§4, §6).
- Efectos que queman la imagen, demasiados pulsos seguidos en un ACE, zooms de más de 2x que pixelan (§6).
- "Tirones": efectos de kill que saltaban de golpe en un cuadro (zoom, sacudida aleatoria). Diagnóstico: cuadros repetidos y saltos de diferencia entre cuadros en el video final, justo en las kills (§6, `check_render.py`).
- Drops sin kill en el downbeat o con una play floja (dos taps en un drop frenético); kill un segundo después de la transición del drop (§4).
- Ráfagas de sílabas con tantos efectos que no se entendía que eran kills, y demasiadas ráfagas en un mismo video (§4).
- Usar clips de CS:GO (§2).
- Kills estimadas por retratos o audio en clips con la cámara sobre el killfeed: salían corridas, con un tiro errado a la vista y la kill final cortada (§2).
- Tomas que arrancan 1.6-2.2 s antes de la primera kill o huecos de 2.5-3 s entre kills dentro de un ACE: el redondeo al beat suma lead sin que se note en el plan (§3).
- Ráfaga que empezaba con una espera después de la kill del clip anterior (§4).
- Texto que tapa la play: frases, letras, títulos grandes en el centro (§7).
- Fundido a negro brusco y segundos muertos en negro antes del drop (§5).
- Sonido del juego bajo: tres pedidos seguidos para subirlo (§8).
- Desfases de milisegundos entre kill y golpe por usar el beat estimado en vez del onset real (§4).
- Música que se repite o salta; tocar secciones que el usuario ya aprobó (§4, §10).
- Exportación cortada por un `timeout` (§9).
- Lectura del killfeed desfasada por un recorte de alto impar (395 → 394 filas): la detección se degradaba a lo largo del clip (§2).
