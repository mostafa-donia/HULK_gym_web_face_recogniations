@echo off
chcp 65001 >nul
title HULK GYM - Standalone Dist Generator

cd /d "%~dp0"

echo ===================================================================
echo     HULK GYM - GENERATING STANDALONE PORTABLE DISTRIBUTION
echo ===================================================================
echo.
echo [*] This script builds the self-contained 'dist\HULK_GYM' package.
echo [*] The client's laptop will NOT need Python or any installation.
echo.

if exist "web_face\venv\Scripts\python.exe" (
    "web_face\venv\Scripts\python.exe" build_dist.py
) else (
    python build_dist.py
)

echo.
pause
