#!/usr/bin/env bash
# Instalador para Linux y macOS: deja el motor listo para usar en un entorno virtual (.venv) dentro de esta carpeta.
#
#     bash install.sh                 pregunta antes de instalar ffmpeg con el gestor de paquetes
#     bash install.sh --yes           no pregunta
#     bash install.sh --dry-run       simulación: muestra lo que haría, sin instalar ni crear nada
#
# Opciones: --venv CARPETA (por defecto .venv) · --extras whisper,ui,dev (extras de pyproject.toml) · --no-demucs ·
#           --no-rife · --torch-index URL (índice de PyTorch a usar) · --python EJECUTABLE
#
# Pasos (cada uno se saltea si ya está hecho, así que se puede correr las veces que haga falta):
#   1. Python 3.11 o más nuevo (no lo instala: dice cómo).
#   2. Entorno virtual y las librerías de requirements.txt (versiones fijadas). No toca el Python del sistema.
#   3. ffmpeg (si falta, ofrece instalarlo con apt / dnf / pacman / zypper / brew).
#   4. PyTorch para Demucs: con CUDA si hay una placa NVIDIA en Linux, la variante de CPU si no; en macOS la de PyPI.
#      Después, Demucs.
#   5. RIFE para las cámaras lentas (engine/setup_rife.py, baja ~410 MB una vez; necesita Vulkan).
#   6. Diagnóstico: engine/doctor.py.
#
# AVISO: implementado sin probar en hardware real (solo hay una PC con Windows para probar). Ver docs/instalacion.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
YES=0; DRY=0; NO_DEMUCS=0; NO_RIFE=0; EXTRAS=""; TORCH_INDEX=""; PYTHON=""
TORCH_VERSION="2.15.0"      # probadas juntas (Demucs 4.1.0 en Python 3.13)
DEMUCS_VERSION="4.1.0"
MIN_MINOR=11                # Python 3.11

while [ $# -gt 0 ]; do
    case "$1" in
        --yes|-y) YES=1 ;;
        --dry-run) DRY=1 ;;
        --no-demucs) NO_DEMUCS=1 ;;
        --no-rife) NO_RIFE=1 ;;
        --venv) VENV="$2"; shift ;;
        --extras) EXTRAS="$2"; shift ;;
        --torch-index) TORCH_INDEX="$2"; shift ;;
        --python) PYTHON="$2"; shift ;;
        -h|--help) sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Opción desconocida: $1 (ver --help)" >&2; exit 2 ;;
    esac
    shift
done

title() { printf '\n=== %s ===\n' "$1"; }
note() { printf '    %s\n' "$1"; }

# Corre un comando y corta el instalador si falla. En simulación solo lo muestra.
step() {
    if [ "$DRY" = 1 ]; then printf '    [simulación] %s\n' "$*"; return 0; fi
    printf '    > %s\n' "$*"
    "$@"
}

confirm() {
    if [ "$YES" = 1 ]; then return 0; fi
    if [ "$DRY" = 1 ]; then note "[simulación] preguntaría: $1"; return 0; fi
    if [ ! -t 0 ]; then
        note "$1 -> no se puede preguntar acá (sin teclado). Corré de nuevo con --yes para aceptarlo."
        return 1
    fi
    local answer
    read -r -p "    $1 [S/n] " answer
    case "$answer" in ""|s*|S*|y*|Y*) return 0 ;; *) return 1 ;; esac
}

have() { command -v "$1" >/dev/null 2>&1; }

# WAKO_OS=linux|macos permite simular el otro sistema con --dry-run
case "${WAKO_OS:-$(uname -s)}" in
    Linux|linux) OS=linux ;;
    Darwin|macos) OS=macos ;;
    *) echo "Este instalador es para Linux y macOS. En Windows usá install.ps1 (o setup_windows.bat)." >&2; exit 2 ;;
esac

