@echo off
chcp 65001 > nul
title HULK GYM Web Management System
color 0A

echo ========================================================
echo          HULK GYM - Web Management System
echo ========================================================
echo.
cd /d "%~dp0"
python manage.py migrate --no-input

echo [*] Starting LAN server on 0.0.0.0:8000...
echo [*] Local: http://localhost:8000/
echo [*] LAN:   http://192.168.0.101:8000/
echo.
python manage.py runserver 0.0.0.0:8000
pause
