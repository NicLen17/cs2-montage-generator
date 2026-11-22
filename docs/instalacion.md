# Instalación y hardware

El motor corre entero en tu computadora. La instalación recomendada es el **instalador**, que detecta tu hardware,
arma un entorno virtual (`.venv`) dentro de la carpeta del proyecto y no toca el Python del sistema. Docker queda
como opción secundaria y lenta (ver [Docker](#docker-opción-secundaria-y-lenta)).

## Requisitos

| | Mínimo | Recomendado |
|---|---|---|
| Sistema | Windows 10/11, Linux o macOS (64 bits) | Windows 11 |
| Python | 3.11 | 3.13 (con la que se probaron las versiones fijadas) |
| Memoria | 8 GB (con `--workers 2`) | 16 GB o más |
| Placa de video | ninguna: todo anda en modo CPU | cualquiera con **OpenGL 4.3** y codificador H.264 (AMD, NVIDIA, Intel) |
| Disco | ~3 GB (librerías, PyTorch, Demucs, RIFE) más tus clips | |
| ffmpeg | con `libx264` | compilación completa (trae los codificadores de placa) |

Sin placa (o sin OpenGL 4.3) el render sale igual, con el procesador: mismo resultado, unas 5 veces más lento.

## Windows

1. Bajá o cloná el repositorio.
2. Doble clic en **`setup_windows.bat`** (es un lanzador de `install.ps1`). O, desde PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

3. Al terminar muestra el diagnóstico. En cada terminal nueva, activá el entorno antes de usar el motor:

```powershell
.\.venv\Scripts\Activate.ps1
```

Qué hace `install.ps1`, en orden (cada paso se saltea si ya está hecho: se puede correr dos veces sin romper nada):

1. Busca Python 3.11+ (`py -3`, `python`). Si no hay, **pregunta** antes de instalarlo con winget.
2. Crea `.venv` e instala `requirements.txt` (versiones fijadas).
3. Si falta ffmpeg, **pregunta** antes de instalarlo con winget (`Gyan.FFmpeg`). ffmpeg no viene con el proyecto.
4. Instala PyTorch para Demucs: con CUDA si detecta una placa NVIDIA (`nvidia-smi`), la variante de CPU si no.
   Con placas AMD e Intel en Windows, Demucs corre en el procesador (una canción tarda 1-2 minutos). Después, Demucs.
5. Baja RIFE (cámaras lentas en la placa, ~410 MB una vez) con `engine/setup_rife.py`. RIFE tampoco viene con el proyecto.
6. Corre `engine/doctor.py`.

Opciones: `-Yes` (no pregunta), `-DryRun` (simulación: muestra los comandos sin ejecutar nada), `-Venv <carpeta>`,
`-Extras whisper,ui,dev`, `-NoDemucs`, `-NoRife`, `-TorchIndex <url>`, `-Python <python.exe>`.

## Linux

```bash
bash install.sh
```

Hace lo mismo que el de Windows. Diferencias:

- Python no lo instala: si falta, dice el comando (`sudo apt install python3 python3-venv`).
- ffmpeg lo ofrece con `apt`, `dnf`, `pacman` o `zypper` (pregunta antes; usa `sudo`).
- PyTorch: con NVIDIA usa el de PyPI (ya trae CUDA); sin NVIDIA, la variante de CPU, que pesa mucho menos.
- Para el modo GPU hacen falta los drivers de video con OpenGL 4.3 y, en equipos sin pantalla, EGL:
  `sudo apt install libegl1 libgl1`. Para RIFE, Vulkan: `sudo apt install libvulkan1`.
- Codificador: NVENC (NVIDIA), QSV (Intel), AMF (AMD con el driver propietario) o **VAAPI** (AMD e Intel con Mesa;
  necesita permiso sobre `/dev/dri/renderD128`, normalmente estar en el grupo `render` o `video`).
  Con VAAPI, el render principal usa la placa; los shorts y las cámaras lentas se codifican con libx264.

Opciones: `--yes`, `--dry-run`, `--venv <carpeta>`, `--extras whisper,ui,dev`, `--no-demucs`, `--no-rife`,
`--torch-index <url>`, `--python <ejecutable>`.

## macOS

```bash
bash install.sh
```

- ffmpeg se ofrece con Homebrew (`brew install ffmpeg`).
- **El render usa siempre el procesador:** macOS llega hasta OpenGL 4.1 y el modo GPU del motor necesita 4.3.
  El codificador sí es el de la placa (**VideoToolbox**).
- PyTorch 2.15 solo publica versión para Apple Silicon. En una Mac con Intel, instalá con `--no-demucs`
  (el render anda; el análisis de la canción que usa Demucs, no).

## Instalación a mano

Si preferís no usar el instalador:

```bash
python -m venv .venv                      # y activarlo
python -m pip install -r requirements.txt # versiones fijadas (las probadas)
python -m pip install torch==2.15.0       # ver https://pytorch.org/get-started/locally/ para la variante CUDA
python -m pip install demucs==4.1.0
python engine/setup_rife.py               # opcional
python engine/doctor.py
```

`pyproject.toml` declara lo mismo con versiones mínimas y extras opcionales, por si usás otro gestor:
`pip install -e ".[gpu,demucs]"`. Extras: `gpu` (moderngl), `demucs`, `whisper` (faster-whisper), `ui`
(fastapi + uvicorn), `dev` (pytest). No se instala ningún paquete propio: los scripts se corren siempre como
`python engine/<script>.py`.

## Diagnóstico: `python engine/doctor.py`

No instala ni cambia nada: solo mira. Sale con código **0** si se puede renderizar y **1** si falta algo
imprescindible. `--json` da lo mismo como datos (para una interfaz).

Estados: `[ OK ]` está y funciona · `[AVISO]` anda, pero más lento o con una limitación · `[FALTA]` imprescindible,
no se puede renderizar · `[ - ]` opcional, no instalado.

| Línea | Qué mira | Si no está |
|---|---|---|
| Sistema operativo, Procesador, Memoria | Informativo. Avisa con menos de 16 GB. | Usar `--workers 2` o `3` en el render. |
| Python | Versión (3.11 o más) y si es el del entorno virtual. | **Imprescindible.** |
| Placa de video | El nombre que devuelve el driver de OpenGL (el mismo que usa el render). Si OpenGL no anda, el que informa el sistema. | Informativo. |
| OpenGL 4.3 | Crea de verdad el contexto que usa el modo GPU (`engine/gpu.py`); en Linux sin pantalla prueba EGL. | Modo CPU. Actualizar el driver de video; `pip install moderngl`. |
| ffmpeg, ffprobe | Que estén en el PATH, y la versión. | **Imprescindible.** |
| Codificadores de video | Prueba real de 1 cuadro con cada uno: `amf`, `nvenc`, `qsv`, `videotoolbox`, `vaapi`; `x264` (procesador) siempre queda de respaldo. Dice cuál se usa. | Solo `x264`: se codifica con el procesador. Forzar uno: variable `MONTAGE_ENCODER`. |
| Decodificación por hardware | Decodifica de verdad un video de prueba con cada acelerador de ffmpeg (d3d11va, dxva2, cuda, qsv, vaapi, videotoolbox). | Los clips se leen con el procesador (más lento en modo GPU). |
| Librerías de Python | Las de `requirements.txt`. | **Imprescindible** (salvo `moderngl`, que solo hace falta para el modo GPU). |
| Versiones | Aparece solo si alguna librería no es la versión fijada. | Suele andar igual. |
| PyTorch | Versión y si ve la placa (CUDA). Con AMD e Intel es normal que diga CPU. | Demucs no anda. |
| Demucs | Separa voz y música: lo usan el análisis de la canción y los festejos. | No impide renderizar un edit ya planeado. |
| RIFE | `tools/rife/` (cámaras lentas interpoladas en la placa, por Vulkan). | Las hace ffmpeg, ~10 veces más lento. `python engine/setup_rife.py`. |
| faster-whisper | Opcional: transcribir la voz de la canción. | Nada. |

Al final dice el **modo de render** (GPU o CPU), el codificador y un **tiempo estimado orientativo**. La estimación
sale de una sola medición (un edit de 2:22 a 1080p60 con Ryzen 5 7600X + RX 7900 XT: 55 s en GPU, 281 s en CPU):
no se ajusta a tu hardware, es una referencia.

Variables útiles: `MONTAGE_DEVICE=cpu|gpu|auto` (igual que `--device` de `build.py`), `MONTAGE_ENCODER=amf|nvenc|qsv|videotoolbox|vaapi|x264`,
`MONTAGE_VAAPI_DEVICE=/dev/dri/renderD129` (otra placa para VAAPI).

## Qué está probado y qué no

Solo hay una computadora para probar: Windows 11 + Ryzen 5 7600X + Radeon RX 7900 XT. Todo lo demás está
implementado siguiendo la documentación de ffmpeg, ModernGL y PyTorch, **sin probar en hardware real**. Si lo usás
en otra combinación, contá cómo te fue (la salida de `python engine/doctor.py` alcanza).

| Combinación | Render | Codificador | Estado |
|---|---|---|---|
| Windows 11 + AMD Radeon | GPU (OpenGL 4.3) | AMF | **Probado**: instalador, `doctor`, render y regresión de imagen |
| Windows, sin usar la placa (`--device cpu`, `MONTAGE_ENCODER=x264`) | CPU | libx264 | **Probado** en la misma PC |
| Windows + NVIDIA | GPU | NVENC | Implementado, sin probar (incluye PyTorch con CUDA para Demucs) |
| Windows + Intel (Arc / integrada) | GPU | QSV | Implementado, sin probar |
| Linux + NVIDIA | GPU (X11 o EGL) | NVENC | Implementado, sin probar |
| Linux + AMD / Intel (Mesa) | GPU (X11 o EGL) | VAAPI (o QSV / AMF) | Implementado, sin probar |
| Linux sin placa / servidor | CPU | libx264 | Implementado, sin probar |
| macOS (Apple Silicon) | CPU (no hay OpenGL 4.3) | VideoToolbox | Implementado, sin probar |
| macOS (Intel) | CPU | VideoToolbox | Implementado, sin probar; sin Demucs |
| Docker (CPU) | CPU | libx264 | Implementado, sin probar |
| Docker + NVIDIA en Linux | GPU (EGL) | NVENC | Implementado, sin probar |

Detalle de lo que se probó de `install.sh`: la sintaxis y el modo `--dry-run` (los comandos que correría en Linux
y en macOS). No se corrió una instalación real en esos sistemas.

## Docker (opción secundaria y lenta)

Docker en Windows y en macOS no le pasa la placa de video al contenedor, así que la imagen trabaja en **modo CPU**
(libx264, sin RIFE). Sirve para probar el motor sin instalar nada o para un servidor Linux; para editar en serio,
usá el instalador.

```bash
docker build -t cs2-montage .
docker run --rm cs2-montage                                                    # diagnóstico
docker run --rm -v "${PWD}:/app" cs2-montage python engine/build.py projects/<nombre>
```

Con una placa NVIDIA en Linux y `nvidia-container-toolkit` se puede usar la GPU dentro del contenedor (sin probar):
las instrucciones están al principio del `Dockerfile`.

## Problemas frecuentes

- **"python" o "ffmpeg" no se encuentran después de instalarlos:** cerrá la terminal, abrí una nueva y corré el
  instalador otra vez (el PATH se actualiza en las ventanas nuevas).
- **PowerShell no deja correr el script:** usá `powershell -ExecutionPolicy Bypass -File install.ps1` o el `.bat`.
- **Tengo placa pero `doctor` dice modo CPU:** mirá la línea de OpenGL; casi siempre es el driver de video
  desactualizado (o, en Linux, falta `libegl1`).
- **pip falla con "No such file or directory" y menciona "Long Path":** Windows limita las rutas a 260 caracteres y
  PyTorch trae archivos con nombres muy largos. Mové la carpeta del proyecto a una ruta más corta (por ejemplo
  `C:\edits`) y corré el instalador otra vez.
- **El render falla por memoria:** bajá `--workers`.
- **Empezar de cero:** borrá la carpeta `.venv` y corré el instalador de nuevo. `tools/rife/` se puede dejar.
