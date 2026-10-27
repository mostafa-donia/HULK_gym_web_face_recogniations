@echo off
chcp 65001 > nul
title Systemize Gym OS - Reset Clean Database
color 0E

cd /d "%~dp0"

echo ===================================================================
echo   SYSTEMIZE GYM OS - RESET DATABASE TO ZERO-DATA CLEAN VERSION
echo ===================================================================
echo.
echo  [!] تحذير هام جداً:
echo  هذا الإجراء سيقوم بمسح كافة الأعضاء والاشتراكات والمدفوعات والمبيعات
echo  وإعادة النظام إلى نسخة فارغة وجديدة تماماً وجاهزة لبيانات الجيم الفعلي.
echo  مع الحفاظ على إعدادات الصالة وحسابات تسجيل الدخول الحالية.
echo ===================================================================
echo.

set /p CONFIRM="هل أنت متأكد من رغبتك في تصفير قاعدة البيانات والبدء بنسخة نظيفة؟ (اكتب Y للمتابعة): "
if /i not "%CONFIRM%"=="Y" (
    echo.
    echo تم إلغاء العملية، لم يتم حذف أي بيانات.
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
echo [*] جارٍ تصفير قاعدة البيانات وتجهيز النسخة الفارغة...
"%PY_EXE%" manage.py reset_clean_database

echo.
echo ===================================================================
echo  [V] تم تصفير قاعدة البيانات بنجاح! النظام الآن فارغ وجاهز للتشغيل.
echo ===================================================================
echo.
pause
