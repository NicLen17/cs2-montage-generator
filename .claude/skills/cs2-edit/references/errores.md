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
- Usar clips de CS:GO (§2).
- Kills estimadas por retratos o audio en clips con la cámara sobre el killfeed: salían corridas, con un tiro errado a la vista y la kill final cortada (§2).
- Tomas que arrancan 1.6-2.2 s antes de la primera kill o huecos de 2.5-3 s entre kills dentro de un ACE: el redondeo al beat suma lead sin que se note en el plan (§3).
- Texto que tapa la play: frases, letras, títulos grandes en el centro (§7).
- Fundido a negro brusco y segundos muertos en negro antes del drop (§5).
- Sonido del juego bajo: cuatro pedidos. Con ganancia fija el juego quedaba 15 dB debajo de la música (la canción viene masterizada fuerte): ahora se nivela contra la música de cada video. Casi a la par (−3.4 dB) fue demasiado: el aprobado es el punto medio (−9.5 dB). Leé `audio_balance.txt` (§8).
- Festejos del final de la play cortados por una cola demasiado corta: la reacción llega 0.7-1.5 s después de la kill (§8).
- Gritos individuales resaltados (solo van los grupales) y un grito que siguió sonando sobre el clip siguiente: la reacción termina en el corte de su tramo (§8).
- Desfases de milisegundos entre kill y golpe por usar el beat estimado en vez del onset real (§4).
- Música que se repite o salta; tocar secciones que el usuario ya aprobó (§4, §10).
- Exportación cortada por un `timeout` (§9).
- Lectura del killfeed desfasada por un recorte de alto impar (395 → 394 filas): la detección se degradaba a lo largo del clip (§2).
- Secciones con buen ritmo "sonando solas": el drop de 1:12 de Faster N Harder (el bajo se corta y vuelve en el 2.º tiempo, 78.91 s) cayó en medio de un 4K sin kill; pasó también en My Jealousy, I Don't Like y Castlevania. El mapa de energía por compás no lo veía: ahora `analyze_song.py` busca la vuelta del bombo y `check_kills.py` exige una kill en cada momento de `SYNC` (§1, §4).
- Interludio a negro con orbes de luz: se sentía seco y la play revelada no caía en un drop real. Reemplazado por la revelación de la play hasta el drop principal (§5).
- Clip de 50 fps usado sin pasarlo a 60: el motor toma el cuadro por índice a 60 fps y mostraba imágenes 6 s más adelante (el cartel de victoria en vez de la kill). Revisá los fps de cada clip al copiarlos (§2).
- Cortes dentro de una play que salteaban 0.4-0.9 s del clip, cada uno con su transición (ACE de Mirage en Paparazzi V2, 1:35): no ahorraban nada y cortaban la inmersión. Un corte tiene que saltear más de 1 s; `check_kills.py` marca los CORTES QUE SOBRAN (§3). Los cortes largos de los ACE están bien.
- Kill mal cronometrada por el killfeed sobre un fondo claro (toldo verde de Mirage, c31 de Paparazzi V2): el detector la tomó 1.9 s tarde y el tramo arrancaba con el enemigo ya muerto. Cuando `check_kills.py` avisa de una kill del killfeed que no está en kf.json **cerca** de otra que sí está, revisá la entrada a ojo con una tira a 20 fps: puede ser la misma kill mal ubicada (§2).
