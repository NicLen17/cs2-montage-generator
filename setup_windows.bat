@echo off
chcp 65001 >nul
echo === Instalando Python y ffmpeg (winget) ===
where python >nul 2>nul || winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
where ffmpeg >nul 2>nul || winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
echo.
echo === Librerias de Python ===
python -m pip install --upgrade pip
python -m pip install -r "%~dp0requirements.txt"
echo.
echo === Demucs (separa voz y musica; descarga ~2 GB la primera vez) ===
python -m pip install demucs
echo.
echo === Prueba de codificadores (deberia decir amf) ===
python "%~dp0engine\encoders.py"
echo.
echo Si "python" o "ffmpeg" no se encuentran, cerra esta ventana, abri una nueva y volve a ejecutar este archivo.
pause
