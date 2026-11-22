"""Diagnóstico de la instalación: qué hay en esta computadora, qué falta, cómo instalarlo y con qué va a renderizar.

    python engine/doctor.py            tabla para leer
    python engine/doctor.py --json     lo mismo como datos (para una interfaz)

Sale con 0 si se puede renderizar (aunque falten cosas opcionales) y con 1 si falta algo imprescindible.
No instala ni cambia nada: solo mira. Lo corren los instaladores al terminar (install.ps1 / install.sh).
Qué significa cada línea: docs/instalacion.md.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import compat  # noqa: F401  (nombres viejos de las variables de entorno)
import argparse, glob, json, os, platform, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, ENGINE)

PY_MIN = (3, 11)
OPTIONAL_REQS = {'moderngl'}        # de requirements.txt, lo único que no hace falta para renderizar (sin él: modo CPU)
WIN, MAC, LINUX = sys.platform == 'win32', sys.platform == 'darwin', sys.platform.startswith('linux')
OK, WARN, MISSING, OPT = 'ok', 'aviso', 'falta', 'opcional'
MARK = {OK: '[ OK  ]', WARN: '[AVISO]', MISSING: '[FALTA]', OPT: '[  -  ]'}
PIP = 'python -m pip install'
INSTALLER = 'install.ps1' if WIN else 'install.sh'
# medido en projects/my_jealousy_v3 (2:22 a 1080p60) con Ryzen 5 7600X + RX 7900 XT: GPU 55 s, CPU 281 s
SPEED = {'gpu': 55 / 142, 'cpu': 281 / 142}       # segundos de render por segundo de video
ENC_LABEL = {'amf': 'AMD AMF', 'nvenc': 'NVIDIA NVENC', 'qsv': 'Intel Quick Sync', 'videotoolbox': 'Apple VideoToolbox',
             'vaapi': 'VAAPI', 'x264': 'libx264 (procesador)'}


def check(id, name, status, detail='', fix='', essential=False):
    return {'id': id, 'nombre': name, 'estado': status, 'detalle': detail, 'solucion': fix, 'imprescindible': essential}


def run(cmd, timeout=60, **kw):
    """Devuelve (código, stdout, stderr); código None si el programa no existe o se colgó."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, **kw)
        return r.returncode, r.stdout or '', r.stderr or ''
    except (OSError, subprocess.TimeoutExpired):
        return None, '', ''


def version_of(dist):
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


