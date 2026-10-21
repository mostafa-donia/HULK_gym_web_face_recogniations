@echo off
chcp 65001 > nul
title Systemize - حاسبة الأسعار والعروض التفاعلية
color 0B

cd /d "%~dp0"

echo ===================================================================
echo     SYSTEMIZE GYM OS - حاسبة الأسعار وباقات الصالات الرياضية
echo ===================================================================
echo.
echo [*] جارٍ فتح حاسبة الأسعار التفاعلية في المتصفح...

if exist "SYSTEMIZE_PRICING_CALCULATOR.html" (
    start "" "SYSTEMIZE_PRICING_CALCULATOR.html"
) else if exist "PRICING_CALCULATOR.html" (
    start "" "PRICING_CALCULATOR.html"
) else (
    start "" "presentation\pricing_calculator.html"
)

exit /b
