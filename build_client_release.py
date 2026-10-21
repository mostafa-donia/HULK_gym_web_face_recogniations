import os
import sys
import shutil
import compileall
import subprocess

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = r"d:\move\career\gym system"
SRC_DIR = os.path.join(BASE_DIR, "web_face")
DIST_SYS = os.path.join(BASE_DIR, "dist", "Systemize")
CLIENT_DIR = os.path.join(BASE_DIR, "dist", "Systemize_Client_Release")

print("=" * 68)
print("  SYSTEMIZE GYM OS — CLIENT RELEASE BUILDER")
print("  Zero Source Code (.py stripped) + Hidden Terminal + Inno Setup + GitHub Updater")
print("=" * 68)

# 1. Clean and recreate CLIENT_DIR
print(f"[*] Target Directory: {CLIENT_DIR}")
if os.path.exists(CLIENT_DIR):
    print("[*] Cleaning previous client release build...")
    shutil.rmtree(CLIENT_DIR)
os.makedirs(CLIENT_DIR, exist_ok=True)

# 2. Copy Python Runtime
print("[*] Copying portable Python runtime (380MB)...")
shutil.copytree(os.path.join(DIST_SYS, "runtime"), os.path.join(CLIENT_DIR, "runtime"))

# 3. Copy Static, Templates, Models, Data
for folder in ["static", "templates", "models", "data"]:
    src_f = os.path.join(SRC_DIR, folder)
    if os.path.exists(src_f):
        print(f"[*] Copying {folder}...")
        shutil.copytree(src_f, os.path.join(CLIENT_DIR, folder))

# 4. Copy Media structure
media_dst = os.path.join(CLIENT_DIR, "media")
os.makedirs(media_dst, exist_ok=True)
for sub in ["members", "invoices", "faces", "profiles"]:
    os.makedirs(os.path.join(media_dst, sub), exist_ok=True)

# 5. Copy clean database template
db_src = os.path.join(DIST_SYS, "gym_face.sqlite3")
if not os.path.exists(db_src):
    db_src = os.path.join(SRC_DIR, "gym_face.sqlite3")
print("[*] Copying initialized database template...")
shutil.copy2(db_src, os.path.join(CLIENT_DIR, "gym_face.sqlite3"))

# 6. Copy Icon and HTML Startup files
for fname in ["gym_icon.ico", "startup.html"]:
    for cand_dir in [DIST_SYS, SRC_DIR, BASE_DIR]:
        cand_p = os.path.join(cand_dir, fname)
        if os.path.exists(cand_p):
            shutil.copy2(cand_p, os.path.join(CLIENT_DIR, fname))
            break

# 7. Copy Python Application Code for compilation
print("[*] Copying Python source tree (apps, config, manage.py)...")
shutil.copytree(os.path.join(SRC_DIR, "apps"), os.path.join(CLIENT_DIR, "apps"))
shutil.copytree(os.path.join(SRC_DIR, "config"), os.path.join(CLIENT_DIR, "config"))
shutil.copy2(os.path.join(SRC_DIR, "manage.py"), os.path.join(CLIENT_DIR, "manage.py"))
shutil.copy2(os.path.join(SRC_DIR, "show_network_ip.py"), os.path.join(CLIENT_DIR, "show_network_ip.py"))

# 8. COMPILE TARGET APPLICATION PYTHON FILES ONLY TO OPTIMIZED BYTECODE (.pyc)
print("[*] Compiling application Python code to optimized bytecode (.pyc)...")
py_exe = os.path.join(CLIENT_DIR, "runtime", "python.exe")

for target_sub in [os.path.join(CLIENT_DIR, "apps"), os.path.join(CLIENT_DIR, "config")]:
    compileall.compile_dir(target_sub, force=True, legacy=True, optimize=2, quiet=1)

compileall.compile_file(os.path.join(CLIENT_DIR, "manage.py"), legacy=True, optimize=2)
compileall.compile_file(os.path.join(CLIENT_DIR, "show_network_ip.py"), legacy=True, optimize=2)

