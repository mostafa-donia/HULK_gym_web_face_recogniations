@echo off
chcp 65001 > nul
title HULK GYM Web Enterprise Edition (Full Hardware & Integrations)
color 0B

echo =======================================================================
echo     HULK GYM - Web Enterprise Edition (Full Hardware & Integrations)
echo =======================================================================
echo.
echo [*] Checking database migrations...
cd /d "%~dp0web_full"
python manage.py migrate --no-input

echo [*] Starting Enterprise Web Server on port 8000...
echo [*] Local Address: http://localhost:8000/
echo [*] LAN Mobile / Tablet: http://192.168.0.101:8000/
echo.
echo [!] Features Active:
echo     - ESP32 Biometric Terminal & Turnstile Sync
echo     - Google Contacts People API Auto-Sync
echo     - POS Thermal 80mm/58mm Receipt Printing
echo     - Full Employee & Trainer Payroll
echo     - WhatsApp Queue & Auto Dispatcher
echo.
echo Press Ctrl+C in this window to stop the server.
echo =======================================================================
python manage.py runserver 0.0.0.0:8000
pause
