# Cómo aportar

Gracias por sumarte. El proyecto arma montajes de CS2 al ritmo de la música y busca que cualquier canal pueda usarlo
sin perder la calidad del resultado.

## Qué aportes sirven más

- **Presets de estilo** (`presets/`): no tocan código. Ver `docs/presets.md`.
- **Pruebas en otro hardware:** el motor solo está probado en Windows con una placa AMD. Si lo corrés en NVIDIA, Intel,
  Linux o macOS, abrí un issue con la salida de `python engine/doctor.py` y de `python engine/regress.py <proyecto> --cross`.
- **Clips con otro HUD** (4:3, 16:10, otra escala): contá qué da `python engine/eval_kills.py`.
- Transiciones, efectos de kill y mejoras del detector: ver `docs/extender.md`.

## Reglas para un pull request

1. `python -m pytest --slow` pasa.
2. Si tocaste el render, `python engine/regress.py <proyecto> --cross` da más de 45 dB entre CPU y GPU, y contás en el
   PR si la imagen cambia a propósito.
3. Si tocaste el detector, `python engine/eval_kills.py` no baja el F1 (las pruebas tienen el piso).
4. Los valores de estilo van al preset, no al código; lo nuevo que cambie el resultado llega apagado por defecto.
5. No subas clips, canciones, logos ni videos: `projects/`, `entrada/` y `output/` están fuera del repo a propósito.
6. Código, comentarios y mensajes en español, como el resto del proyecto. Los comentarios explican el porqué.

## Música y contenido

El motor no distribuye música. Leé `docs/musica-y-derechos.md` antes de publicar un edit.
