@echo off
chcp 65001 > nul
title Systemize - Interactive Sales Presentation
color 0A

cd /d "%~dp0"

echo ===================================================================
echo   SYSTEMIZE - INTERACTIVE SALES PRESENTATION
echo   [+] Hand Slide Navigation (Wave Next / Prev)
echo   [+] Zero Dependency Standalone Edition (Works on ANY Computer)
echo ===================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [*] Starting local presentation server via Python on port 8080...
    start "" "http://127.0.0.1:8080/index.html"
    python -m http.server 8080
) else (
    echo [*] Python not detected — Starting native Windows HTTP server on port 8080...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0server.ps1" -Port 8080 -Path "%~dp0"
)

if %ERRORLEVEL% NEQ 0 (
    echo [*] Falling back to direct browser launch...
    start "" "%~dp0index.html"
)
pause
