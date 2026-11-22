"""Instala RIFE (rife-ncnn-vulkan, licencia MIT) para las cámaras lentas: interpolación en la GPU por Vulkan
(AMD, NVIDIA e Intel), ~10 veces más rápida que minterpolate de ffmpeg.

    python engine/setup_rife.py            (no hace nada si ya está instalado)
    python engine/setup_rife.py --force    (lo baja de nuevo)

Baja el paquete oficial de https://github.com/nihui/rife-ncnn-vulkan/releases (versión 20221029, ~410 MB) y deja solo
lo necesario en tools/rife/ (el programa y el modelo rife-v4.6, ~17 MB). build.py lo usa solo si está instalado.
"""
import os, sys, zipfile, tempfile, urllib.request, shutil, platform

VERSION = '20221029'
NAMES = {'Windows': 'windows', 'Linux': 'ubuntu', 'Darwin': 'macos'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'tools', 'rife')
KEEP_MODEL = 'rife-v4.6'


def main():
    osname = NAMES.get(platform.system())
    if not osname:
        raise SystemExit(f'Sistema no soportado: {platform.system()}')
    exe = os.path.join(OUT, 'rife-ncnn-vulkan' + ('.exe' if os.name == 'nt' else ''))
    if os.path.isfile(exe) and os.path.isdir(os.path.join(OUT, KEEP_MODEL)) and '--force' not in sys.argv:
        print('RIFE ya está instalado en', OUT, '(para bajarlo de nuevo: --force)')
        return
    name = f'rife-ncnn-vulkan-{VERSION}-{osname}'
    url = f'https://github.com/nihui/rife-ncnn-vulkan/releases/download/{VERSION}/{name}.zip'
    tmp = tempfile.mkdtemp(prefix='rife_')
    zpath = os.path.join(tmp, 'rife.zip')
    print(f'Bajando {url} (~410 MB)...')
    try:
        urllib.request.urlretrieve(url, zpath)
        z = zipfile.ZipFile(zpath)
        pre = name + '/'
        os.makedirs(OUT, exist_ok=True)
        for n in z.namelist():
            rel = n[len(pre):] if n.startswith(pre) else ''
            if not rel or n.endswith('/'):
                continue
            if '/' not in rel or rel.startswith(KEEP_MODEL + '/'):       # programa, DLL, licencia y un solo modelo
                p = os.path.join(OUT, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, 'wb') as fh:
                    fh.write(z.read(n))
        if os.name != 'nt':
            os.chmod(exe, 0o755)
        print('RIFE instalado en', OUT)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