echo "Instalador ($OS)"
note "Carpeta: $ROOT"
note "Entorno virtual: $VENV"
[ "$DRY" = 1 ] && note "SIMULACIÓN: no se instala ni se crea nada."

# ---------------------------------------------------------------- 1. Python
title "Python"
VENV_PY="$VENV/bin/python"
PY=""
for cand in "$PYTHON" python3 python3.13 python3.12 python3.11 python; do
    [ -n "$cand" ] && have "$cand" || continue
    if "$cand" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, $MIN_MINOR) else 1)" 2>/dev/null; then
        PY="$cand"; break
    fi
done
if [ -n "$PY" ]; then
    note "$("$PY" --version 2>&1) ($PY)"
elif [ ! -x "$VENV_PY" ]; then
    note "No encontré Python 3.$MIN_MINOR o más nuevo."
    if [ "$OS" = macos ]; then note "Instalalo con: brew install python@3.13"
    else note "Instalalo con: sudo apt install python3 python3-venv   (o el paquete equivalente de tu distribución)"; fi
    [ "$DRY" = 1 ] || exit 1
    PY=python3
fi

# ---------------------------------------------------------------- 2. entorno virtual y librerías
title "Entorno virtual y librerías"
if [ -x "$VENV_PY" ]; then
    note "El entorno virtual ya existe: se reusa."
elif ! step "$PY" -m venv "$VENV"; then
    note "No se pudo crear el entorno virtual. En Debian y Ubuntu falta un paquete: sudo apt install python3-venv"
    exit 1
fi
step "$VENV_PY" -m pip install --upgrade pip --disable-pip-version-check -q
step "$VENV_PY" -m pip install --disable-pip-version-check -r "$ROOT/requirements.txt"

# ---------------------------------------------------------------- 3. ffmpeg
title "ffmpeg"
if have ffmpeg && have ffprobe; then
    note "ffmpeg ya está instalado."
else
    note "No encontré ffmpeg en el PATH (hace falta para leer los clips y codificar el video)."
    CMD=""
    if [ "$OS" = macos ]; then
        if have brew; then CMD="brew install ffmpeg"; fi
    elif have apt-get; then CMD="sudo apt-get install -y ffmpeg"
    elif have dnf; then CMD="sudo dnf install -y ffmpeg"
    elif have pacman; then CMD="sudo pacman -S --noconfirm ffmpeg"
    elif have zypper; then CMD="sudo zypper install -y ffmpeg"
    fi
    if [ -z "$CMD" ]; then
        note "No reconozco el gestor de paquetes: instalá ffmpeg a mano (en macOS, con Homebrew: https://brew.sh)."
    elif confirm "¿Instalo ffmpeg con: $CMD ?"; then
        # shellcheck disable=SC2086
        step $CMD || note "No se pudo instalar ffmpeg. Instalalo a mano con: $CMD"
    else
        note "Sin ffmpeg no se puede renderizar. Para instalarlo después: $CMD"
    fi
fi

# ---------------------------------------------------------------- 4. PyTorch y Demucs
if [ "$NO_DEMUCS" = 0 ]; then
    title "PyTorch y Demucs (separa voz y música)"
    NVIDIA=0
    if have nvidia-smi && nvidia-smi -L >/dev/null 2>&1; then NVIDIA=1; fi
    STATE=""
    if [ -x "$VENV_PY" ]; then
        STATE="$("$VENV_PY" -c "import importlib.util as u
