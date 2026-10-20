import os
import shutil
import sys

BASE_DIR = r"d:\move\career\gym system"
DIST_DIR = os.path.join(BASE_DIR, "dist")
CC_DIR = os.path.join(DIST_DIR, "ControlCenter")

print(f"[*] Assembling Standalone Control Center at: {CC_DIR}")

if os.path.exists(CC_DIR):
    shutil.rmtree(CC_DIR)
os.makedirs(CC_DIR, exist_ok=True)

# 1. Copy runtime from dist/Systemize/runtime
src_runtime = os.path.join(DIST_DIR, "Systemize", "runtime")
dst_runtime = os.path.join(CC_DIR, "runtime")
print("[*] Copying portable Python runtime...")
shutil.copytree(src_runtime, dst_runtime)

# 2. Copy control_center app files
src_cc = os.path.join(BASE_DIR, "control_center")
shutil.copy2(os.path.join(src_cc, "app.py"), os.path.join(CC_DIR, "app.py"))
shutil.copy2(os.path.join(src_cc, "clients.json"), os.path.join(CC_DIR, "clients.json"))
shutil.copytree(os.path.join(src_cc, "templates"), os.path.join(CC_DIR, "templates"))

# 3. Copy apps/core/licensing for standalone crypto & token generation
dst_licensing = os.path.join(CC_DIR, "apps", "core", "licensing")
os.makedirs(dst_licensing, exist_ok=True)
src_licensing = os.path.join(BASE_DIR, "web_face", "apps", "core", "licensing")
for fname in ["__init__.py", "crypto.py", "hwid.py"]:
    fpath = os.path.join(src_licensing, fname)
    if os.path.exists(fpath):
        shutil.copy2(fpath, os.path.join(dst_licensing, fname))

# Also create __init__.py in apps and apps/core
with open(os.path.join(CC_DIR, "apps", "__init__.py"), "w") as f:
    f.write("")
with open(os.path.join(CC_DIR, "apps", "core", "__init__.py"), "w") as f:
    f.write("")

# 4. Write portable START_CONTROL_CENTER.bat
bat_content = """@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Systemize - Central Control Center
color 0B

cd /d "%~dp0"

echo ===================================================================
echo     SYSTEMIZE — DEVELOPER COMMAND AND CONTROL CENTER
echo     Standalone Portable Edition (Zero Python / Zero SQL Needed)
echo ===================================================================
echo.

if exist "runtime\\python.exe" (
    set "PY_EXE=runtime\\python.exe"
) else (
    set "PY_EXE=python"
)

echo [*] Starting Central Control Server...
echo [*] The dashboard browser will open automatically when ready...
echo.

"%PY_EXE%" -s app.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo ===================================================================
    echo  [!] An error occurred while running the Control Center.
    echo ===================================================================
    pause
)
"""

with open(os.path.join(CC_DIR, "START_CONTROL_CENTER.bat"), "w", encoding="utf-8") as f:
    f.write(bat_content)

print("[V] Standalone Control Center assembled successfully!")
