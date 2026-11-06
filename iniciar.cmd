@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" main.py
    exit /b %errorlevel%
)

py -3.14 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3.14 main.py
    exit /b %errorlevel%
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 main.py
    exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
    exit /b %errorlevel%
)

echo.
echo Python 3 nao foi encontrado neste computador.
echo Instale o Python 3.10 ou superior e tente novamente.
echo Em ambiente offline, use o pacote DiskPilot-offline e o instalar_offline.cmd.
echo.
pause
exit /b 1
