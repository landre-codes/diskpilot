@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" main.py
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

echo Python 3 nao encontrado.
pause
exit /b 1