# ---------------------------------------------------------------- sistema
def cpu_name():
    try:
        if WIN:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as k:
                return winreg.QueryValueEx(k, 'ProcessorNameString')[0].strip()
        if MAC:
            return run(['sysctl', '-n', 'machdep.cpu.brand_string'])[1].strip() or platform.processor()
        with open('/proc/cpuinfo', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                if line.lower().startswith(('model name', 'hardware')):
                    return line.split(':', 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine()


def ram_gb():
    try:
        if WIN:
            import ctypes

            class MEM(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong)] + \
                           [(n, ctypes.c_ulonglong) for n in ('ullTotalPhys', 'ullAvailPhys', 'ullTotalPageFile',
                                                              'ullAvailPageFile', 'ullTotalVirtual', 'ullAvailVirtual',
                                                              'ullAvailExtendedVirtual')]
            m = MEM(); m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 2 ** 30
        if MAC:
            return int(run(['sysctl', '-n', 'hw.memsize'])[1]) / 2 ** 30
        return os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2 ** 30
    except Exception:
        return None


def os_name():
    if WIN:
        v = platform.version()
        try:
            name = 'Windows 11' if int(v.split('.')[2]) >= 22000 else f'Windows {platform.release()}'
        except (IndexError, ValueError):
            name = f'Windows {platform.release()}'
        return f'{name} ({v})'
    if MAC:
        return f'macOS {platform.mac_ver()[0]} ({platform.machine()})'
    try:
        return f"{platform.freedesktop_os_release().get('PRETTY_NAME', 'Linux')} ({platform.machine()})"
    except Exception:
        return f'Linux {platform.release()} ({platform.machine()})'


def os_gpus():
    """Placas de video según el sistema operativo (cuando OpenGL no anda y gpu.init no puede decir el nombre)."""
    if WIN:
        out = run(['powershell', '-NoProfile', '-Command',
                   '(Get-CimInstance Win32_VideoController).Name'], timeout=30)[1]
        return [l.strip() for l in out.splitlines() if l.strip()]
    if MAC:
        out = run(['system_profiler', 'SPDisplaysDataType'], timeout=30)[1]
        return [l.split(':', 1)[1].strip() for l in out.splitlines() if 'Chipset Model' in l]
    out = run(['lspci'])[1]
    return [l.split(': ', 1)[-1].strip() for l in out.splitlines() if re.search(r'VGA|3D controller|Display', l)]


def has_nvidia():
    return run(['nvidia-smi', '-L'], timeout=15)[0] == 0


def check_system():
    v = sys.version_info
    venv = sys.prefix != sys.base_prefix
    py = f'{v.major}.{v.minor}.{v.micro}' + (' (entorno virtual)' if venv else '') + f' - {sys.executable}'
    ram = ram_gb()
    return [
        check('os', 'Sistema operativo', OK, os_name()),
        check('cpu', 'Procesador', OK, f'{cpu_name()} ({os.cpu_count()} hilos)'),
        check('ram', 'Memoria', OK if ram is None or ram >= 15 else WARN,
              f'{ram:.0f} GB' if ram else 'no se pudo leer',
              '' if ram is None or ram >= 15 else 'Con menos de 16 GB el render puede quedarse sin memoria: usá --workers 2 o 3.'),
        check('python', 'Python', OK if v[:2] >= PY_MIN else MISSING, py,
              '' if v[:2] >= PY_MIN else f'Hace falta Python {PY_MIN[0]}.{PY_MIN[1]} o más nuevo: corré {INSTALLER}.',
              essential=True),
    ]


# ---------------------------------------------------------------- video
def check_opengl():
    """Corre gpu.init en otro proceso (un driver roto puede tirar abajo el intérprete) y devuelve nombre y versión."""
    if not version_of('moderngl'):
        gpus = os_gpus()
        return [check('gpu', 'Placa de video', OK if gpus else WARN, ', '.join(gpus) or 'no se detectó ninguna'),
                check('opengl', 'OpenGL 4.3 (render en la placa)', WARN, 'falta la librería moderngl',
                      f'{PIP} moderngl   (sin esto el render usa el procesador)')]
    code = ("import json, gpu; n = gpu.init(64, 64); "
            "print('@@' + json.dumps([n, gpu.ctx.info.get('GL_VERSION', ''), gpu.ctx.info.get('GL_VENDOR', '')]))")
    rc, out, err = run([sys.executable, '-c', code], cwd=ENGINE, timeout=90)
    m = re.search(r'@@(.*)', out)
    if rc == 0 and m:
        name, ver, vendor = json.loads(m.group(1))
        return [check('gpu', 'Placa de video', OK, name),
                check('opengl', 'OpenGL 4.3 (render en la placa)', OK, f'OpenGL {ver}')]
    gpus = os_gpus()
    why = (err.strip().splitlines() or ['no se pudo crear el contexto'])[-1][:160]
    if MAC:
        fix = 'macOS llega hasta OpenGL 4.1: el render usa el procesador (el codificador VideoToolbox sí es de la placa).'
    elif LINUX:
        fix = 'Actualizá el driver de video (Mesa o el propietario) e instalá EGL: sudo apt install libegl1 libgl1. Mientras tanto se usa el procesador.'
    else:
        fix = 'Actualizá el driver de la placa de video. Mientras tanto el render usa el procesador.'
    return [check('gpu', 'Placa de video', OK if gpus else WARN, ', '.join(gpus) or 'no se detectó ninguna'),
            check('opengl', 'OpenGL 4.3 (render en la placa)', WARN, why, fix)]


def ffmpeg_fix():
    if WIN:
        return 'winget install -e --id Gyan.FFmpeg   (después abrí una terminal nueva)'
    if MAC:
        return 'brew install ffmpeg'
    return 'sudo apt install ffmpeg   (o dnf / pacman, según la distribución)'


def check_ffmpeg():
    res = []
    for exe in ('ffmpeg', 'ffprobe'):
        path = shutil.which(exe)
        out = run([exe, '-version'])[1] if path else ''
        m = re.search(r'version (\S+)', out)
        if path and m:
            res.append(check(exe, exe, OK, m.group(1), essential=True) | {'ruta': path})
        else:
            res.append(check(exe, exe, MISSING, 'no está en el PATH', ffmpeg_fix(), essential=True))
    return res


def check_encoders():
    if not shutil.which('ffmpeg'):
        return [check('encoders', 'Codificadores de video', MISSING, 'sin ffmpeg no se puede probar', ffmpeg_fix(), essential=True)]
    import encoders
    found = encoders.available()
    forced = os.environ.get('MONTAGE_ENCODER')
    use = forced or found[0]
    detail = ', '.join(f'{k} ({encoders.NAMES[k]})' for k in found) + f' -> se usa {use}' + (' (forzado con MONTAGE_ENCODER)' if forced else '')
    if len(found) > 1:
        return [check('encoders', 'Codificadores de video', OK, detail)]
    listed = run(['ffmpeg', '-hide_banner', '-encoders'])[1]
    if 'libx264' not in listed:
        return [check('encoders', 'Codificadores de video', MISSING, 'este ffmpeg no trae libx264 ni un codificador de placa que funcione',
                      'Instalá un ffmpeg completo: ' + ffmpeg_fix(), essential=True)]
    return [check('encoders', 'Codificadores de video', WARN, detail,
                  'No funciona ningún codificador de la placa: se codifica con el procesador (más lento, misma calidad). '
                  'Actualizá el driver de video' + (' y revisá que exista /dev/dri/renderD128 (VAAPI).' if LINUX else '.'))]


HWACCELS = (('d3d11va', 'd3d11'), ('dxva2', 'dxva2_vld'), ('cuda', 'cuda'), ('qsv', 'qsv'), ('vaapi', 'vaapi'),
            ('videotoolbox', 'videotoolbox_vld'))


def check_hwdec():
    """Decodifica de verdad un H.264 chico con cada acelerador: '-hwaccel auto' cae al procesador sin avisar, así que
    acá se pide que el cuadro quede en la placa y se lo baja con hwdownload (falla si se decodificó por software)."""
    name = 'Decodificación por hardware'
    if not shutil.which('ffmpeg'):
        return [check('hwdec', name, WARN, 'sin ffmpeg no se puede probar')]
    listed = set(run(['ffmpeg', '-hide_banner', '-hwaccels'])[1].split())
    tmp = tempfile.mkdtemp(prefix='wako_doctor_')
    src = os.path.join(tmp, 'p.mp4')
    try:
        rc = run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=1280x720:r=30:d=0.5', '-c:v', 'libx264',
                  '-pix_fmt', 'yuv420p', src])[0]
        if rc != 0:
            return [check('hwdec', name, WARN, 'no se pudo generar el video de prueba')]

        def works(h):
            acc, fmt = h
            extra = ['-vaapi_device', (sorted(glob.glob('/dev/dri/renderD*')) or [''])[0]] if acc == 'vaapi' else []
            return run(['ffmpeg', '-v', 'error', *extra, '-hwaccel', acc, '-hwaccel_output_format', fmt, '-i', src,
                        '-vf', 'hwdownload,format=nv12', '-frames:v', '2', '-f', 'null', '-'], timeout=30)[0] == 0
        cands = [h for h in HWACCELS if h[0] in listed]
        with ThreadPoolExecutor(max(1, len(cands))) as ex:
            ok = [h[0] for h, good in zip(cands, ex.map(works, cands)) if good]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if ok:
        return [check('hwdec', name, OK, ', '.join(ok) + '   (los clips se leen con el decodificador de la placa)')]
    return [check('hwdec', name, WARN, 'ningún acelerador funcionó: los clips se decodifican con el procesador',
                  'No impide renderizar; en modo GPU es más lento. Actualizá el driver de video.')]


