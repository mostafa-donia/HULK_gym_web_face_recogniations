@echo off
chcp 65001 >nul
title Systemize — Sales Presentation Runner

echo ========================================================
echo       Systemize Interactive Gym Sales Presentation
echo ========================================================
echo.
echo [1/2] جار تشغيل سيرفر العرض المحلي (Local Server)...
echo       يضمن هذا تشغيل الكاميرا وإشارات اليد (Pinch & Wave)
echo       بأعلى أداء وبدون أي قيود أمان للمتصفح.
echo.

cd /d "%~dp0\.."

start "" http://localhost:8080/presentation/

echo [2/2] السيرفر يعمل الآن على الرابط: http://localhost:8080/presentation/
echo.
echo ملاحظة: اضغط مفتاح Z للتكبير الفوري، أو استخدم إشارة Pinch 🤏 بالأيدي.
echo اترك هذه النافذة مفتوحة طوال فترة العرض.
echo ========================================================
python -m http.server 8080
pause
