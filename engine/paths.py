"""Dónde queda cada cosa de un edit terminado: una carpeta por proyecto en output/.

    output/<nombre>/video/<nombre>.mp4          el edit largo (engine/build.py)
    output/<nombre>/shorts/<nombre>_short1.mp4  los shorts verticales (engine/short.py)
    output/<nombre>/info/                       miniaturas, youtube.md, redes.md, info.json, LEEME.md (engine/pack.py)

Antes todo iba suelto en output/ (output/<nombre>.mp4, output/<nombre>_short1.mp4, output/<nombre>_pack/): los que leen
un video lo buscan primero en el lugar nuevo y, si no está, en el viejo.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(ROOT, 'output')


def project_dir(name):
    return os.path.join(OUTPUT, name)


def video_dir(name):
    return os.path.join(project_dir(name), 'video')


def shorts_dir(name):
    return os.path.join(project_dir(name), 'shorts')


def info_dir(name):
    return os.path.join(project_dir(name), 'info')


def video_path(name, filename=None):
    """Dónde se escribe el edit largo (crea la carpeta)."""
    os.makedirs(video_dir(name), exist_ok=True)
    return os.path.join(video_dir(name), filename or f'{name}.mp4')


def short_path(name, filename):
    os.makedirs(shorts_dir(name), exist_ok=True)
    return os.path.join(shorts_dir(name), filename)


def find_video(name):
    """El edit largo ya renderizado: lugar nuevo, o el viejo output/<nombre>.mp4 si es un proyecto anterior."""
    new = os.path.join(video_dir(name), f'{name}.mp4')
    old = os.path.join(OUTPUT, f'{name}.mp4')
    if os.path.exists(new) or not os.path.exists(old):
        return new
    return old
