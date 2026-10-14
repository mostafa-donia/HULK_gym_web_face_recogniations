@echo off
chcp 65001 > nul
title HULK GYM Web Management System
color 0A

echo ========================================================
echo          HULK GYM - Web Management System
echo ========================================================
echo.
cd /d "%~dp0web_face"

if exist "venv\Scripts\python.exe" (
    set "PY_EXE=venv\Scripts\python.exe"
) else if exist "..\venv\Scripts\python.exe" (
    set "PY_EXE=..\venv\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

echo [*] Launching HULK GYM interface...
if exist "%~dp0startup.html" (
    start "" "%~dp0startup.html"
) else if exist "%~dp0web_face\startup.html" (
    start "" "%~dp0web_face\startup.html"
) else (
    start http://127.0.0.1:8000
)

echo [*] Checking database migrations...
"%PY_EXE%" manage.py migrate --no-input

echo [*] Starting local LAN web server on port 8000...
echo [*] Accessible locally at: http://127.0.0.1:8000/
echo.
echo Press Ctrl+C in this window to stop the server.
echo ========================================================
"%PY_EXE%" manage.py runserver 0.0.0.0:8000
pause