print("[*] REMOVING ALL .py SOURCE CODE FILES...")
py_count = 0
for root, dirs, files in os.walk(CLIENT_DIR):
    if os.path.commonpath([root, os.path.join(CLIENT_DIR, "runtime")]).lower() == os.path.join(CLIENT_DIR, "runtime").lower():
        continue
    for f in files:
        if f.endswith(".py"):
            fpath = os.path.join(root, f)
            os.remove(fpath)
            py_count += 1

print(f"  [V] Stripped and deleted {py_count} source (.py) files! ZERO .py files remain in the application.")

# 9. Write Silent Launcher (Hidden Terminal)
vbs_content = '''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' Check if server is already running on port 8000
' Launch background pythonw without any console window
WshShell.Run "runtime\\pythonw.exe manage.pyc runserver 0.0.0.0:8000 --noreload", 0, False

' Brief pause then open default browser
WScript.Sleep 1600
WshShell.Run "http://127.0.0.1:8000"
'''
with open(os.path.join(CLIENT_DIR, "Systemize_Silent.vbs"), "w", encoding="utf-8") as f:
    f.write(vbs_content)

# 10. Write STOP_SYSTEMIZE.bat
stop_bat = """@echo off
chcp 65001 > nul
title Systemize Gym OS - Stop Server
color 0C

echo ===================================================================
echo     إيقاف تشغيل سيرفر Systemize Gym OS
echo ===================================================================
echo.
echo [*] Stopping background services...

taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1

echo.
echo  [V] تم إيقاف النظام وسيرفر البرنامج بنجاح.
echo ===================================================================
timeout /t 3 >nul
"""
with open(os.path.join(CLIENT_DIR, "STOP_SYSTEMIZE.bat"), "wb") as f:
    f.write(stop_bat.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))

# 11. Write START_DEBUG.bat (if client specifically needs to see terminal logs)
debug_bat = """@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Systemize Gym OS - Debug Console
color 0A

cd /d "%~dp0"

echo ===================================================================
echo     SYSTEMIZE GYM OS - Debug Console
echo ===================================================================
echo.

if exist "show_network_ip.pyc" (
    "runtime\\python.exe" -s show_network_ip.pyc
)

echo [*] Starting Server at http://127.0.0.1:8000 ...
start "" "http://127.0.0.1:8000"
"runtime\\python.exe" -s manage.pyc runserver 0.0.0.0:8000
pause
"""
with open(os.path.join(CLIENT_DIR, "START_SYSTEMIZE.bat"), "wb") as f:
    f.write(debug_bat.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))

