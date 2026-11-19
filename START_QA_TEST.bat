@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Systemize QA Terminal - معمل فحص واختبار المنظومة
color 0B

cd /d "%~dp0"

if not exist "web_face\manage.py" (
    if exist "manage.py" (
        cd /d "%~dp0"
    ) else if exist "d:\move\career\gym system\web_face\manage.py" (
        cd /d "d:\move\career\gym system\web_face"
    )
) else (
    cd /d "%~dp0web_face"
)

echo ===================================================================
echo     SYSTEMIZE QA TERMINAL // CLIENT HANDOVER SUITE
echo     معمل فحص الجاهزية الشاملة واختبار كافة الصفحات والأزرار
echo ===================================================================
echo.

if exist "runtime\python.exe" (
    set "PY_EXE=runtime\python.exe"
) else if exist "..\dist\Systemize\runtime\python.exe" (
    set "PY_EXE=..\dist\Systemize\runtime\python.exe"
) else (
    set "PY_EXE=python"
)

rem 1. Check if server is already running on port 8000
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [*] المنظومة تعمل بالفعل على المنفذ 8000.
    echo [*] جارٍ فتح معمل الفحص والاختبار في المتصفح...
    start "" "http://127.0.0.1:8000/qa/"
    ping 127.0.0.1 -n 3 >nul
    exit /b 0
)

rem 2. If server is not running, run migrations and start server
echo [*] فحص ترحيلات قاعدة البيانات...
"%PY_EXE%" manage.py migrate --noinput >nul 2>&1

echo [*] جارٍ تشغيل معمل الفحص في المتصفح...
start "" "http://127.0.0.1:8000/qa/"

echo.
echo [*] بدء تشغيل خادم المنظومة - Listening on 0.0.0.0:8000...
echo [*] تنبيه: اترك هذه النافذة مفتوحة أثناء الفحص والاستخدام.
echo ===================================================================
echo.
"%PY_EXE%" manage.py runserver 0.0.0.0:8000

if %ERRORLEVEL% neq 0 (
    echo.
    echo ===================================================================
    echo  [!] حدث خطأ أثناء تشغيل الخادم - Exit Code: %ERRORLEVEL%
    echo ===================================================================
    pause
)
