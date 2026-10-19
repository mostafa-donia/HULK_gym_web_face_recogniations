@echo off
chcp 65001 > nul
title Systemize - Smart Gym Management System
color 0A

echo ========================================================
echo          SYSTEMIZE - Smart Management System
echo ========================================================
echo.

:: Detect Python executable and application directory
if exist "%~dp0dist\Systemize\runtime\python.exe" (
    set "PY_EXE=%~dp0dist\Systemize\runtime\python.exe"
    set "APP_DIR=%~dp0dist\Systemize"
) else if exist "%~dp0dist\gym system\runtime\python.exe" (
    set "PY_EXE=%~dp0dist\gym system\runtime\python.exe"
    set "APP_DIR=%~dp0dist\gym system"
) else if exist "%~dp0dist\HULK_GYM\runtime\python.exe" (
    set "PY_EXE=%~dp0dist\HULK_GYM\runtime\python.exe"
    set "APP_DIR=%~dp0dist\HULK_GYM"
) else if exist "%~dp0web_face\venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0web_face\venv\Scripts\python.exe"
    set "APP_DIR=%~dp0web_face"
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0venv\Scripts\python.exe"
    set "APP_DIR=%~dp0web_face"
) else (
    set "PY_EXE=python"
    set "APP_DIR=%~dp0web_face"
)

cd /d "%APP_DIR%"

echo [*] Checking database migrations...
"%PY_EXE%" manage.py migrate --no-input

echo.
echo.
echo [*] Launching Systemize in default web browser...
start "" "http://127.0.0.1:8000/"

echo.
echo ========================================================
echo  System is running. Press Ctrl+C to stop the server.
echo ========================================================
"%PY_EXE%" manage.py runserver 0.0.0.0:8000
pause
