"""
Automated Standalone Distribution Packager for HULK GYM
Builds a 100% self-contained portable distribution in 'dist/HULK_GYM'
that can be copied and run on ANY Windows laptop without Python or pip installed.
"""

import os
import sys
import shutil
import subprocess
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web_face")
DIST_ROOT = os.path.join(BASE_DIR, "dist")
OUTPUT_DIR = os.path.join(DIST_ROOT, "HULK_GYM")
RUNTIME_DIR = os.path.join(OUTPUT_DIR, "runtime")

# Python Source locations
PY_ROOT = r"C:\Program Files\Python311"
USER_SITE = os.path.expanduser(r"~\AppData\Roaming\Python\Python311\site-packages")
SYS_SITE = os.path.join(PY_ROOT, "Lib", "site-packages")

REQUIRED_PACKAGES = [
    "django",
    "asgiref",
    "sqlparse",
    "cv2",
    "numpy",
    "numpy.libs",
    "PIL",
    "serial",
    "pyautogui",
    "pyperclip",
    "pygetwindow",
    "google",
    "googleapiclient",
    "google_auth_oauthlib",
    "httplib2",
    "urllib3",
]


def log(msg):
    print(f"[*] {msg}", flush=True)


def copy_file_safe(src, dst):
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def build_portable_runtime():
    log("Building Portable Python 3.11 Runtime in: " + RUNTIME_DIR)
    os.makedirs(RUNTIME_DIR, exist_ok=True)

    # 1. Copy Core Python Executables and DLLs
    core_files = [
        "python.exe",
        "pythonw.exe",
        "python3.dll",
        "python311.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
    ]
    for cf in core_files:
        src = os.path.join(PY_ROOT, cf)
        copy_file_safe(src, os.path.join(RUNTIME_DIR, cf))

    # 2. Copy DLLs directory
    dll_src = os.path.join(PY_ROOT, "DLLs")
    dll_dst = os.path.join(RUNTIME_DIR, "DLLs")
    if not os.path.exists(dll_dst) and os.path.exists(dll_src):
        log("Copying Python standard DLLs...")
        shutil.copytree(dll_src, dll_dst)

    # 3. Copy Standard Library Lib
    lib_src = os.path.join(PY_ROOT, "Lib")
    lib_dst = os.path.join(RUNTIME_DIR, "Lib")
    if not os.path.exists(lib_dst):
        log("Copying Python standard library modules (Lib)...")
        os.makedirs(lib_dst, exist_ok=True)
        for root, dirs, files in os.walk(lib_src):
            rel = os.path.relpath(root, lib_src)
            if "site-packages" in rel or "__pycache__" in rel:
                continue
            target_sub = os.path.join(lib_dst, rel)
            os.makedirs(target_sub, exist_ok=True)
            for f in files:
                if not f.endswith(".pyc"):
                    shutil.copy2(os.path.join(root, f), os.path.join(target_sub, f))

    # 4. Copy Required Packages into Lib/site-packages
    site_dst = os.path.join(lib_dst, "site-packages")
    os.makedirs(site_dst, exist_ok=True)
    log("Copying required site-packages (Django, OpenCV, NumPy, Pillow, etc.)...")

    search_dirs = [USER_SITE, SYS_SITE]
    for pkg in REQUIRED_PACKAGES:
        copied = False
        for sdir in search_dirs:
            if not os.path.exists(sdir):
                continue
            # Look for directory or .py / .dist-info
            target_pkg_dir = os.path.join(sdir, pkg)
            target_pkg_file = os.path.join(sdir, pkg + ".py")
            if os.path.isdir(target_pkg_dir):
                dest = os.path.join(site_dst, pkg)
                if not os.path.exists(dest):
                    shutil.copytree(target_pkg_dir, dest, ignore=shutil.ignore_patterns("*.pyc", "__pycache__"))
                copied = True
                break
            elif os.path.isfile(target_pkg_file):
                shutil.copy2(target_pkg_file, os.path.join(site_dst, pkg + ".py"))
                copied = True
                break

        if copied:
            # Also copy matching dist-info / egg-info if exists
            for sdir in search_dirs:
                if not os.path.exists(sdir):
                    continue
                for entry in os.listdir(sdir):
                    if entry.lower().startswith(pkg.lower()) and (entry.endswith(".dist-info") or entry.endswith(".egg-info")):
                        dist_dest = os.path.join(site_dst, entry)
                        if not os.path.exists(dist_dest):
                            try:
                                shutil.copytree(os.path.join(sdir, entry), dist_dest)
                            except Exception:
                                pass

    # 5. Create python311._pth isolated path configuration
    pth_path = os.path.join(RUNTIME_DIR, "python311._pth")
    pth_lines = [
        "python311.zip",
        ".",
        "DLLs",
        "Lib",
        "Lib\\site-packages",
        "..",
        "import site",
    ]
    with open(pth_path, "w", encoding="utf-8") as f:
        f.write("\n".join(pth_lines) + "\n")

    log("Portable Python runtime created successfully.")


