# Opción secundaria y LENTA: el motor en modo CPU dentro de un contenedor (render con el procesador, libx264).
# El camino recomendado es el instalador (install.ps1 / install.sh), que usa la placa de video: Docker en Windows
# y en macOS no le pasa la GPU al contenedor (en Windows, tampoco las AMD por WSL para OpenGL/AMF).
#
#     docker build -t cs2-montage .
#     docker run --rm cs2-montage                                  # diagnóstico (engine/doctor.py)
#     docker run --rm -v "${PWD}:/app" cs2-montage python engine/build.py projects/<nombre>
#
# Montando la carpeta del repo en /app (-v) el contenedor ve tus proyectos, presets y config.json, y deja el
# resultado en output/ de tu disco. RIFE no se instala: las cámaras lentas salen con ffmpeg (minterpolate).
#
# NVIDIA en Linux (sin probar en hardware real): con nvidia-container-toolkit instalado en el host,
#
#     docker run --rm --gpus all -e NVIDIA_DRIVER_CAPABILITIES=all -e MONTAGE_DEVICE=auto \
#         -v "${PWD}:/app" cs2-montage python engine/build.py projects/<nombre>
#
# "all" incluye graphics (OpenGL por EGL, lo que usa engine/gpu.py) y video (NVENC). Si doctor sigue mostrando
# CPU, el contenedor no está viendo el driver: probá  docker run --rm --gpus all cs2-montage nvidia-smi
# Demucs sigue en CPU en esta imagen (PyTorch sin CUDA); para usar la placa: pip install torch==2.15.0 adentro.
FROM python:3.13-slim

# ffmpeg; libgl1 y libglib2.0-0 los pide OpenCV; libegl1 es para OpenGL sin pantalla (modo GPU con NVIDIA)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 libegl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir demucs==4.1.0

COPY . .
ENV MONTAGE_DEVICE=cpu PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
CMD ["python", "engine/doctor.py"]