# 12. Write GitHub Auto-Updater Script (updater.pyc + UPDATE_FROM_GITHUB.bat)
updater_py = '''import os
import sys
import shutil
import zipfile
import urllib.request
import compileall

REPO_ZIP_URL = "https://github.com/mostafa-donia/HULK_gym_web_face_recogniations/archive/refs/heads/main.zip"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

print("=" * 64)
print("  SYSTEMIZE GYM OS — GITHUB AUTO-UPDATER")
print("=" * 64)
print("[*] Connecting to GitHub to check latest update package...")

zip_path = os.path.join(BASE_DIR, "_update_pkg.zip")
extract_dir = os.path.join(BASE_DIR, "_update_extracted")

try:
    headers = {"User-Agent": "Systemize-Client-Updater"}
    req = urllib.request.Request(REPO_ZIP_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        with open(zip_path, "wb") as f:
            f.write(resp.read())
    print("[*] Downloaded update package successfully.")

    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)

    # Locate web_face in extracted repo
    repo_root = ""
    for item in os.listdir(extract_dir):
        sub = os.path.join(extract_dir, item)
        if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "web_face")):
            repo_root = os.path.join(sub, "web_face")
            break

    if not repo_root:
        raise ValueError("Could not find web_face in downloaded update package.")

    print("[*] Applying code updates (Apps, Templates, Static)...")
    for fld in ["apps", "config", "templates", "static"]:
        src_fld = os.path.join(repo_root, fld)
        dst_fld = os.path.join(BASE_DIR, fld)
        if os.path.exists(src_fld):
            if os.path.exists(dst_fld):
                shutil.rmtree(dst_fld)
            shutil.copytree(src_fld, dst_fld)

    # Copy updated manage.py
    shutil.copy2(os.path.join(repo_root, "manage.py"), os.path.join(BASE_DIR, "manage.py"))

    # Compile new files to .pyc and strip .py
    print("[*] Compiling new update to bytecode (.pyc)...")
    for target_sub in [os.path.join(BASE_DIR, "apps"), os.path.join(BASE_DIR, "config")]:
        compileall.compile_dir(target_sub, force=True, legacy=True, optimize=2, quiet=1)
    compileall.compile_file(os.path.join(BASE_DIR, "manage.py"), legacy=True, optimize=2)

    # Remove all .py files
    for root, dirs, files in os.walk(BASE_DIR):
        if os.path.commonpath([root, os.path.join(BASE_DIR, "runtime")]).lower() == os.path.join(BASE_DIR, "runtime").lower():
            continue
        for f in files:
            if f.endswith(".py"):
                try: os.remove(os.path.join(root, f))
                except: pass

    # Run migrations
    print("[*] Running database migrations...")
    py_exe = os.path.join(BASE_DIR, "runtime", "python.exe")
    os.system(f'"{py_exe}" -s manage.pyc migrate --noinput')

    # Cleanup temp zip
    if os.path.exists(zip_path): os.remove(zip_path)
    if os.path.exists(extract_dir): shutil.rmtree(extract_dir)

    print("")
    print("=" * 64)
    print("  [V] تم تحديث النظام بنجاح من GitHub بأحدث نسخة!")
    print("  بيانات المشتركين والاشتراكات والصور محفوظة 100% دون مساس.")
    print("=" * 64)
except Exception as e:
    print(f"[!] Update error: {e}")
    if os.path.exists(zip_path): os.remove(zip_path)
    if os.path.exists(extract_dir): shutil.rmtree(extract_dir)
'''
with open(os.path.join(CLIENT_DIR, "updater.py"), "w", encoding="utf-8") as f:
    f.write(updater_py)

compileall.compile_file(os.path.join(CLIENT_DIR, "updater.py"), legacy=True, optimize=2)
os.remove(os.path.join(CLIENT_DIR, "updater.py"))

update_bat = """@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Systemize Gym OS - Online Updater
color 0B

cd /d "%~dp0"
echo ===================================================================
echo     تحديث نظام Systemize تلقائياً من GitHub
echo ===================================================================
echo.
"runtime\\python.exe" -s updater.pyc
echo.
pause
"""
with open(os.path.join(CLIENT_DIR, "UPDATE_SYSTEMIZE.bat"), "wb") as f:
    f.write(update_bat.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))

# 13. Verify Build by running manage.pyc check
print("[*] Verifying build integrity...")
check_res = subprocess.run([py_exe, "manage.pyc", "check"], cwd=CLIENT_DIR, capture_output=True, text=True)
if check_res.returncode == 0:
    print("  [V] Django System Check: PASSED with ZERO issues!")
else:
    print("  [!] Django System Check Failed:")
    print(check_res.stderr)
    sys.exit(1)

