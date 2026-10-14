@echo off
chcp 65001 > nul
title HULK GYM - Background Automation Daemon
color 0E

echo =======================================================================
echo          HULK GYM - Background Automation & Polling Worker
echo =======================================================================
echo.
echo [*] Starting continuous tasks:
echo     - ESP32 Turnstile Scan Polling & Entry Processing (every 5s)
echo     - Outgoing WhatsApp Queue Dispatcher
echo     - Daily Expiry Notifications at configured time
echo.
cd /d "%~dp0web_full"
python manage.py run_automations --interval 5
pause