# ---------------------------------------------------------------- librerías
def read_requirements():
    """[(nombre, versión fijada o None)] de requirements.txt."""
    reqs = []
    try:
        with open(os.path.join(ROOT, 'requirements.txt'), encoding='utf-8') as fh:
            for line in fh:
                line = line.split('#')[0].strip()
                m = re.match(r'([A-Za-z0-9_.\-]+)\s*(?:==\s*([^\s;]+))?', line)
                if line and m:
                    reqs.append((m.group(1), m.group(2)))
    except OSError:
        pass
    return reqs


def check_requirements():
    reqs = read_requirements()
    if not reqs:
        return [check('requirements', 'Librerías de Python', WARN, 'no se pudo leer requirements.txt')]
    missing, other, ok = [], [], []
    for name, pin in reqs:
        v = version_of(name)
        if v is None and name == 'opencv-python':       # cualquiera de las variantes de OpenCV sirve
            v = version_of('opencv-python-headless') or version_of('opencv-contrib-python')
        if v is None:
            missing.append(name)
        else:
            ok.append(f'{name} {v}')
            if pin and v != pin:
                other.append(f'{name} {v} (probado con {pin})')
    res = []
    hard = [n for n in missing if n not in OPTIONAL_REQS]
    if hard:
        res.append(check('requirements', 'Librerías de Python', MISSING, 'faltan: ' + ', '.join(hard),
                         f'{PIP} -r requirements.txt   (o corré {INSTALLER})', essential=True))
    else:
        res.append(check('requirements', 'Librerías de Python', OK, ', '.join(ok), essential=True))
    if other:
        res.append(check('versions', 'Versiones', WARN, ', '.join(other),
                         f'Suele andar igual. Si algo falla, volvé a las versiones probadas: {PIP} -r requirements.txt'))
    return res


