@echo off
chcp 65001 > nul
title Systemize — Interactive Presentation (Hand Wave Controls)
color 0A

cd /d "%~dp0"

echo ===================================================================
echo   SYSTEMIZE — PRESENTATION DECK (EGYPTIAN ARABIC + HAND WAVE)
echo ===================================================================
echo.
echo [*] Opening presentation in your default web browser...
echo [*] Gesture Controls:
echo     - Wave your hand in front of webcam: Left <-> Right
echo     - Keyboard: Left / Right Arrows / Space / PageUp / PageDown
echo.

start "" "%~dp0index.html"
