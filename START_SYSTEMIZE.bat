@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Systemize Gym OS - Standalone Portable
color 0A

cd /d "%~dp0"

echo ===================================================================
echo     SYSTEMIZE GYM OS - المنظومة الذكية لإدارة الصالات الرياضية
echo ===================================================================
echo.

if exist "runtime\python.exe" (
    set "PY_EXE=runtime\python.exe"
) else (
    set "PY_EXE=python"
)

echo [*] Checking database migrations...
"%PY_EXE%" -s manage.py migrate --noinput >nul 2>&1

echo [*] Checking Local Network Connection...
"%PY_EXE%" -s -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); ip=s.getsockname()[0]; s.close(); print(f'  [>] تشغيل اللابتوب الحالي:  http://127.0.0.1:8000\n  [>] تشغيل لابتوب ثاني أو موبايل: http://{ip}:8000\n===================================================================\n')" 2>nul

echo [*] Launching Systemize in default web browser...
start "" "http://127.0.0.1:8000"

echo [*] Starting Systemize Server (listening on 0.0.0.0:8000)...
"%PY_EXE%" -s manage.py runserver 0.0.0.0:8000
pause
