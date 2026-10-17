@echo off
chcp 65001 > nul
title Systemize - GitHub System Updater
color 0b

echo ========================================================
echo         SYSTEMIZE - GitHub System Updater
echo ========================================================
echo.

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
) else (
    set "PY_EXE=python"
    set "APP_DIR=%~dp0web_face"
)

cd /d "%APP_DIR%"

echo [*] Checking for updates and performing automatic backup...
"%PY_EXE%" manage.py check_and_update

echo.
pause
