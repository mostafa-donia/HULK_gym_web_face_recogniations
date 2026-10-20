@echo off
chcp 65001 > nul
title Systemize Gym OS - تفعيل اتصال اللابتوب الثاني
color 0A

:: Check for Administrator elevation
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [*] جاري طلب صلاحيات المسؤول (Administrator) لفتح المنفذ 8000 في جدار الحماية...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo ===================================================================
echo   تفعيل جدار الحماية للاتصال من لابتوب ثاني أو موبايل - SYSTEMIZE
echo ===================================================================
echo.
echo [*] جاري فتح المنفذ 8000 في جدار حماية ويندوز (Windows Firewall)...

netsh advfirewall firewall add rule name="Systemize Gym OS (Port 8000)" dir=in action=allow protocol=TCP localport=8000 profile=any >nul 2>&1

if exist "runtime\python.exe" (
    set "PY_EXE=runtime\python.exe"
) else if exist "dist\Systemize\runtime\python.exe" (
    set "PY_EXE=dist\Systemize\runtime\python.exe"
) else (
    set "PY_EXE=python"
)

echo.
"%PY_EXE%" -s show_network_ip.py

echo.
pause
