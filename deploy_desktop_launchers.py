import os
import sys
import base64
import subprocess

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
system_bat = os.path.join(BASE_DIR, "START_SYSTEMIZE.bat")
test_bat = os.path.join(BASE_DIR, "START_QA_TEST.bat")
ico_path = os.path.join(BASE_DIR, "gym_icon.ico")

# Detect all valid Desktop paths
desktops = []
for p in [
    os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\Admin"), "Desktop"),
    "D:\\Desktop",
    "C:\\Users\\Admin\\Desktop"
]:
    if os.path.isdir(p) and p not in desktops:
        desktops.append(p)

print(f"[*] Found {len(desktops)} Desktop locations: {desktops}")

# 1. Content for Desktop RUN_SYSTEM.bat
run_system_bat_content = f"""@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Systemize Gym OS - تشغيل المنظومة
color 0A

set "PROJECT_DIR={BASE_DIR}"

if exist "%PROJECT_DIR%\\START_SYSTEMIZE.bat" (
    cd /d "%PROJECT_DIR%"
    call "%PROJECT_DIR%\\START_SYSTEMIZE.bat"
) else (
    echo [!] Project directory not found: %PROJECT_DIR%
    pause
)
"""

# 2. Content for Desktop RUN_TEST_WEBSITE.bat
run_test_bat_content = f"""@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Systemize QA Terminal - معمل فحص واختبار المنظومة
color 0B

set "PROJECT_DIR={BASE_DIR}"

if exist "%PROJECT_DIR%\\START_QA_TEST.bat" (
    cd /d "%PROJECT_DIR%"
    call "%PROJECT_DIR%\\START_QA_TEST.bat"
) else (
    echo [!] Project directory not found: %PROJECT_DIR%
    pause
)
"""

# Write batch files directly to all desktop folders
for d in desktops:
    # 1. RUN_SYSTEM.bat
    p_sys = os.path.join(d, "RUN_SYSTEM.bat")
    with open(p_sys, "w", encoding="utf-8") as f:
        f.write(run_system_bat_content)
    print(f"[V] Created Desktop BAT: {p_sys}")

    # 2. RUN_TEST_WEBSITE.bat
    p_test = os.path.join(d, "RUN_TEST_WEBSITE.bat")
    with open(p_test, "w", encoding="utf-8") as f:
        f.write(run_test_bat_content)
    print(f"[V] Created Desktop BAT: {p_test}")

# 3. Create Windows Shortcuts (.lnk) with icons using PowerShell
ps_script = f"""
$Desktops = @(
    [Environment]::GetFolderPath('Desktop'),
    (Join-Path $env:USERPROFILE 'Desktop'),
    "D:\\Desktop"
) | Select-Object -Unique | Where-Object {{ Test-Path $_ }}

$WshShell = New-Object -ComObject WScript.Shell

foreach ($d in $Desktops) {{
    # 1. Systemize Gym OS shortcut
    $Lnk1 = Join-Path $d "Systemize - تشغيل المنظومة.lnk"
    $s1 = $WshShell.CreateShortcut($Lnk1)
    $s1.TargetPath = "{system_bat}"
    $s1.WorkingDirectory = "{BASE_DIR}"
    $s1.Description = "Systemize Gym OS - تشغيل المنظومة"
    if (Test-Path "{ico_path}") {{ $s1.IconLocation = "{ico_path},0" }}
    $s1.Save()
    Write-Host "[OK] Created shortcut: $Lnk1"

    # 2. Systemize QA Test Website shortcut
    $Lnk2 = Join-Path $d "Systemize - فحص واختبار المنظومة QA.lnk"
    $s2 = $WshShell.CreateShortcut($Lnk2)
    $s2.TargetPath = "{test_bat}"
    $s2.WorkingDirectory = "{BASE_DIR}"
    $s2.Description = "Systemize QA Terminal - معمل فحص واختبار المنظومة"
    if (Test-Path "{ico_path}") {{ $s2.IconLocation = "{ico_path},0" }}
    $s2.Save()
    Write-Host "[OK] Created shortcut: $Lnk2"
}}
"""

encoded_ps = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")

try:
    subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded_ps], check=True)
    print("[V] Windows Desktop Shortcuts created successfully with icons.")
except Exception as e:
    print(f"[!] Warning creating shortcuts via PowerShell: {e}")

print("\n" + "=" * 65)
print(" [SUCCESS] All Desktop Launchers Deployed:")
print("  1. RUN_SYSTEM.bat             -> تشغيل المنظومة (http://127.0.0.1:8000)")
print("  2. RUN_TEST_WEBSITE.bat        -> معمل الفحص والاختبار (http://127.0.0.1:8000/qa/)")
print("=" * 65)
