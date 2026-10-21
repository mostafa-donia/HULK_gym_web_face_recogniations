@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Systemize Gym OS - Standalone Portable
color 0A

cd /d "%~dp0"

if not exist "manage.py" (
    if exist "web_face\manage.py" (
        cd /d "%~dp0web_face"
    )
)

echo ===================================================================
echo     SYSTEMIZE GYM OS - المنظومة الذكية لإدارة الصالات الرياضية
echo ===================================================================
echo.

if exist "runtime\python.exe" (
    set "PY_EXE=runtime\python.exe"
) else if exist "..\dist\Systemize\runtime\python.exe" (
    set "PY_EXE=..\dist\Systemize\runtime\python.exe"
) else (
    set "PY_EXE=python"
)

echo [*] Checking database migrations...
"%PY_EXE%" -s manage.py migrate --noinput >nul 2>&1

echo [*] Checking Local Network Connection...
if exist "show_network_ip.py" (
    "%PY_EXE%" -s show_network_ip.py
) else if exist "..\dist\Systemize\show_network_ip.py" (
    "%PY_EXE%" -s "..\dist\Systemize\show_network_ip.py"
) else (
    echo   [>] الرابط المحلي:  http://127.0.0.1:8000
)

echo.
echo [*] Launching Systemize in default web browser...
start "" "http://127.0.0.1:8000"

echo.
echo [*] Starting Systemize Server (listening on 0.0.0.0:8000)...
echo [*] Note: Keep this window open while using Systemize.
echo ===================================================================
echo.
"%PY_EXE%" -s manage.py runserver 0.0.0.0:8000

if %ERRORLEVEL% neq 0 (
    echo.
    echo ===================================================================
    echo  [!] Systemize Server encountered an issue (Exit Code: %ERRORLEVEL%).
    echo ===================================================================
    pause
)