def check_torch():
    """Demucs separa voz y música (análisis de la canción y festejos): corre sobre PyTorch."""
    res = []
    dm = version_of('demucs')
    tv = version_of('torch')
    if not tv:
        res.append(check('torch', 'PyTorch', WARN, 'no está instalado',
                         f'Lo instala {INSTALLER} (elige la variante para tu placa). A mano: {PIP} torch torchaudio'))
    else:
        code = ("import json, torch; c = torch.cuda.is_available(); "
                "m = bool(getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available()); "
                "print('@@' + json.dumps([torch.__version__, c, torch.cuda.get_device_name(0) if c else '', m]))")
        rc, out, err = run([sys.executable, '-c', code], timeout=180)
        m = re.search(r'@@(.*)', out)
        if rc != 0 or not m:
            res.append(check('torch', 'PyTorch', WARN, f'{tv}, pero no se pudo importar: ' + (err.strip().splitlines() or ['?'])[-1][:120],
                             f'Reinstalalo: {PIP} --force-reinstall torch torchaudio'))
        else:
            ver, cuda, dev, mps = json.loads(m.group(1))
            if cuda:
                res.append(check('torch', 'PyTorch', OK, f'{ver} - ve la placa: {dev} (CUDA). Demucs corre en la GPU'))
            elif mps:
                res.append(check('torch', 'PyTorch', OK, f'{ver} - ve la GPU de Apple (MPS). Demucs corre en el procesador salvo que se le pida mps'))
            elif has_nvidia():
                res.append(check('torch', 'PyTorch', WARN, f'{ver} - no ve la placa NVIDIA: Demucs corre en el procesador',
                                 f'Instalá la variante CUDA: corré {INSTALLER} de nuevo, o mirá https://pytorch.org/get-started/locally/'))
            else:
                res.append(check('torch', 'PyTorch', OK, f'{ver} - sin CUDA: Demucs corre en el procesador '
                                 '(normal con placas AMD e Intel; una canción tarda 1-2 minutos)'))
    if dm:
        res.append(check('demucs', 'Demucs (separa voz y música)', OK if tv else WARN, dm))
    else:
        res.append(check('demucs', 'Demucs (separa voz y música)', WARN, 'no está instalado',
                         f'{PIP} demucs   (hace falta para analizar la canción y los festejos; no para renderizar)'))
    return res


