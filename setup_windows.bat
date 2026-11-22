@echo off
rem Lanzador del instalador de Windows: toda la logica esta en install.ps1 (acepta las mismas opciones, p. ej. -Yes).
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
