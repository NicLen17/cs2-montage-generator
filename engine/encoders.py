"""Elige el codificador de video: el de la placa si existe (AMD AMF / NVIDIA NVENC / Intel QSV / Apple VideoToolbox /
VAAPI en Linux), si no CPU (libx264). Cada uno se prueba de verdad con 1 cuadro antes de darlo por bueno.
Forzar uno con la variable de entorno MONTAGE_ENCODER=amf|nvenc|qsv|videotoolbox|vaapi|x264.
VAAPI usa el primer /dev/dri/renderD* (otro: MONTAGE_VAAPI_DEVICE=/dev/dri/renderD129)."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import compat  # noqa: F401  (nombres viejos de las variables de entorno)
import os, sys, glob, subprocess, functools

# en orden de preferencia; x264 (CPU) siempre queda al final como respaldo
HW = (('h264_amf', 'amf'), ('h264_nvenc', 'nvenc'), ('h264_qsv', 'qsv'),
      ('h264_videotoolbox', 'videotoolbox'), ('h264_vaapi', 'vaapi'))
NAMES = {**{key: name for name, key in HW}, 'x264': 'libx264'}


def vaapi_device():
    """Nodo DRM que usa VAAPI (solo Linux), o None si no hay ninguno."""
    dev = os.environ.get('MONTAGE_VAAPI_DEVICE')
    if dev:
        return dev
    devs = sorted(glob.glob('/dev/dri/renderD*'))
    return devs[0] if devs else None


@functools.lru_cache(None)
def available():
    try:
        out = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
    except FileNotFoundError:
        raise SystemExit('No se encontró ffmpeg en el PATH. Corré el instalador (install.ps1 en Windows, install.sh en '
                         'Linux y macOS) o mirá qué falta con: python engine/doctor.py')
    found = []
    for name, key in HW:
        if name in out and _works(name):
            found.append(key)
    found.append('x264')
    return found


@functools.lru_cache(None)
def _works(name):
    """Prueba real de 1 cuadro: el encoder puede figurar en la lista y no funcionar (drivers)."""
    pre = []
    if name == 'h264_vaapi':        # VAAPI no toma cuadros de la memoria común: hay que subirlos a la placa
        if not sys.platform.startswith('linux') or not vaapi_device():
            return False
        pre = ['-vaapi_device', vaapi_device(), '-vf', 'format=nv12,hwupload']
    r = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=256x144:d=0.1', '-frames:v', '1',
                        *pre, '-c:v', name, '-f', 'null', '-'], capture_output=True)
    return r.returncode == 0


def pick():
    """build.py lo detecta una vez y lo deja en MONTAGE_ENCODER: los procesos de render lo heredan y no vuelven a probar
    los codificadores (eran 2-3 s por proceso)."""
    forced = os.environ.get('MONTAGE_ENCODER')
    if forced:
        return forced
    return available()[0]


def video_encoder_args(stage='intermediate', bitrate_mbps=None, src_nv12=None):
    """src_nv12: la entrada ya viene en NV12 (modo GPU): los codificadores de placa la toman directo, sin conversión.
    Pasar src_nv12 (True o False) también le dice a esta función que la entrada es un flujo de cuadros crudos sin
    filtros propios (el render). Solo ahí se usa VAAPI, que necesita su propio '-vf ...hwupload': en los comandos que
    ya traen filtros (shorts, cámaras lentas) pisaría los del comando, así que esos salen con libx264."""
    if pick() == 'vaapi':
        if stage == 'final' and bitrate_mbps is None:
            bitrate_mbps = 30
        return _x264_args(stage, bitrate_mbps) if src_nv12 is None else _vaapi_args(stage, bitrate_mbps)
    a = _video_encoder_args(stage, bitrate_mbps)
    if src_nv12 and pick() in ('amf', 'nvenc'):
        a = ['nv12' if x == 'yuv420p' else x for x in a]
    return a


def _vaapi_args(stage, bitrate_mbps):
    pre = ['-vaapi_device', vaapi_device() or '/dev/dri/renderD128', '-vf', 'format=nv12,hwupload', '-c:v', 'h264_vaapi']
    if stage == 'intermediate':
        return pre + ['-rc_mode', 'CQP', '-qp', '16']
    return pre + ['-rc_mode', 'VBR', '-b:v', f'{bitrate_mbps}M', '-maxrate', f'{int(bitrate_mbps * 1.5)}M']


def _x264_args(stage, bitrate_mbps):
    if stage == 'intermediate':
        return ['-c:v', 'libx264', '-preset', 'fast', '-crf', '15', '-pix_fmt', 'yuv420p', '-g', '120']
    return ['-c:v', 'libx264', '-preset', 'fast', '-b:v', f'{bitrate_mbps}M', '-maxrate', f'{int(bitrate_mbps * 1.5)}M',
            '-bufsize', f'{bitrate_mbps * 2}M', '-pix_fmt', 'yuv420p']


def _video_encoder_args(stage='intermediate', bitrate_mbps=None):
    """stage='intermediate': casi sin pérdida (cámaras lentas). stage='final': tamaño razonable para subir.
    Los pedazos del render se codifican directo con 'final' y se unen sin recodificar (todos con los mismos ajustes)."""
    enc = pick()
    if stage == 'final' and bitrate_mbps is None:
        bitrate_mbps = 30
    if enc == 'amf':
        if stage == 'intermediate':
            return ['-c:v', 'h264_amf', '-quality', 'quality', '-rc', 'cqp', '-qp_i', '14', '-qp_p', '16', '-qp_b', '18', '-pix_fmt', 'yuv420p']
        return ['-c:v', 'h264_amf', '-quality', 'quality', '-rc', 'vbr_peak', '-b:v', f'{bitrate_mbps}M',
                '-maxrate', f'{int(bitrate_mbps * 1.5)}M', '-pix_fmt', 'yuv420p']
    if enc == 'nvenc':
        if stage == 'intermediate':
            return ['-c:v', 'h264_nvenc', '-preset', 'p6', '-rc', 'constqp', '-qp', '15', '-pix_fmt', 'yuv420p']
        return ['-c:v', 'h264_nvenc', '-preset', 'p6', '-rc', 'vbr', '-b:v', f'{bitrate_mbps}M',
                '-maxrate', f'{int(bitrate_mbps * 1.5)}M', '-pix_fmt', 'yuv420p']
    if enc == 'qsv':
        if stage == 'intermediate':
            return ['-c:v', 'h264_qsv', '-global_quality', '16', '-pix_fmt', 'nv12']
        return ['-c:v', 'h264_qsv', '-b:v', f'{bitrate_mbps}M', '-pix_fmt', 'nv12']
    if enc == 'videotoolbox':       # sin calidad constante portable (-q:v solo anda en Apple Silicon): bitrate alto
        if stage == 'intermediate':
            return ['-c:v', 'h264_videotoolbox', '-b:v', '80M', '-pix_fmt', 'yuv420p']
        return ['-c:v', 'h264_videotoolbox', '-b:v', f'{bitrate_mbps}M', '-maxrate', f'{int(bitrate_mbps * 1.5)}M',
                '-pix_fmt', 'yuv420p']
    return _x264_args(stage, bitrate_mbps)


if __name__ == '__main__':
    print('Codificadores que funcionan:', available(), '-> se usa:', pick())
