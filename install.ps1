<#
.SYNOPSIS
Instalador para Windows: deja el motor listo para usar en un entorno virtual (.venv) dentro de esta carpeta.

.DESCRIPTION
Pasos (cada uno se saltea si ya está hecho, así que se puede correr las veces que haga falta):
  1. Python 3.11 o más nuevo (si falta, ofrece instalarlo con winget).
  2. Entorno virtual .venv y las librerías de requirements.txt (versiones fijadas). No toca el Python del sistema.
  3. ffmpeg (si falta, ofrece instalarlo con winget).
  4. PyTorch para Demucs: con CUDA si hay una placa NVIDIA; si no, la variante de CPU (con AMD e Intel en Windows
     Demucs corre en el procesador). Después, Demucs.
  5. RIFE para las cámaras lentas (engine\setup_rife.py, baja ~410 MB una vez).
  6. Diagnóstico: engine\doctor.py.

Este archivo está guardado en UTF-8 con BOM (Windows PowerShell 5.1 lo necesita para leer los acentos).

.PARAMETER Yes
No pregunta: acepta instalar Python y ffmpeg con winget si faltan.
.PARAMETER DryRun
Simulación: muestra lo que haría, sin instalar ni crear nada.
.PARAMETER Venv
Carpeta del entorno virtual (por defecto .venv en esta carpeta).
.PARAMETER Extras
Extras opcionales de pyproject.toml separados por coma: whisper, ui, dev.
.PARAMETER NoDemucs
No instala PyTorch ni Demucs.
.PARAMETER NoRife
No instala RIFE.
.PARAMETER TorchIndex
Índice de PyTorch para placas NVIDIA (por defecto el de CUDA 13.2).
.PARAMETER Python
Ruta a un python.exe para crear el entorno (por defecto se busca con py -3 y python).

.EXAMPLE
powershell -ExecutionPolicy Bypass -File install.ps1
.EXAMPLE
powershell -ExecutionPolicy Bypass -File install.ps1 -Yes -Extras whisper,dev
#>
param(
    [switch]$Yes,
    [switch]$DryRun,
    [string]$Venv,
    [string]$Extras = '',
    [switch]$NoDemucs,
    [switch]$NoRife,
    [string]$TorchIndex = 'https://download.pytorch.org/whl/cu132',
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Venv) { $Venv = Join-Path $Root '.venv' }
$TorchVersion = '2.15.0'      # probadas juntas (Demucs 4.1.0 en Python 3.13)
$DemucsVersion = '4.1.0'
$MinMinor = 11                # Python 3.11
$TorchCpuIndex = 'https://download.pytorch.org/whl/cpu'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = 'utf-8'

function Write-Title($text) { Write-Host ''; Write-Host "=== $text ===" -ForegroundColor Cyan }
function Write-Note($text) { Write-Host "    $text" }

function Invoke-Step {
    # Corre un programa y corta el instalador si falla. En simulación solo lo muestra.
    param([string]$Exe, [string[]]$Arguments, [switch]$Optional)
    $shown = "$Exe $($Arguments -join ' ')"
    if ($DryRun) { Write-Host "    [simulación] $shown" -ForegroundColor DarkGray; return $true }
    Write-Host "    > $shown" -ForegroundColor DarkGray
    & $Exe @Arguments | Out-Host      # Out-Host: que la salida se vea y no se mezcle con el valor devuelto
    if ($LASTEXITCODE -ne 0) {
        if ($Optional) { Write-Host "    No se pudo completar (código $LASTEXITCODE). Sigo con el resto." -ForegroundColor Yellow; return $false }
        Write-Host "    Si el error habla de una ruta o archivo que no existe ('Long Path'), la carpeta del proyecto es demasiado" -ForegroundColor Yellow
        Write-Host "    profunda para Windows: movela a una ruta más corta (por ejemplo C:\edits) y corré el instalador otra vez." -ForegroundColor Yellow
        throw "Falló: $shown (código $LASTEXITCODE)"
    }
    return $true
}

function Confirm-Step($question) {
    if ($Yes) { return $true }
    if ($DryRun) { Write-Note "[simulación] preguntaría: $question"; return $true }
    if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) {
        Write-Note "$question -> no se puede preguntar acá (sin teclado). Corré de nuevo con -Yes para aceptarlo."
        return $false
    }
    $answer = Read-Host "    $question [S/n]"
    return ($answer -eq '' -or $answer -match '^[sSyY]')
}

