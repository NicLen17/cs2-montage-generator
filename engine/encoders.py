"""Elige el codificador de video: GPU si existe (AMD AMF / NVIDIA NVENC / Intel QSV), si no CPU (libx264).
Forzar uno con la variable de entorno WAKO_ENCODER=amf|nvenc|qsv|x264."""
import os, subprocess, functools


@functools.lru_cache(None)
def available():
    try:
        out = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
    except FileNotFoundError:
        raise SystemExit('No se encontró ffmpeg en el PATH. Corré setup_windows.bat o instalalo con: winget install Gyan.FFmpeg')
    found = []
    for name, key in (('h264_amf', 'amf'), ('h264_nvenc', 'nvenc'), ('h264_qsv', 'qsv')):
        if name in out and _works(name):
            found.append(key)
    found.append('x264')
    return found


@functools.lru_cache(None)
def _works(name):
    """Prueba real de 1 cuadro: el encoder puede figurar en la lista y no funcionar (drivers)."""
    r = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=256x144:d=0.1', '-frames:v', '1',
                        '-c:v', name, '-f', 'null', '-'], capture_output=True)
    return r.returncode == 0


def pick():
    """build.py lo detecta una vez y lo deja en WAKO_ENCODER: los procesos de render lo heredan y no vuelven a probar
    los codificadores (eran 2-3 s por proceso)."""
    forced = os.environ.get('WAKO_ENCODER')
    if forced:
        return forced
    return available()[0]


def video_encoder_args(stage='intermediate', bitrate_mbps=None, src_nv12=False):
    """src_nv12: la entrada ya viene en NV12 (modo GPU): los codificadores de placa la toman directo, sin conversión."""
    a = _video_encoder_args(stage, bitrate_mbps)
    if src_nv12 and pick() in ('amf', 'nvenc'):
        a = ['nv12' if x == 'yuv420p' else x for x in a]
    return a


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
    if stage == 'intermediate':
        return ['-c:v', 'libx264', '-preset', 'fast', '-crf', '15', '-pix_fmt', 'yuv420p', '-g', '120']
    return ['-c:v', 'libx264', '-preset', 'fast', '-b:v', f'{bitrate_mbps}M', '-maxrate', f'{int(bitrate_mbps * 1.5)}M',
            '-bufsize', f'{bitrate_mbps * 2}M', '-pix_fmt', 'yuv420p']


if __name__ == '__main__':
    print('Codificadores que funcionan:', available(), '-> se usa:', pick())
