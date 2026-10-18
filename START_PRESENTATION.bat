@echo off
chcp 65001 >nul
title Systemize — Sales Presentation Launcher

cd /d "%~dp0"
call "presentation\RUN_PRESENTATION.bat"