def copy_web_app():
    log("Copying HULK GYM application into standalone dist folder...")

    # Folders to copy
    dirs_to_copy = ["apps", "config", "models", "static", "templates", "data"]
    for d in dirs_to_copy:
        src = os.path.join(WEB_DIR, d)
        dst = os.path.join(OUTPUT_DIR, d)
        if os.path.exists(src):
            log(f"Copying {d}...")
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.pyc", "__pycache__"))

    # Copy files
    files_to_copy = ["manage.py", "gym_face.sqlite3", "requirements.txt", "startup.html"]
    for f in files_to_copy:
        src = os.path.join(WEB_DIR, f)
        dst = os.path.join(OUTPUT_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)

    # Ensure media directory exists
    os.makedirs(os.path.join(OUTPUT_DIR, "media", "faces"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "media", "branding"), exist_ok=True)
    if os.path.exists(os.path.join(WEB_DIR, "media")):
        for root, dirs, files in os.walk(os.path.join(WEB_DIR, "media")):
            rel = os.path.relpath(root, os.path.join(WEB_DIR, "media"))
            dest_dir = os.path.join(OUTPUT_DIR, "media", rel)
            os.makedirs(dest_dir, exist_ok=True)
            for file in files:
                shutil.copy2(os.path.join(root, file), os.path.join(dest_dir, file))


def create_launchers():
    log("Creating one-click standalone launchers in dist folder...")

    # Primary Launcher
    start_bat = os.path.join(OUTPUT_DIR, "START_GYM.bat")
    with open(start_bat, "w", encoding="utf-8") as f:
        f.write(
            """@echo off
chcp 65001 >nul
title HULK GYM - Standalone Portable System

cd /d "%~dp0"

echo ===================================================================
echo     HULK GYM MANAGEMENT SYSTEM - PORTABLE CLIENT EDITION
echo ===================================================================
echo.

if exist "startup.html" (
    start "" "%~dp0startup.html"
) else (
    start http://127.0.0.1:8000
)

echo [*] Checking database migrations...
"runtime\\python.exe" manage.py migrate --noinput >nul 2>&1

echo [*] Starting HULK GYM server at http://127.0.0.1:8000 ...
"runtime\\python.exe" manage.py runserver 0.0.0.0:8000
pause
"""
        )
    copy_file_safe(start_bat, os.path.join(OUTPUT_DIR, "Run_Hulk_Gym.bat"))

    # Standalone Update Launcher
    update_bat = os.path.join(OUTPUT_DIR, "UPDATE_GYM.bat")
    with open(update_bat, "w", encoding="utf-8") as f:
        f.write(
            """@echo off
chcp 65001 >nul
title HULK GYM - GitHub System Updater
color 0b

cd /d "%~dp0"

echo ===================================================================
echo             HULK GYM - Standalone GitHub Updater
echo      Portable GitHub Updater with Automatic Database Backup
echo ===================================================================
echo.
echo [*] Checking for updates on GitHub and creating automatic backup...
echo.

"runtime\\python.exe" manage.py check_and_update

echo.
echo ===================================================================
echo  Update check completed. You may now continue using HULK GYM.
echo ===================================================================
echo.
pause
"""
        )
    copy_file_safe(update_bat, os.path.join(OUTPUT_DIR, "UPDATE_HULK_GYM.bat"))

    # Readme for client
    readme = os.path.join(OUTPUT_DIR, "README_INSTRUCTIONS.txt")
    with open(readme, "w", encoding="utf-8") as f:
        f.write(
            """تعليمات تشغيل نظام HULK GYM المحمول (نسخة العميل):
=============================================================

1. هذا المجلد محمول بالكامل (Standalone / Portable):
   - لا يتطلب تثبيت بايثون (Python) على الجهاز.
   - لا يتطلب أي برامج إضافية أو اتصال بالإنترنت للتشغيل اليومي.
   - يحتوي على كافة نماذج الذكاء الاصطناعي وقاعدة البيانات.

2. طريقة التشغيل:
   - قم بنسخ هذا المجلد بالكامل لأي لابتوب أو كمبيوتر يعمل بنظام Windows.
   - اضغط مرتين على ملف: "تشغيل_النظام.bat" (أو "Run_Hulk_Gym.bat").
   - سيفتح المتصفح تلقائياً على الرابط: http://127.0.0.1:8000

3. بيانات الدخول الافتراضية:
   - اسم المستخدم: admin
   - كلمة المرور: admin123456

4. بوابة التعرف على الوجه:
   - تعمل الكاميرا تلقائياً على كامل صفحات النظام فور فتح المتصفح.
   - يمكنك تفعيلها أو إيقافها من صفحة الإعدادات في أي وقت.

5. زر تحديث النظام وسحب التعديلات من GitHub:
   - يمكن التحديث مباشرة بضغطة زر واحدة من داخل لوحة التحكم: الإعدادات -> تحديثات النظام -> "تحديث النظام الآن".
   - أو تشغيل ملف "تحديث_النظام.bat" (أو "UPDATE_HULK_GYM.bat") في أي وقت لسحب أحدث إصدار مع نسخ احتياطي تلقائي لقاعدة البيانات.
"""
        )


def verify_dist():
    log("Verifying generated standalone distribution...")
    test_exe = os.path.join(RUNTIME_DIR, "python.exe")
    res = subprocess.run(
        [test_exe, "manage.py", "check"],
        cwd=OUTPUT_DIR,
        capture_output=True,
        text=True,
    )
    if res.returncode == 0:
        log("Verification SUCCESS: Standalone package runs with 0 errors!")
    else:
        log("Verification Warning:\n" + res.stdout + "\n" + res.stderr)


def main():
    start_time = time.time()
    log("Starting standalone build process for HULK GYM...")
    os.makedirs(DIST_ROOT, exist_ok=True)

    build_portable_runtime()
    copy_web_app()
    create_launchers()
    verify_dist()

    elapsed = round(time.time() - start_time, 1)
    log(f"============================================================")
    log(f"BUILD COMPLETED in {elapsed}s!")
    log(f"Standalone folder ready at: {OUTPUT_DIR}")
    log(f"You can copy/paste or zip this folder onto any client laptop!")
    log(f"============================================================")


if __name__ == "__main__":
    main()