if u.find_spec('torch') is None: print('no')
else:
    import torch; print(torch.__version__, 'cuda' if torch.cuda.is_available() else 'cpu')" 2>/dev/null || true)"
    fi
    INDEX=()
    if [ -n "$TORCH_INDEX" ]; then INDEX=(--index-url "$TORCH_INDEX"); fi
    if [ -n "$STATE" ] && [ "$STATE" != no ] && { [ "$NVIDIA" = 0 ] || [[ "$STATE" == *cuda* ]]; }; then
        note "PyTorch ya está instalado ($STATE): se deja como está."
    elif [ "$OS" = macos ]; then
        note "macOS: PyTorch de PyPI (solo hay versión para Apple Silicon; Demucs corre en el procesador)."
        step "$VENV_PY" -m pip install --disable-pip-version-check "torch==$TORCH_VERSION" ${INDEX[@]+"${INDEX[@]}"}
    elif [ "$NVIDIA" = 1 ]; then
        note "Placa NVIDIA detectada: PyTorch con CUDA (el de PyPI en Linux ya la trae; descarga ~2.5 GB)."
        step "$VENV_PY" -m pip install --disable-pip-version-check "torch==$TORCH_VERSION" ${INDEX[@]+"${INDEX[@]}"}
    else
        note "Sin placa NVIDIA: PyTorch para CPU (Demucs corre en el procesador)."
        if [ -z "$TORCH_INDEX" ]; then INDEX=(--index-url https://download.pytorch.org/whl/cpu); fi
        step "$VENV_PY" -m pip install --disable-pip-version-check "torch==$TORCH_VERSION" "${INDEX[@]}"
    fi
    step "$VENV_PY" -m pip install --disable-pip-version-check "demucs==$DEMUCS_VERSION"
    note "El modelo de Demucs (~80 MB) se baja solo la primera vez que se separa una canción."
fi

# ---------------------------------------------------------------- 5. extras
if [ -n "$EXTRAS" ]; then
    title "Extras: $EXTRAS"
    IFS=',' read -r -a LIST <<< "$EXTRAS"
    for extra in "${LIST[@]}"; do
        extra="$(echo "$extra" | tr -d '[:space:]')"
        [ -n "$extra" ] || continue
        if [ "$DRY" = 1 ] && [ ! -x "$VENV_PY" ]; then note "[simulación] instalaría el extra '$extra' de pyproject.toml"; continue; fi
        SPECS="$("$VENV_PY" -c "import sys, tomllib
d = tomllib.load(open(sys.argv[1], 'rb'))['project']['optional-dependencies']
print('\n'.join(d.get(sys.argv[2], [])))" "$ROOT/pyproject.toml" "$extra")"
        if [ -z "$SPECS" ]; then note "El extra '$extra' no existe en pyproject.toml: se saltea."; continue; fi
        mapfile -t SPEC_LIST <<< "$SPECS" 2>/dev/null || IFS=$'\n' read -r -d '' -a SPEC_LIST <<< "$SPECS" || true
        step "$VENV_PY" -m pip install --disable-pip-version-check "${SPEC_LIST[@]}"
    done
fi

# ---------------------------------------------------------------- 6. RIFE
if [ "$NO_RIFE" = 0 ]; then
    title "RIFE (cámaras lentas en la placa)"
    step "$VENV_PY" "$ROOT/engine/setup_rife.py" ||
        note "Sin RIFE las cámaras lentas se hacen con ffmpeg (más lento). Para reintentar: python engine/setup_rife.py"
fi

# ---------------------------------------------------------------- 7. diagnóstico
title "Diagnóstico"
if [ "$DRY" = 1 ]; then
    note "[simulación] $VENV_PY engine/doctor.py"
    printf '\nSimulación terminada: no se cambió nada.\n'
    exit 0
fi
DOCTOR=0
"$VENV_PY" "$ROOT/engine/doctor.py" || DOCTOR=$?
echo
if [ "$DOCTOR" = 0 ]; then echo "Instalación lista."
else echo "La instalación terminó, pero falta algo imprescindible: mirá las líneas [FALTA] de arriba."; fi
echo "Para usar el motor, activá el entorno en cada terminal nueva:"
echo "    source \"$VENV/bin/activate\""
echo "y después, por ejemplo:  python engine/doctor.py"
exit "$DOCTOR"
