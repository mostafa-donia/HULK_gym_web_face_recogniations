@echo off
chcp 65001 > nul
title Systemize Gym OS - Clear All Data
color 0C

cd /d "%~dp0"

echo ===================================================================
echo   SYSTEMIZE GYM OS - مسح وتصفير كافة البيانات (CLEAR ALL DATA)
echo ===================================================================
echo.
echo  [!] تحذير هام جداً:
echo  هذا الإجراء سيقوم بحذف كافة سجلات الأعضاء والاشتراكات والمدفوعات
echo  ومبيعات البار والمصروفات والرواتب، للبدء بقاعدة بيانات فارغة ونظيفة.
echo.
echo  بيانات الدخول الافتراضية بعد المسح:
echo    - admin / 1234
echo    - demo / 1234
echo    - manager / 1234
echo    - reception / 1234
echo ===================================================================
echo.

set /p CONFIRM="هل أنت متأكد تماماً من رغبتك في مسح كافة البيانات والبدء على نظيف؟ (اكتب Y للتأكيد): "
if /i not "%CONFIRM%"=="Y" (
    echo.
    echo [i] تم إلغاء العملية، لم يتم حذف أي بيانات.
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

echo.
echo [*] جارٍ تصفير قاعدة البيانات ومسح السجلات...
"%PY_EXE%" manage.py reset_clean_database

echo.
echo ===================================================================
echo  [V] تم تصفير كافة البيانات بنجاح! النظام الآن نظيف وفارغ تماماً.
echo ===================================================================
echo.
pause
