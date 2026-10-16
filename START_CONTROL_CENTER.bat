@echo off
chcp 65001 > nul
title HULK GYM - Developer Command & Control Center
color 0B

cd /d "%~dp0"

echo ===================================================================
echo     HULK GYM — DEVELOPER COMMAND & CONTROL CENTER (PORT 9000)
echo ===================================================================
echo.

set PY_BIN=
if exist "web_face\venv\Scripts\python.exe" (
    set PY_BIN=web_face\venv\Scripts\python.exe
) else if exist "dist\HULK_GYM\runtime\python.exe" (
    set PY_BIN=dist\HULK_GYM\runtime\python.exe
) else (
    set PY_BIN=python
)

echo [*] Starting Developer Control Center server on http://127.0.0.1:9000 ...
timeout /t 2 /nobreak > nul
start http://127.0.0.1:9000

"%PY_BIN%" control_center\app.py
pause
