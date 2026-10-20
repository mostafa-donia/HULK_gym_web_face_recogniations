@echo off
chcp 65001 > nul
title Systemize Gym OS - إنشاء اختصار سطح المكتب باللوجو
color 0B

cd /d "%~dp0"

echo ===================================================================
echo   معالج إنشاء اختصار سطح المكتب وتطبيق لوجو الصالة كأيقونة
echo ===================================================================
echo.
echo  يمكنك سحب وإفلات صورة اللوجو (PNG أو JPG) في هذه الشاشة
echo  ليتم تحويلها تلقائياً إلى أيقونة Windows Icon ووضع اختصار للجيم على سطح المكتب.
echo.
echo  (إذا كنت قد وضعت اللوجو سابقاً أو يوجد ملف logo.png في المجلد، اضغط Enter مباشرة)
echo ===================================================================
echo.

set /p LOGO_INPUT="اسحب ملف اللوجو هنا ثم اضغط Enter (أو اضغط Enter للافتراضي): "

if exist "runtime\python.exe" (
    set "PY_EXE=runtime\python.exe"
) else if exist "dist\Systemize\runtime\python.exe" (
    set "PY_EXE=dist\Systemize\runtime\python.exe"
) else (
    set "PY_EXE=python"
)

echo.
echo [*] جارٍ تجهيز الأيقونة وإنشاء اختصار سطح المكتب...
"%PY_EXE%" -s make_shortcut.py "%LOGO_INPUT%"

echo.
pause
