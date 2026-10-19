@echo off
chcp 65001 > nul
title Number One Gym - Demo Setup & Activation
color 0E

cd /d "%~dp0"

echo ===================================================================
echo   NUMBER ONE GYM - DEMO SETUP & ACTIVATION (GOLD YELLOW THEME)
echo   Branches: 1. شكري القوتلي   2. الزراعة   3. الشعبية
echo ===================================================================
echo.

if exist "runtime\python.exe" (
    set "PY_EXE=runtime\python.exe"
) else if exist "dist\Systemize\runtime\python.exe" (
    set "PY_EXE=dist\Systemize\runtime\python.exe"
) else (
    set "PY_EXE=python"
)

echo [*] Applying Number One Gym branding, logo, and 3 branches...
"%PY_EXE%" manage.py seed_number_one_demo

echo.
echo ===================================================================
echo  [V] Setup completed successfully! You can now start Systemize.
echo ===================================================================
echo.
pause
