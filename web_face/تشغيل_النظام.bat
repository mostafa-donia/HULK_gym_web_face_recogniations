@echo off
chcp 65001 >nul
title HULK GYM - نظام إدارة الصالة وبوابة الوجه الذكية

cd /d "%~dp0"

echo ===================================================================
echo     HULK GYM MANAGEMENT SYSTEM - FACE RECOGNITION EDITION
echo ===================================================================
echo.

:: Detect Python executable in local venv or system
if exist "venv\Scripts\python.exe" (
    set "PY_EXE=venv\Scripts\python.exe"
    echo [*] استخدام البيئة الافتراضية venv المحلية...
) else if exist "..\venv\Scripts\python.exe" (
    set "PY_EXE=..\venv\Scripts\python.exe"
    echo [*] استخدام البيئة الافتراضية venv من المجلد الرئيسي...
) else (
    echo [!] لم يتم العثور على venv، جاري التحقق من بايثون المثبت على الجهاز...
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo [X] خطأ: بايثون غير مثبت على هذا الجهاز. يرجى تثبيت Python 3.10 أو 3.11 أولاً.
        pause
        exit /b 1
    )
    echo [*] جاري إعداد وتجهيز البيئة الافتراضية venv تلقائياً...
    python -m venv --system-site-packages venv
    set "PY_EXE=venv\Scripts\python.exe"
)

echo [*] فحص وتحديث جداول قاعدة البيانات...
"%PY_EXE%" manage.py migrate --noinput

echo.
echo [*] تم تجهيز النظام بنجاح!
echo [*] رابط النظام: http://127.0.0.1:8000
echo [*] جاري فتح المتصفح...
echo.

start http://127.0.0.1:8000

"%PY_EXE%" manage.py runserver 0.0.0.0:8000
pause
