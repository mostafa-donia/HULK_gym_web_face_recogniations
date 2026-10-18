@echo off
title Systemize - Interactive Presentation (Hand Wave Slide Navigation)
color 0A

cd /d "%~dp0"

echo ===================================================================
echo   SYSTEMIZE - INTERACTIVE SALES PRESENTATION
echo   [+] Hand Slide Navigation (Next / Prev)
echo   [+] Presenter Prompter (N) and Loss Calculator
echo   [+] High Performance Local Server
echo ===================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [*] Starting local presentation server for webcam and AI gestures...
    start /b python -m http.server 8420 --directory "%~dp0" >nul 2>nul
    ping 127.0.0.1 -n 2 >nul
    start "" "http://localhost:8420/index.html"
) else (
    echo [*] Opening presentation directly in default browser...
    start "" "%~dp0index.html"
)

echo.
echo [*] Presentation is running!
echo [*] Controls:
echo     - Hand Gestures: Wave hand right for Next, left for Previous
echo     - Keyboard: Arrows (Navigate), Space (Next), N (Presenter Prompter)
echo.
