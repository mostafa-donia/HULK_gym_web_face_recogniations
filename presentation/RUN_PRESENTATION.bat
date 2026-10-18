@echo off
title Systemize - Interactive Sales Presentation
color 0A

cd /d "%~dp0"

echo ========================================================
echo   SYSTEMIZE GYM OS - SALES PRESENTATION
echo ========================================================
echo.
echo [*] Starting local presentation server...
echo [*] Opening presentation in your default browser...
echo.

start "" "http://localhost:8080/index.html"

echo [*] Presentation URL:  http://localhost:8080/index.html
echo [*] Speaker Notes URL: http://localhost:8080/speaker_notes.html
echo [*] Hand gestures (Pinch and Wave) are active on presentation screen.
echo [*] Press [Z] on presentation to Zoom / Inspect details.
echo.
echo Keep this window open during your presentation.
echo ========================================================
echo.
python -m http.server 8080
pause
