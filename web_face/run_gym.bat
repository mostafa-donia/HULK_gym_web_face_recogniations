@echo off
chcp 65001 >nul
title HULK GYM - Smart Gym Management System

cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    set "PY_EXE=venv\Scripts\python.exe"
) else if exist "..\venv\Scripts\python.exe" (
    set "PY_EXE=..\venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo [X] Python is not installed on this computer. Please install Python 3.10 or 3.11.
        pause
        exit /b 1
    )
    python -m venv --system-site-packages venv
    set "PY_EXE=venv\Scripts\python.exe"
)

"%PY_EXE%" manage.py migrate --noinput
start http://127.0.0.1:8000
"%PY_EXE%" manage.py runserver 0.0.0.0:8000
pause
