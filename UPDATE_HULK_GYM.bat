@echo off
chcp 65001 >nul
title HULK GYM - فحص وتحديث النظام من GitHub
color 0b

cd /d "%~dp0"

echo ===================================================================
echo             HULK GYM - أداة تحديث النظام الذكية
echo        Smart GitHub Updater with Automatic Database Backup
echo ===================================================================
echo.

:: Detect Python environment
set PY_BIN=
if exist "%~dp0runtime\python.exe" set "PY_BIN=%~dp0runtime\python.exe"
if not defined PY_BIN if exist "%~dp0web_face\venv\Scripts\python.exe" set "PY_BIN=%~dp0web_face\venv\Scripts\python.exe"
if not defined PY_BIN if exist "C:\Program Files\Python311\python.exe" set "PY_BIN=C:\Program Files\Python311\python.exe"
if not defined PY_BIN set "PY_BIN=python"

:: Detect manage.py path
set MANAGE_DIR=
if exist "%~dp0web_face\manage.py" (
    set "MANAGE_DIR=%~dp0web_face"
) else if exist "%~dp0manage.py" (
    set "MANAGE_DIR=%~dp0"
)

if not defined MANAGE_DIR (
    echo [X] خطأ: لم يتم العثور على ملف manage.py في مسار النظام.
    echo Please make sure you are running this file from the HULK GYM root directory.
    pause
    exit /b 1
)

echo [*] جاري التحقق من وجود تحديثات على GitHub وعمل نسخة احتياطية آمنة...
echo.

pushd "%MANAGE_DIR%"
"%PY_BIN%" manage.py check_and_update
popd

echo.
echo ===================================================================
echo  تم الانتهاء من عملية الفحص والتحديث. يمكنك الآن متابعة العمل بالنظام.
echo ===================================================================
echo.
pause
