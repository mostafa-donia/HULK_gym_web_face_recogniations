@echo off
chcp 65001 > nul
title HULK GYM Web Management System
color 0A

echo ========================================================
echo          HULK GYM - Web Management System
echo ========================================================
echo.
echo [*] Checking database migrations...
cd /d "%~dp0web"
python manage.py migrate --no-input

echo [*] Starting local LAN web server on port 8000...
echo [*] Accessible locally at: http://localhost:8000/
echo [*] Accessible from gym phones / tablets at: http://192.168.0.101:8000/
echo.
echo Press Ctrl+C in this window to stop the server.
echo ========================================================
python manage.py runserver 0.0.0.0:8000
pause
