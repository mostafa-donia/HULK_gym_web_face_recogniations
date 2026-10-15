import os
import sys
import shutil
import subprocess
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.utils import timezone


def get_repo_dir() -> Path:
    """Returns the base repository directory (containing .git or manage.py)."""
    base = Path(settings.BASE_DIR)
    # If BASE_DIR is web_face, check web_face/.git, then gym system/.git, then parent/.git
    if (base / ".git").exists():
        return base
    if (base.parent / ".git").exists():
        return base.parent
    if (base.parent.parent / ".git").exists():
        return base.parent.parent
    return base


def run_git_command(args: list, cwd: Path = None, timeout: int = 25) -> tuple[bool, str]:
    """Safely executes a git command and returns (success, output)."""
    git_bin = shutil.which("git")
    if not git_bin:
        # Check standard Git installations on Windows
        common_paths = [
            Path("C:/Program Files/Git/cmd/git.exe"),
            Path("C:/Program Files/Git/bin/git.exe"),
            Path("C:/Program Files (x86)/Git/cmd/git.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Git/cmd/git.exe",
        ]
        for p in common_paths:
            if p.exists():
                git_bin = str(p)
                break

    if not git_bin:
        return False, "أداة Git غير مثبتة في مسار النظام (Git is not installed or not in PATH)."

    target_dir = str(cwd or get_repo_dir())
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    try:
        proc = subprocess.run(
            [git_bin] + args,
            cwd=target_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode == 0:
            return True, out if out else err
        return False, err if err else out
    except subprocess.TimeoutExpired:
        return False, "انتهت مهلة الاتصال بمستودع GitHub (Connection Timed Out)."
    except Exception as e:
        return False, str(e)


def get_current_version_info() -> dict:
    """Retrieves current commit hash, branch, and last commit info."""
    repo_dir = get_repo_dir()
    info = {
        "commit": "unknown",
        "branch": "main",
        "date": "غير محدد",
        "message": "إصدار HULK GYM الأساسي",
        "has_git": False,
        "repo_dir": str(repo_dir),
    }

    ok_hash, out_hash = run_git_command(["rev-parse", "--short", "HEAD"])
    if ok_hash and out_hash:
        info["commit"] = out_hash.splitlines()[0].strip()
        info["has_git"] = True

    ok_branch, out_branch = run_git_command(["branch", "--show-current"])
    if ok_branch and out_branch:
        info["branch"] = out_branch.splitlines()[0].strip()

    ok_log, out_log = run_git_command(["log", "-1", "--format=%cd|%s", "--date=short"])
    if ok_log and "|" in out_log:
        parts = out_log.split("|", 1)
        info["date"] = parts[0].strip()
        info["message"] = parts[1].strip()

    # Read from local version.json fallback if available
    version_file = repo_dir / "version.json"
    if version_file.exists():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                v_data = json.load(f)
                info["version_tag"] = v_data.get("version", "v2.1.0")
        except Exception:
            pass
    else:
        info["version_tag"] = "v2.1.0-face"

    return info


def check_for_updates(profile=None) -> dict:
    """
    Checks GitHub for any new commits or updates available on the remote branch.
    Returns status dictionary with commit count and details.
    """
    from apps.core.models import GymProfile
    profile = profile or GymProfile.get_solo()
    branch = profile.github_branch or "main"
    current_info = get_current_version_info()

    profile.last_update_check = timezone.now()
    profile.save(update_fields=["last_update_check"])

    if current_info["has_git"]:
        # 1. Fetch latest changes from remote with safe timeout
        ok_fetch, out_fetch = run_git_command(["fetch", "origin", branch], timeout=15)
        if not ok_fetch:
            print(f"[check_for_updates] Git fetch warning: {out_fetch}. Trying GitHub API fallback...")
            api_res = check_updates_via_api(profile, current_info)
            if api_res.get("success"):
                return api_res
            return {
                "success": False,
                "update_available": False,
                "message": f"تعذر الاتصال بـ GitHub: {out_fetch or 'يرجى التحقق من اتصال الإنترنت'}",
                "error": out_fetch,
                "current_info": current_info,
            }

        # 2. Count commits behind
        ok_count, out_count = run_git_command(["rev-list", f"HEAD..origin/{branch}", "--count"])
        behind_count = 0
        try:
            behind_count = int(out_count.strip()) if ok_count else 0
        except ValueError:
            behind_count = 0

        if behind_count > 0:
            # Get list of new commit messages
            _, commits_log = run_git_command(["log", f"HEAD..origin/{branch}", "--oneline", "-n", "8"])
            _, remote_latest = run_git_command(["log", "-1", "--format=%h|%s|%cd", "--date=short", f"origin/{branch}"])
            remote_parts = remote_latest.split("|") if "|" in remote_latest else ["", "", ""]

            commits_list = [c.strip() for c in commits_log.splitlines() if c.strip()]

            return {
                "success": True,
                "update_available": True,
                "commits_behind": behind_count,
                "current_commit": current_info["commit"],
                "remote_commit": remote_parts[0] if len(remote_parts) > 0 else "latest",
                "remote_message": remote_parts[1] if len(remote_parts) > 1 else "",
                "remote_date": remote_parts[2] if len(remote_parts) > 2 else "",
                "commits_list": commits_list,
                "branch": branch,
                "message": f"يوجد {behind_count} تحديث جديد متوفر على GitHub جاهز للتثبيت! 🚀",
                "current_info": current_info,
            }

        return {
            "success": True,
            "update_available": False,
            "commits_behind": 0,
            "current_commit": current_info["commit"],
            "branch": branch,
            "message": "النظام محدث بالكامل لأحدث إصدار متوفر على GitHub ✓",
            "current_info": current_info,
        }

    # Fallback to GitHub API if Git binary or .git folder is absent
    return check_updates_via_api(profile, current_info)


def check_updates_via_api(profile, current_info) -> dict:
    """Fallback updater using GitHub Public REST API when Git binary is missing."""
    repo_url = profile.github_repo_url or "https://github.com/mostafa-donia/HULK_gym_web_face_recogniations.git"
    clean_url = repo_url.replace(".git", "").rstrip("/")
    parts = clean_url.split("/")
    if len(parts) >= 2:
        owner = parts[-2]
        repo_name = parts[-1]
    else:
        owner, repo_name = "mostafa-donia", "HULK_gym_web_face_recogniations"

    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{profile.github_branch or 'main'}"
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": "HulkGym-System-Updater", "Accept": "application/vnd.github.v3+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            sha = data.get("sha", "")[:7]
            msg = data.get("commit", {}).get("message", "").splitlines()[0]
            date_str = data.get("commit", {}).get("author", {}).get("date", "")[:10]

            is_diff = sha and sha != current_info["commit"] and current_info["commit"] != "unknown"
            return {
                "success": True,
                "update_available": is_diff,
                "commits_behind": 1 if is_diff else 0,
                "current_commit": current_info["commit"],
                "remote_commit": sha,
                "remote_message": msg,
                "remote_date": date_str,
                "commits_list": [f"{sha} {msg}"],
                "message": "يوجد تحديث متوفر على GitHub!" if is_diff else "النظام محدث بالكامل لأحدث إصدار ✓",
                "current_info": current_info,
            }
    except Exception as e:
        return {
            "success": False,
            "update_available": False,
            "message": f"تعذر التحقق من التحديثات: {str(e)}",
            "current_info": current_info,
        }


def backup_database() -> tuple[bool, str]:
    """Creates a timestamped snapshot backup of gym_face.sqlite3 before updating."""
    base_dir = Path(settings.BASE_DIR)
    db_file = base_dir / "gym_face.sqlite3"
    if not db_file.exists():
        # Look in parent
        db_file = base_dir.parent / "gym_face.sqlite3"

    if not db_file.exists():
        return False, "قاعدة البيانات غير موجودة لعمل نسخة احتياطية."

    backup_dir = base_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"backup_pre_update_{timestamp}.sqlite3"

    try:
        shutil.copy2(db_file, backup_file)
        return True, str(backup_file)
    except Exception as e:
        return False, f"فشل عمل النسخة الاحتياطية: {str(e)}"


def update_via_zip_download(profile, branch: str, logs: list) -> tuple[bool, str]:
    """
    Downloads repo archive zip from GitHub as fallback when Git CLI is unavailable.
    Safely unpacks updated python/html files without overwriting sqlite database or media.
    """
    import zipfile
    import tempfile

    repo_url = profile.github_repo_url or "https://github.com/mostafa-donia/HULK_gym_web_face_recogniations.git"
    clean_url = repo_url.replace(".git", "").rstrip("/")
    parts = clean_url.split("/")
    if len(parts) >= 2:
        owner = parts[-2]
        repo_name = parts[-1]
    else:
        owner, repo_name = "mostafa-donia", "HULK_gym_web_face_recogniations"

    zip_url = f"https://github.com/{owner}/{repo_name}/archive/refs/heads/{branch}.zip"
    logs.append(f"⏳ جاري تحميل حزمة التحديث من GitHub ({owner}/{repo_name})...")

    target_dir = Path(settings.BASE_DIR)
    PROTECTED_ITEMS = {
        "gym_face.sqlite3",
        "gym_face.db",
        "db.sqlite3",
        "backups",
        "media",
        "runtime",
        ".env",
    }

    try:
        req = urllib.request.Request(
            zip_url,
            headers={"User-Agent": "HulkGym-System-Updater"}
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_zip = Path(tmp_dir) / "update.zip"
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_zip, "wb") as out_file:
                shutil.copyfileobj(resp, out_file)

            logs.append("✓ تم تحميل حزمة التحديث بنجاح. جاري استخراج وتحديث الملفات...")
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                members = zf.infolist()
                if not members:
                    return False, "ملف التحديث المضغوط فارغ."
                root_prefix = members[0].filename.split("/")[0] + "/"

                extracted = 0
                for m in members:
                    if m.is_dir():
                        continue
                    rel_path = m.filename
                    if rel_path.startswith(root_prefix):
                        rel_path = rel_path[len(root_prefix):]
                    if not rel_path:
                        continue

                    parts_rel = Path(rel_path).parts
                    if any(p in PROTECTED_ITEMS for p in parts_rel):
                        continue

                    dest_file = target_dir / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(m) as src, open(dest_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted += 1

            logs.append(f"✓ تم استخراج وتحديث {extracted} ملفاً بنجاح.")
            return True, "تم تحديث الملفات بنجاح من GitHub Archive."
    except Exception as e:
        return False, f"فشل تحميل وتطبيق التحديث عبر الإنترنت: {str(e)}"


def perform_system_update(profile=None) -> dict:
    """
    Executes the complete system update pipeline:
    1. Backs up SQLite database
    2. Pulls latest changes from GitHub (git pull) or downloads archive zip
    3. Runs Django database migrations
    4. Refreshes AI face recognition caches
    """
    from apps.core.models import GymProfile
    profile = profile or GymProfile.get_solo()
    branch = profile.github_branch or "main"
    logs = []

    # 1. Database Backup
    logs.append("⏳ 1. جاري إنشاء نسخة احتياطية لقاعدة البيانات...")
    backup_ok, backup_path = backup_database()
    if backup_ok:
        logs.append(f"✓ تم حفظ نسخة احتياطية آمنة في: {Path(backup_path).name}")
    else:
        logs.append(f"⚠️ تحذير: {backup_path}")

    # 2. Git Stash & Pull with Zip Fallback
    current_info = get_current_version_info()
    pulled = False

    if current_info.get("has_git"):
        logs.append(f"⏳ 2. جاري سحب التحديثات عبر Git (Branch: {branch})...")
        run_git_command(["stash"])
        ok_pull, out_pull = run_git_command(["pull", "origin", branch], timeout=60)
        if ok_pull:
            pulled = True
            logs.append(f"✓ تم سحب التحديثات بنجاح: {out_pull[:100]}...")
        else:
            logs.append(f"⚠️ تعذر السحب عبر Git: {out_pull[:80]}. جاري تجربة التحديث المباشر من GitHub...")

    if not pulled:
        ok_zip, out_zip = update_via_zip_download(profile, branch, logs)
        if not ok_zip:
            logs.append(f"❌ خطأ أثناء تطبيق التحديث: {out_zip}")
            return {
                "success": False,
                "message": f"فشل سحب التحديثات من GitHub: {out_zip}",
                "logs": logs,
            }

    # 3. Apply Migrations
    logs.append("⏳ 3. جاري تطبيق ترقيات قاعدة البيانات (manage.py migrate)...")
    python_bin = sys.executable
    base_dir = Path(settings.BASE_DIR)
    manage_py = base_dir / "manage.py"

    try:
        mig_proc = subprocess.run(
            [python_bin, str(manage_py), "migrate", "--noinput"],
            cwd=str(base_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=40,
        )
        if mig_proc.returncode == 0:
            logs.append("✓ تم فحص وترقية جداول قاعدة البيانات بنجاح.")
        else:
            logs.append(f"⚠️ تنبيه أثناء ترقية قاعدة البيانات: {mig_proc.stderr[:100]}")
    except Exception as e:
        logs.append(f"⚠️ تعذر تشغيل migrate تلقائياً: {str(e)}")

    # 4. Refresh AI Cache
    logs.append("⏳ 4. جاري تحديث ذاكرة التعرف على الوجه...")
    try:
        from apps.face_recognition.engine import get_face_engine
        engine = get_face_engine()
        engine.refresh_cache(force=True)
        logs.append("✓ تم تحديث ذاكرة بصمات الوجه بنجاح.")
    except Exception:
        pass

    # 5. Get new commit hash
    new_info = get_current_version_info()
    profile.current_version_tag = f"v2.1.0 ({new_info['commit']})"
    profile.save(update_fields=["current_version_tag"])

    logs.append(f"🎉 5. اكتمل التحديث بنجاح! الإصدار الحالي: {new_info['commit']} ({new_info['date']})")

    return {
        "success": True,
        "message": f"تم تحديث النظام بنجاح إلى آخر إصدار ({new_info['commit']})!",
        "new_info": new_info,
        "logs": logs,
    }
