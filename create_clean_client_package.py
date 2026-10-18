import os
import sys
import shutil
import subprocess
import time
import zipfile

# Ensure proper utf-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
SOURCE_DIR = os.path.join(DIST_DIR, "Systemize")
CLIENT_DIR = os.path.join(DIST_DIR, "Systemize_Client_Release")
ZIP_OUTPUT = os.path.join(DIST_DIR, "Systemize_Client_Release.zip")
PY_EXE = os.path.join(CLIENT_DIR, "runtime", "python.exe")

def log(msg):
    print(f"[*] {msg}", flush=True)

def main():
    start_time = time.time()
    log("==================================================================")
    log("   SYSTEMIZE GYM OS - CLEAN CLIENT RELEASE PACKAGING ENGINE       ")
    log("==================================================================")

    # 1. Prepare target folder
    if os.path.exists(CLIENT_DIR):
        log(f"Removing existing target folder: {CLIENT_DIR}")
        shutil.rmtree(CLIENT_DIR, ignore_errors=True)
    os.makedirs(CLIENT_DIR, exist_ok=True)

    # 2. Copy directories
    dirs_to_copy = ["apps", "config", "models", "runtime", "static", "templates"]
    for d in dirs_to_copy:
        src = os.path.join(SOURCE_DIR, d)
        dst = os.path.join(CLIENT_DIR, d)
        if os.path.exists(src):
            log(f"Copying {d}...")
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.pyc", "__pycache__"))

    # 3. Create fresh data and media directories
    os.makedirs(os.path.join(CLIENT_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(CLIENT_DIR, "media", "faces"), exist_ok=True)
    os.makedirs(os.path.join(CLIENT_DIR, "media", "branding"), exist_ok=True)

    # 4. Copy launcher files, readme, and guide
    files_to_copy = [
        "manage.py",
        "requirements.txt",
        "startup.html",
        "START_SYSTEMIZE.bat",
        "تشغيل_النظام.bat",
        "UPDATE_SYSTEMIZE.bat",
        "تحديث_النظام.bat",
        "README_INSTRUCTIONS.txt",
        "SYSTEMIZE_SYSTEM_GUIDE.md",
        "DEMO_TESTING_GUIDE.md",
    ]
    for f in files_to_copy:
        src = os.path.join(SOURCE_DIR, f)
        dst = os.path.join(CLIENT_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)

    # 5. Initialize Fresh Database with 0 members
    sub_env = os.environ.copy()
    sub_env["PYTHONIOENCODING"] = "utf-8"

    log("Running migrations on fresh client database...")
    res = subprocess.run(
        [PY_EXE, "manage.py", "migrate", "--noinput"],
        cwd=CLIENT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=sub_env
    )
    if res.returncode != 0:
        log("Migration Error:\n" + str(res.stderr) + "\n" + str(res.stdout))
        sys.exit(1)

    log("Executing setup_gym command to provision 0-member clean database...")
    res = subprocess.run(
        [PY_EXE, "manage.py", "setup_gym"],
        cwd=CLIENT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=sub_env
    )
    if res.returncode != 0:
        log("Setup Error:\n" + str(res.stderr) + "\n" + str(res.stdout))
        sys.exit(1)
    log(str(res.stdout))

    # 6. Verify Database State
    verify_cmd = (
        "import os, django; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup(); "
        "from apps.members.models import Member; from apps.accounts.models import User; "
        "print(f'CLEAN_VERIFICATION: Members={Member.objects.count()}, Users={User.objects.count()}'); "
        "assert Member.objects.count() == 0, 'Members must be 0!';"
    )
    res = subprocess.run(
        [PY_EXE, "-c", verify_cmd],
        cwd=CLIENT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=sub_env
    )
    log(res.stdout)
    if res.returncode != 0:
        log("Verification failed: " + res.stderr)
        sys.exit(1)

    # 7. Compress into ZIP archive
    log(f"Compressing into portable client ZIP package: {ZIP_OUTPUT} ...")
    if os.path.exists(ZIP_OUTPUT):
        os.remove(ZIP_OUTPUT)

    with zipfile.ZipFile(ZIP_OUTPUT, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(CLIENT_DIR):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, os.path.dirname(CLIENT_DIR))
                zipf.write(abs_path, rel_path)

    zip_size_mb = round(os.path.getsize(ZIP_OUTPUT) / (1024 * 1024), 2)
    elapsed = round(time.time() - start_time, 1)

    log("=" * 70)
    log(f"   CLIENT PACKAGE SUCCESSFULLY GENERATED IN {elapsed}s!")
    log(f"   Unzipped Folder: {CLIENT_DIR}")
    log(f"   Zipped Archive:  {ZIP_OUTPUT} ({zip_size_mb} MB)")
    log("   Ready to deliver to clients for zero-setup 1-click execution!")
    log("=" * 70)

if __name__ == "__main__":
    main()
