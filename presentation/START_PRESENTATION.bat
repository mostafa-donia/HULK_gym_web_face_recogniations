@echo off
chcp 65001 > nul
title Systemize — Interactive Presentation (Hand Wave + 4-Finger L-Shape Zoom)
color 0A

cd /d "%~dp0"

echo ===================================================================
echo   SYSTEMIZE — INTERACTIVE SALES PRESENTATION
echo   [+] 4-Finger L-Shape Framing Zoom & Pan
echo   [+] Hand Wave Slide Switching
echo   [+] Presenter Prompter (N) & Loss Calculator
echo ===================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [*] Starting local presentation server for webcam & AI gestures...
    start /b python -m http.server 8420 --directory "%~dp0" >nul 2>nul
    timeout /t 1 >nul
    start "" "http://localhost:8420/index.html"
) else (
    echo [*] Opening presentation directly in default browser...
    start "" "%~dp0index.html"
)

echo.
echo [*] Presentation is running!
echo [*] Controls:
echo     - 4-Finger L-Shape: 2 Index + 2 Thumbs up to Zoom & Pan
echo     - Lower fingers: Smoothly return to normal slide
echo     - Wave hand: Left/Right to flip slides
echo     - Keyboard: Arrows (Navigate), Z (Zoom), N (Presenter Prompter)
echo.
