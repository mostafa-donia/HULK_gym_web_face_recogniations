@echo off
chcp 65001 >nul
title Systemize — WhatsApp Pro Bulk Sender & Scheduler

echo =====================================================================
echo           Systemize - WhatsApp Pro Bulk Sender ^& Scheduler
echo =====================================================================
echo.

cd /d "%~dp0"

:: 1. Check for bundled runtime in parent or local dir
if exist "..\dist\Systemize\runtime\python.exe" (
    set "PY_EXE=..\dist\Systemize\runtime\python.exe"
    goto RUN
)

if exist "..\Systemize\runtime\python.exe" (
    set "PY_EXE=..\Systemize\runtime\python.exe"
    goto RUN
)

if exist "runtime\python.exe" (
    set "PY_EXE=runtime\python.exe"
    goto RUN
)

:: 2. Check for system Python
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PY_EXE=python"
    goto RUN
)

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PY_EXE=py"
    goto RUN
)

echo [!] Error: Python not found on your system!
echo     Please install Python 3.10+ or run with Systemize runtime.
echo.
pause
exit /b 1

:RUN
echo [*] Starting Systemize WhatsApp Pro...
echo [*] Runtime: %PY_EXE%
echo.

"%PY_EXE%" main.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] Application exited with error code %ERRORLEVEL%.
    pause
)