function Update-SessionPath {
    # winget cambia el PATH del usuario, pero esta ventana sigue con el viejo
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Test-Tool($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Get-PythonVersion($exe, $prefix) {
    # Devuelve [mayor, menor] o $null. El python.exe de la Tienda de Windows existe pero no corre: por eso se prueba.
    try {
        $all = @($prefix) + @('-c', 'import sys; print(sys.version_info[0], sys.version_info[1])') | Where-Object { $_ }
        $out = & $exe @all 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -match '^(\d+) (\d+)') { return @([int]$Matches[1], [int]$Matches[2]) }
    } catch {}
    return $null
}

function Find-Python {
    $candidates = @()
    if ($Python) { $candidates += , @($Python, '') }
    $candidates += , @('py', '-3')
    $candidates += , @('python', '')
    foreach ($c in $candidates) {
        if (-not (Test-Tool $c[0]) -and -not (Test-Path $c[0])) { continue }
        $v = Get-PythonVersion $c[0] $c[1]
        if ($v -and $v[0] -eq 3 -and $v[1] -ge $MinMinor) { return @{ Exe = $c[0]; Prefix = $c[1]; Version = "$($v[0]).$($v[1])" } }
    }
    return $null
}

function Install-WithWinget($id, $what) {
    if (-not (Test-Tool 'winget')) {
        Write-Note "No está winget (viene con Windows 10 y 11 actualizados). Instalá $what a mano y volvé a correr este archivo."
        return $false
    }
    return (Invoke-Step 'winget' @('install', '-e', '--id', $id, '--accept-source-agreements', '--accept-package-agreements') -Optional)
}

Write-Host 'Instalador (Windows)' -ForegroundColor Green
Write-Note "Carpeta: $Root"
Write-Note "Entorno virtual: $Venv"
if ($DryRun) { Write-Note 'SIMULACIÓN: no se instala ni se crea nada.' }

# ---------------------------------------------------------------- 1. Python
Write-Title 'Python'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
$py = Find-Python
if (-not $py -and -not (Test-Path $VenvPy)) {
    Write-Note "No encontré Python 3.$MinMinor o más nuevo."
    if (Confirm-Step '¿Instalo Python 3.13 con winget?') {
        [void](Install-WithWinget 'Python.Python.3.13' 'Python 3.13 (https://www.python.org/downloads/)')
        Update-SessionPath
        $py = Find-Python
    }
    if (-not $py -and -not $DryRun) {
        throw "Hace falta Python 3.$MinMinor o más nuevo. Instalalo (https://www.python.org/downloads/, tildando 'Add python.exe to PATH'), abrí una terminal nueva y corré este archivo otra vez."
    }
}
if ($py) { Write-Note "Python $($py.Version) ($($py.Exe) $($py.Prefix))" }

# ---------------------------------------------------------------- 2. entorno virtual y librerías
Write-Title 'Entorno virtual y librerías'
if (Test-Path $VenvPy) {
    Write-Note 'El entorno virtual ya existe: se reusa.'
} else {
    $pyExe = 'python'; $pyPrefix = @()
    if ($py) { $pyExe = $py.Exe; if ($py.Prefix) { $pyPrefix = @($py.Prefix) } }
    [void](Invoke-Step $pyExe ($pyPrefix + @('-m', 'venv', $Venv)))
}
[void](Invoke-Step $VenvPy @('-m', 'pip', 'install', '--upgrade', 'pip', '--disable-pip-version-check', '-q'))
[void](Invoke-Step $VenvPy @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', (Join-Path $Root 'requirements.txt')))

# ---------------------------------------------------------------- 3. ffmpeg
Write-Title 'ffmpeg'
if ((Test-Tool 'ffmpeg') -and (Test-Tool 'ffprobe')) {
    Write-Note 'ffmpeg ya está instalado.'
} else {
    Write-Note 'No encontré ffmpeg en el PATH (hace falta para leer los clips y codificar el video).'
    if (Confirm-Step '¿Instalo ffmpeg con winget (Gyan.FFmpeg, ~200 MB)?') {
        [void](Install-WithWinget 'Gyan.FFmpeg' 'ffmpeg (https://www.gyan.dev/ffmpeg/builds/)')
        Update-SessionPath
        if (-not $DryRun -and -not (Test-Tool 'ffmpeg')) {
            Write-Note 'ffmpeg se instaló pero esta ventana todavía no lo ve: abrí una terminal nueva y corré este archivo otra vez.'
        }
    } else {
        Write-Note 'Sin ffmpeg no se puede renderizar. Para instalarlo después: winget install -e --id Gyan.FFmpeg'
    }
}

# ---------------------------------------------------------------- 4. PyTorch y Demucs
if (-not $NoDemucs) {
    Write-Title 'PyTorch y Demucs (separa voz y música)'
    $nvidia = $false
    if (Test-Tool 'nvidia-smi') { & nvidia-smi -L *> $null; $nvidia = ($LASTEXITCODE -eq 0) }
    $torchState = ''
    if (Test-Path $VenvPy) {
        $torchState = & $VenvPy -c "import importlib.util as u; s = u.find_spec('torch'); print('no' if s is None else __import__('torch').__version__ + (' cuda' if __import__('torch').cuda.is_available() else ' cpu'))" 2>$null
    }
    if ($torchState -and $torchState -ne 'no' -and (-not $nvidia -or $torchState -match 'cuda')) {
        Write-Note "PyTorch ya está instalado ($torchState): se deja como está."
    } elseif ($nvidia) {
        Write-Note 'Placa NVIDIA detectada: PyTorch con CUDA (descarga ~2.5 GB).'
        [void](Invoke-Step $VenvPy @('-m', 'pip', 'install', '--disable-pip-version-check', "torch==$TorchVersion", '--index-url', $TorchIndex))
    } else {
        Write-Note 'Sin placa NVIDIA: PyTorch para CPU (con AMD e Intel en Windows, Demucs corre en el procesador).'
        # del índice de PyTorch y no de PyPI: es la variante probada (+cpu) y sus rutas de archivo son más cortas
        [void](Invoke-Step $VenvPy @('-m', 'pip', 'install', '--disable-pip-version-check', "torch==$TorchVersion", '--index-url', $TorchCpuIndex))
    }
    [void](Invoke-Step $VenvPy @('-m', 'pip', 'install', '--disable-pip-version-check', "demucs==$DemucsVersion"))
    Write-Note 'El modelo de Demucs (~80 MB) se baja solo la primera vez que se separa una canción.'
}

# ---------------------------------------------------------------- 5. extras
if ($Extras) {
    Write-Title "Extras: $Extras"
    foreach ($extra in ($Extras -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
        if ($DryRun -and -not (Test-Path $VenvPy)) { Write-Note "[simulación] instalaría el extra '$extra' de pyproject.toml"; continue }
        $code = "import sys, tomllib; d = tomllib.load(open(sys.argv[1], 'rb'))['project']['optional-dependencies']; print('\n'.join(d.get(sys.argv[2], [])))"
        $specs = @(& $VenvPy -c $code (Join-Path $Root 'pyproject.toml') $extra | Where-Object { $_ })
        if (-not $specs) { Write-Note "El extra '$extra' no existe en pyproject.toml: se saltea."; continue }
        [void](Invoke-Step $VenvPy (@('-m', 'pip', 'install', '--disable-pip-version-check') + $specs))
    }
}

# ---------------------------------------------------------------- 6. RIFE
if (-not $NoRife) {
    Write-Title 'RIFE (cámaras lentas en la placa)'
    $ok = Invoke-Step $VenvPy @((Join-Path $Root 'engine\setup_rife.py')) -Optional
    if (-not $ok) { Write-Note 'Sin RIFE las cámaras lentas se hacen con ffmpeg (más lento). Para reintentar: python engine\setup_rife.py' }
}

# ---------------------------------------------------------------- 7. diagnóstico
Write-Title 'Diagnóstico'
if ($DryRun) {
    Write-Note "[simulación] $VenvPy engine\doctor.py"
    Write-Host ''
    Write-Host 'Simulación terminada: no se cambió nada.' -ForegroundColor Green
    exit 0
}
& $VenvPy (Join-Path $Root 'engine\doctor.py')
$doctor = $LASTEXITCODE
Write-Host ''
if ($doctor -eq 0) {
    Write-Host 'Instalación lista.' -ForegroundColor Green
} else {
    Write-Host 'La instalación terminó, pero falta algo imprescindible: mirá las líneas [FALTA] de arriba.' -ForegroundColor Yellow
}
Write-Host 'Para usar el motor, activá el entorno en cada terminal nueva:'
Write-Host "    $(Join-Path $Venv 'Scripts\Activate.ps1')"
Write-Host 'y después, por ejemplo:  python engine\doctor.py'
exit $doctor
