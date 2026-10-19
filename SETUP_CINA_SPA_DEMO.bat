@echo off
chcp 65001 > nul
title Cina Spa - Demo Setup & Activation
color 0C

cd /d "%~dp0"

echo ===================================================================
echo   CINA SPA - DEMO SETUP & ACTIVATION (RUBY RED THEME)
echo   Logo: Cina Spa Emblem Circular Cutout
echo   Branches: 1. الفرع الرئيسي   2. النادي الصحي والاستشفاء   3. فرع السيدات
echo ===================================================================
echo.

if exist "runtime\python.exe" (
    set "PY_EXE=runtime\python.exe"
) else if exist "dist\Systemize\runtime\python.exe" (
    set "PY_EXE=dist\Systemize\runtime\python.exe"
) else (
    set "PY_EXE=python"
)

echo [*] Applying Cina Spa branding, logo, and branches...
"%PY_EXE%" manage.py seed_cina_spa_demo

echo.
echo ===================================================================
echo  [V] Cina Spa Demo applied successfully! You can now start Systemize.
echo ===================================================================
echo.
pause