def check_extras():
    exe = os.path.join(ROOT, 'tools', 'rife', 'rife-ncnn-vulkan' + ('.exe' if WIN else ''))
    model = glob.glob(os.path.join(ROOT, 'tools', 'rife', 'rife-v*'))
    if os.path.isfile(exe) and model:
        rife = check('rife', 'RIFE (cámaras lentas en la placa)', OK, f'tools/rife ({os.path.basename(model[0])})')
    else:
        rife = check('rife', 'RIFE (cámaras lentas en la placa)', OPT, 'no está instalado: las cámaras lentas se hacen con ffmpeg (lento)',
                     'python engine/setup_rife.py   (baja ~410 MB una vez)')
    fw = version_of('faster-whisper')
    whisper = check('whisper', 'faster-whisper (opcional)', OK if fw else OPT, fw or 'no está instalado',
                    '' if fw else f'{PIP} faster-whisper   (solo si querés transcribir la voz de la canción)')
    return [rife, whisper]


# ---------------------------------------------------------------- informe
def diagnose():
    groups = [check_system, check_opengl, check_ffmpeg, check_encoders, check_hwdec, check_requirements, check_torch, check_extras]

    def safe(fn):
        try:
            return fn()
        except BaseException as e:          # un chequeo roto no puede tapar al resto (encoders usa SystemExit)
            return [check(fn.__name__, fn.__name__, WARN, f'el chequeo falló: {e}')]
    with ThreadPoolExecutor(len(groups)) as ex:
        checks = [c for part in ex.map(safe, groups) for c in part]
    by = {c['id']: c for c in checks}
    ok = not any(c['imprescindible'] and c['estado'] == MISSING for c in checks)
    forced_dev = os.environ.get('MONTAGE_DEVICE', 'auto')
    mode = 'gpu' if by.get('opengl', {}).get('estado') == OK and forced_dev != 'cpu' else 'cpu'
    enc = None
    if by.get('encoders', {}).get('estado') in (OK, WARN):
        import encoders
        enc = os.environ.get('MONTAGE_ENCODER') or encoders.available()[0]
    est = round(150 * SPEED[mode] / 5) * 5
    return {
        'ok': ok,
        'modo': mode if ok else None,
        'placa': by.get('gpu', {}).get('detalle'),
        'codificador': enc,
        'estimado': {'video_seg': 150, 'render_seg': est,
                     'nota': 'orientativo: medido en un Ryzen 5 7600X con una RX 7900 XT, a 1080p y 60 fps'},
        'checks': checks,
    }


def report(d):
    w = max(len(c['nombre']) for c in d['checks'])
    print('\n  Diagnóstico de la instalación\n  ' + '-' * 29)
    for c in d['checks']:
        print(f"  {MARK[c['estado']]}  {c['nombre']:<{w}}  {c['detalle']}")
    todo = [c for c in d['checks'] if c['solucion']]
    if todo:
        print('\n  Qué falta y cómo resolverlo\n  ' + '-' * 27)
        for c in todo:
            print(f"  {MARK[c['estado']]}  {c['nombre']}:\n           {c['solucion']}")
    print()
    if not d['ok']:
        print('  NO se puede renderizar todavía: resolvé las líneas [FALTA] y volvé a correr  python engine/doctor.py\n')
        return
    e = d['estimado']
    how = (f"GPU ({d['placa']}): todo el cuadro se procesa en la placa" if d['modo'] == 'gpu'
           else 'CPU: el cuadro se procesa en el procesador ' +
           ('(forzado con MONTAGE_DEVICE=cpu)' if os.environ.get('MONTAGE_DEVICE') == 'cpu' else '(ver la línea de OpenGL)'))
    print(f'  Modo de render:  {how}')
    print(f"  Codificador:     {d['codificador']} - {ENC_LABEL.get(d['codificador'], d['codificador'])}")
    print(f"  Tiempo estimado: un edit de {e['video_seg'] // 60}:{e['video_seg'] % 60:02d} tarda cerca de "
          f"{max(1, round(e['render_seg'] / 60))} min ({e['nota']})")
    print('  Listo para renderizar.\n')


def main():
    ap = argparse.ArgumentParser(description='Diagnóstico de la instalación y del hardware.')
    ap.add_argument('--json', action='store_true', help='imprime el resultado como JSON')
    args = ap.parse_args()
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
    d = diagnose()
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        report(d)
    sys.exit(0 if d['ok'] else 1)


if __name__ == '__main__':
    main()
