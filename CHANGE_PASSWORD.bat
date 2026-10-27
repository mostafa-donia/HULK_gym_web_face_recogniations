@echo off
chcp 65001 > nul
title Systemize Gym OS - Change User Password
color 0B

cd /d "%~dp0"

echo ===================================================================
echo   SYSTEMIZE GYM OS - CHANGE USER PASSWORD TOOL
echo ===================================================================
echo.
echo المستخدمون الأساسيون:
echo   - manager    (المالك / مدير الصالة)
echo   - reception  (موظف الاستقبال)
echo ===================================================================
echo.

set /p USERNAME="اسم المستخدم (Username) [افتراضي manager]: "
if "%USERNAME%"=="" set USERNAME=manager

set /p NEWPASS="كلمة المرور الجديدة (New Password): "
if "%NEWPASS%"=="" (
    echo [X] لم يتم إدخال كلمة مرور جديدة. تم الإلغاء.
    pause
    exit /b
)

if exist "runtime\python.exe" (
    set "PY_EXE=runtime\python.exe"
) else if exist "dist\Systemize\runtime\python.exe" (
    set "PY_EXE=dist\Systemize\runtime\python.exe"
) else (
    set "PY_EXE=python"
)

"%PY_EXE%" -s -c "import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); django.setup(); from apps.accounts.models import User; u = User.objects.filter(username='%USERNAME%').first(); (u.set_password('%NEWPASS%'), u.save(), print('SUCCESS')) if u else print('NOT_FOUND')" > "%TEMP%\pw_res.txt"

findstr /C:"SUCCESS" "%TEMP%\pw_res.txt" > nul
if %errorlevel% equ 0 (
    echo.
    echo ===================================================================
    echo  [V] تم تغيير كلمة المرور للمستخدم '%USERNAME%' بنجاح!
    echo ===================================================================
) else (
    echo.
    echo [X] لم يتم العثور على مستخدم بهذا الاسم: '%USERNAME%'
)

if exist "%TEMP%\pw_res.txt" del "%TEMP%\pw_res.txt"
echo.
pause