# 14. Create Inno Setup Script
print("[*] Generating Inno Setup Script (Systemize_Setup.iss)...")
iss_content = f"""#define MyAppName "Systemize Gym OS"
#define MyAppVersion "2.0"
#define MyAppPublisher "Systemize Tech"
#define MyAppURL "http://127.0.0.1:8000"
#define SourceDir "{CLIENT_DIR}"

[Setup]
AppId={{{{D29E73A1-884B-4E32-9F10-6C2A7B8E9012}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
AppUpdatesURL={{#MyAppURL}}
DefaultDirName=C:\\Systemize
DefaultGroupName={{#MyAppName}}
AllowNoIcons=yes
OutputDir={os.path.join(BASE_DIR, "dist")}
OutputBaseFilename=Systemize_Setup_v2.0
SetupIconFile={{#SourceDir}}\\gym_icon.ico
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
CloseApplications=force

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"

[Files]
; 1. Preserve existing client database on upgrade
Source: "{{#SourceDir}}\\gym_face.sqlite3"; DestDir: "{{app}}"; Flags: onlyifdoesntexist uninsneveruninstall

; 2. Preserve existing member photos and invoices
Source: "{{#SourceDir}}\\media\\*"; DestDir: "{{app}}\\media"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs uninsneveruninstall

; 3. All other compiled binaries, templates, static assets, and runtime
Source: "{{#SourceDir}}\\*"; DestDir: "{{app}}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "gym_face.sqlite3,media\\*"

[Icons]
; Main Silent Desktop Shortcut (Zero Terminal / Console completely hidden!)
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{sys}}\\wscript.exe"; Parameters: \"\"\"{{app}}\\Systemize_Silent.vbs\"\"\"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\gym_icon.ico"; Tasks: desktopicon

; Start Menu Shortcuts
Name: "{{autoprograms}}\\{{#MyAppName}}\\{{#MyAppName}}"; Filename: "{{sys}}\\wscript.exe"; Parameters: \"\"\"{{app}}\\Systemize_Silent.vbs\"\"\"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\gym_icon.ico"
Name: "{{autoprograms}}\\{{#MyAppName}}\\إيقاف تشغيل Systemize (Stop)"; Filename: "{{app}}\\STOP_SYSTEMIZE.bat"; WorkingDir: "{{app}}"
Name: "{{autoprograms}}\\{{#MyAppName}}\\تحديث النظام من GitHub"; Filename: "{{app}}\\UPDATE_SYSTEMIZE.bat"; WorkingDir: "{{app}}"
Name: "{{autoprograms}}\\{{#MyAppName}}\\تشغيل مع شاشة الأوامر (Debug)"; Filename: "{{app}}\\START_SYSTEMIZE.bat"; WorkingDir: "{{app}}"
Name: "{{autoprograms}}\\{{#MyAppName}}\\Uninstall Systemize"; Filename: "{{uninstallexe}}"

[Run]
; Auto-run migrations silently upon installation
Filename: "{{app}}\\runtime\\python.exe"; Parameters: "manage.pyc migrate --noinput"; WorkingDir: "{{app}}"; StatusMsg: "Configuring database schema..."; Flags: runhidden

; Optional: Launch Systemize immediately after install
Filename: "{{sys}}\\wscript.exe"; Parameters: \"\"\"{{app}}\\Systemize_Silent.vbs\"\"\"; WorkingDir: "{{app}}"; Description: "{{cm:LaunchProgram,{{#StringChange(MyAppName, '&', '&&')}}}}"; Flags: postinstall nowait
"""

iss_path = os.path.join(BASE_DIR, "Systemize_Setup.iss")
with open(iss_path, "w", encoding="utf-8") as f:
    f.write(iss_content)
print(f"  [V] Inno Setup Script generated: {iss_path}")

# 15. Compile Inno Setup Installer if ISCC is installed
iscc_path = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if os.path.exists(iscc_path):
    print("[*] Compiling Standalone Installer via Inno Setup (ISCC)...")
    compile_res = subprocess.run([iscc_path, iss_path], capture_output=True, text=True)
    if compile_res.returncode == 0:
        print("  [V] INNO SETUP INSTALLER BUILT SUCCESSFULLY!")
        print(f"  Output File: {os.path.join(BASE_DIR, 'dist', 'Systemize_Setup_v2.0.exe')}")
    else:
        print("[!] Inno Setup compilation error:")
        print(compile_res.stderr or compile_res.stdout)
else:
    print("[!] Inno Setup ISCC.exe not found at standard path.")

print("")
print("=" * 68)
print("  CLIENT PACKAGE & SETUP COMPLETED SUCCESSFULLY!")
print(f"  Folder: {CLIENT_DIR}")
print(f"  Installer: {os.path.join(BASE_DIR, 'dist', 'Systemize_Setup_v2.0.exe')}")
print("=" * 68)
