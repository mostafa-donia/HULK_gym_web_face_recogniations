@echo off
chcp 65001 > nul
title Systemize Gym OS - معالج إعداد صالة جديدة
color 0B

cd /d "%~dp0"

echo ===================================================================
echo     معالج إعداد وتهيئة صالة رياضية جديدة - SYSTEMIZE GYM OS
echo ===================================================================
echo.
echo  سيرشدك هذا المعالج لإعداد جيم جديد بالكامل:
echo  - الاسم والهوية
echo  - الشعار (Logo)
echo  - ألوان الثيم (Theme Colors)
echo  - الفروع المتعددة
echo.
echo ===================================================================
echo.

set /p GYM_NAME="1. أدخل اسم الصالة الرياضية (مثال: Number One Gym): "
if "%GYM_NAME%"=="" set "GYM_NAME=Systemize Gym & Fitness"

set /p GYM_TAGLINE="2. أدخل شعار / وصف الصالة (اتركه فارغاً للافتراضي): "

set /p LOGO_PATH="3. أدخل مسار ملف صورة الشعار (اسحب الملف وأفلته هنا أو اكتب المسار): "

echo.
echo خيارات الألوان الشائعة:
echo   - ذهبي / أصفر (Number One): #F59E0B أو #EAB308
echo   - أحمر سبا / فيتنس (Cina Spa): #E11D48
echo   - أخضر نيون رياضي: #84CC16
echo   - أزرق ملكي عصري: #38BDF8
echo.
set /p THEME_COLOR="4. أدخل كود لون الثيم الأساسي Hex (مثال: #F59E0B أو اتركه فارغاً): "
if "%THEME_COLOR%"=="" set "THEME_COLOR=#84CC16"

set /p ACCENT_COLOR="5. أدخل كود اللون الثانوي Hex (اتركه فارغاً لاستخدام نفس الأساسي): "
if "%ACCENT_COLOR%"=="" set "ACCENT_COLOR=%THEME_COLOR%"

set /p BRANCHES="6. أدخل أسماء الفروع مفصولة بفاصلة (مثال: شكري القوتلي, الزراعة, الشعبية): "
if "%BRANCHES%"=="" set "BRANCHES=الفرع الرئيسي"

set /p CLEAR_DATA="7. هل تريد مسح بيانات الأعضاء والاشتراكات القديمة للبدء على نظيف؟ (Y/N): "

echo.
echo ===================================================================
echo  إعداد بيانات تسجيل الدخول والأمان (Security & Credentials):
echo ===================================================================
set /p ADMIN_USER="8. اسم مستخدم المدير / المالك (Username) [اضغط Enter لـ: manager]: "
if "%ADMIN_USER%"=="" set "ADMIN_USER=manager"

:ASK_ADMIN_PASS
set /p ADMIN_PASS="9. كلمة مرور حساب المدير (Password) [مطلوبة - لا يمكن تركها فارغة]: "
if "%ADMIN_PASS%"=="" (
    echo [!] يجب إدخال كلمة مرور لحساب المدير لحماية المنظومة!
    goto ASK_ADMIN_PASS
)

set /p RECEPTION_USER="10. اسم مستخدم موظف الاستقبال (Reception Username) [اضغط Enter لـ: reception]: "
if "%RECEPTION_USER%"=="" set "RECEPTION_USER=reception"

set /p RECEPTION_PASS="11. كلمة مرور موظف الاستقبال (اتركها فارغة لاستخدام نفس كلمة مرور المدير): "
if "%RECEPTION_PASS%"=="" set "RECEPTION_PASS=%ADMIN_PASS%"

if exist "runtime\python.exe" (
    set "PY_EXE=runtime\python.exe"
) else if exist "dist\Systemize\runtime\python.exe" (
    set "PY_EXE=dist\Systemize\runtime\python.exe"
) else (
    set "PY_EXE=python"
)

set "CLEAR_ARG="
if /i "%CLEAR_DATA%"=="Y" (
    set "CLEAR_ARG=--clear-data"
)

set "LOGO_ARG="
if not "%LOGO_PATH%"=="" (
    set LOGO_ARG=--logo "%LOGO_PATH%"
)

set "TAGLINE_ARG="
if not "%GYM_TAGLINE%"=="" (
    set TAGLINE_ARG=--tagline "%GYM_TAGLINE%"
)

echo.
echo [*] جارٍ تطبيق الإعدادات وتجهيز قاعدة البيانات للصالة الجديدة...
"%PY_EXE%" manage.py setup_custom_gym --name "%GYM_NAME%" %TAGLINE_ARG% %LOGO_ARG% --color "%THEME_COLOR%" --accent "%ACCENT_COLOR%" --branches "%BRANCHES%" --admin-user "%ADMIN_USER%" --admin-pass "%ADMIN_PASS%" --reception-user "%RECEPTION_USER%" --reception-pass "%RECEPTION_PASS%" %CLEAR_ARG%

echo.
echo ===================================================================
echo  [V] تم إعداد الصالة بنجاح! يمكنك الآن بدء تشغيل النظام بـ START_SYSTEMIZE.bat
echo ===================================================================
echo.
pause
