"""Nombres viejos que siguen valiendo. Las variables de entorno del motor se llamaban WAKO_* (el canal donde nació);
ahora son MONTAGE_*: si alguien todavía usa las viejas, se copian al nombre nuevo."""
import os

for _k, _v in list(os.environ.items()):
    if _k.startswith('WAKO_'):
        os.environ.setdefault('MONTAGE_' + _k[5:], _v)
