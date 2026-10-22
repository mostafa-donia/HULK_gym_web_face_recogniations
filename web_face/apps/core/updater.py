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
    # Check current directory and parents for .git
    for cand in [base, base.parent, base.parent.parent]:
        if (cand / ".git").exists():
            return cand
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
    base_dir = Path(settings.BASE_DIR)
    info = {
        "commit": "unknown",
        "branch": "main",
        "date": "غير محدد",
        "message": "إصدار Systemize الأساسي",
        "version_tag": "v2.0",
        "has_git": False,
        "repo_dir": str(repo_dir),
    }

    # 1. Read from local version.json fallback if available
    for v_dir in [base_dir, repo_dir, base_dir.parent]:
        version_file = v_dir / "version.json"
        if version_file.exists():
            try:
                with open(version_file, "r", encoding="utf-8") as f:
                    v_data = json.load(f)
                    if v_data.get("commit"):
                        info["commit"] = str(v_data["commit"])[:7]
                    if v_data.get("version"):
                        info["version_tag"] = str(v_data["version"])
                    if v_data.get("date"):
                        info["date"] = str(v_data["date"])
                    if v_data.get("message") and info["message"] == "إصدار Systemize الأساسي":
                        info["message"] = str(v_data["message"])
                break
            except Exception:
                pass

    # 2. If Git is present, override with real live Git info
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

    # Central Cloud updates permission check
    try:
        from apps.core.models import SystemLicense
        lic = SystemLicense.get_solo()
        if not lic.updates_allowed:
            block_msg = lic.update_block_reason or "تم إيقاف التحديثات البرمجية لهذه النسخة مؤقتاً بقرار من إدارة النظام المركزية."
            return {
                "success": True,
                "update_available": False,
                "updates_blocked": True,
                "commits_behind": 0,
                "current_commit": current_info["commit"],
                "remote_commit": current_info["commit"],
                "branch": branch,
                "message": f"🔒 التحديثات معطلة: {block_msg}",
                "current_info": current_info,
            }
    except Exception as exc:
        print(f"[check_for_updates] License check warning: {exc}")

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
                "update_available": True,  # Allow manual/zip update anyway
                "message": f"تعذر الاتصال بـ GitHub عبر Git: {out_fetch or 'يرجى التحقق من اتصال الإنترنت'}",
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
            "remote_commit": current_info["commit"],
            "branch": branch,
            "message": f"النظام محدث بالكامل لأحدث إصدار ({current_info['commit']}) ✓",
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

    branch = profile.github_branch or "main"
    api_url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{branch}"
    req = urllib.request.Request(
        api_url,
        headers={"User-Agent": "Systemize-Gym-Updater", "Accept": "application/vnd.github.v3+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            sha = data.get("sha", "")[:7]
            msg = data.get("commit", {}).get("message", "").splitlines()[0]
            date_str = data.get("commit", {}).get("author", {}).get("date", "")[:10]

            curr_commit = current_info.get("commit", "unknown")
            is_diff = bool(sha and (curr_commit == "unknown" or sha != curr_commit))

            return {
                "success": True,
                "update_available": is_diff,
                "commits_behind": 1 if is_diff else 0,
                "current_commit": curr_commit,
                "remote_commit": sha,
                "remote_message": msg,
                "remote_date": date_str,
                "commits_list": [f"{sha} {msg}"],
                "message": f"يوجد تحديث متوفر على GitHub ({sha})! 🚀" if is_diff else f"النظام محدث بالكامل لأحدث إصدار ({curr_commit}) ✓",
                "current_info": current_info,
            }
    except Exception as e:
        # If GitHub API fails (rate limit, timeout, etc.), still allow one-click update via direct archive download
        return {
            "success": True,
            "update_available": True,
            "commits_behind": 1,
            "current_commit": current_info.get("commit", "unknown"),
            "remote_commit": "latest",
            "remote_message": "سحب وتثبيت أحدث نسخة مباشرة من GitHub",
            "remote_date": datetime.now().strftime("%Y-%m-%d"),
            "commits_list": ["تحديث النظام من المستودع السحابي"],
            "message": "التحديث السحابي المباشر متاح وجاهز للتثبيت ⚡",
            "current_info": current_info,
        }


def backup_database() -> tuple[bool, str]:
    """Creates a timestamped snapshot backup of gym_face.sqlite3 before updating."""
    base_dir = Path(settings.BASE_DIR)
    db_file = base_dir / "gym_face.sqlite3"
    if not db_file.exists():
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


def update_via_zip_download(profile, branch: str, logs: list, remote_info: dict = None) -> tuple[bool, str]:
    """
    Downloads repo archive zip from GitHub as fallback when Git CLI is unavailable.
    Safely unpacks updated python/html files without overwriting sqlite database, media, or licenses.
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
    logs.append(f"⏳ جاري تحميل حزمة التحديث من GitHub ({owner}/{repo_name} @ {branch})...")

    target_dir = Path(settings.BASE_DIR)
    PROTECTED_ITEMS = {
        "gym_face.sqlite3",
        "gym_face.db",
        "db.sqlite3",
        "backups",
        "media",
        "runtime",
        ".env",
        "system_license.json",
        "Systemize.exe",
        "Systemize_Silent.vbs",
        "START_SYSTEMIZE.bat",
        "STOP_SYSTEMIZE.bat",
        "UPDATE_SYSTEMIZE.bat",
    }

    try:
        req = urllib.request.Request(
            zip_url,
            headers={"User-Agent": "Systemize-Client-Updater"}
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_zip = Path(tmp_dir) / "update.zip"
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_zip, "wb") as out_file:
                shutil.copyfileobj(resp, out_file)

            logs.append("✓ تم تحميل حزمة التحديث بنجاح. جاري فحص واستخراج الملفات...")
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

                    # IMPORTANT: In the git repo, Django code lives inside web_face/
                    # target_dir (settings.BASE_DIR) IS the Django project root!
                    # So web_face/apps/core/... must map directly to target_dir/apps/core/...
                    if rel_path.startswith("web_face/"):
                        rel_path = rel_path[len("web_face/"):]
                    elif rel_path in ("README.md", "build_client_release.py", "SystemizeLauncher.cs", ".gitignore"):
                        # Skip root repo management files not needed by Django client
                        continue

                    parts_rel = Path(rel_path).parts
                    if any(p in PROTECTED_ITEMS for p in parts_rel):
                        continue

                    dest_file = target_dir / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)

                    try:
                        with zf.open(m) as src, open(dest_file, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                    except PermissionError:
                        # Windows file replacement fallback
                        try:
                            old_file = dest_file.with_name(dest_file.name + ".old")
                            if old_file.exists():
                                try:
                                    old_file.unlink()
                                except Exception:
                                    pass
                            dest_file.rename(old_file)
                            with zf.open(m) as src, open(dest_file, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            try:
                                old_file.unlink()
                            except Exception:
                                pass
                        except Exception as e_copy:
                            logs.append(f"⚠️ تنبيه أثناء استبدال {rel_path}: {e_copy}")
                            continue

                    extracted += 1

            logs.append(f"✓ تم استخراج وتحديث {extracted} ملفاً بنجاح.")

            # If running in client deployment (runtime/ exists or manage.pyc exists), compile to .pyc and strip .py
            is_client = (target_dir / "runtime").exists() or (target_dir / "manage.pyc").exists()
            if is_client:
                logs.append("⏳ جاري ترجمة وحماية الملفات البرمجية الجديدة (.pyc)...")
                try:
                    import compileall
                    for app_sub in [target_dir / "apps", target_dir / "config"]:
                        if app_sub.exists():
                            compileall.compile_dir(str(app_sub), force=True, legacy=True, optimize=2, quiet=1)
                    if (target_dir / "manage.py").exists():
                        compileall.compile_file(str(target_dir / "manage.py"), legacy=True, optimize=2)

                    # Remove newly extracted .py files to keep clean zero-source client environment
                    for root, dirs, files in os.walk(str(target_dir)):
                        if "runtime" in Path(root).parts:
                            continue
                        for f in files:
                            if f.endswith(".py") and f != "updater.py":
                                try:
                                    os.remove(os.path.join(root, f))
                                except Exception:
                                    pass
                    logs.append("✓ تم ترجمة وحماية ملفات النظام بنجاح (.pyc).")
                except Exception as comp_err:
                    logs.append(f"⚠️ ملاحظة أثناء الترجمة: {comp_err}")

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
    5. Updates version.json and GymProfile
    """
    from apps.core.models import GymProfile, SystemLicense
    profile = profile or GymProfile.get_solo()
    branch = profile.github_branch or "main"
    logs = []

    # Check Central Cloud updates permission
    try:
        lic = SystemLicense.get_solo()
        if not lic.updates_allowed:
            block_msg = lic.update_block_reason or "تم إيقاف التحديثات البرمجية لهذه النسخة مؤقتاً بقرار من إدارة النظام المركزية."
            logs.append(f"❌ التحديث مرفوض ومحظور: {block_msg}")
            return {
                "success": False,
                "updates_blocked": True,
                "message": block_msg,
                "logs": logs,
            }
    except Exception as exc:
        print(f"[perform_system_update] License check warning: {exc}")

    # 1. Database Backup
    logs.append("⏳ 1. جاري إنشاء نسخة احتياطية لقاعدة البيانات...")
    backup_ok, backup_path = backup_database()
    if backup_ok:
        logs.append(f"✓ تم حفظ نسخة احتياطية آمنة في: {Path(backup_path).name}")
    else:
        logs.append(f"⚠️ تحذير: {backup_path}")

    # 2. Get remote version info first for tracking
    current_info = get_current_version_info()
    api_check = check_updates_via_api(profile, current_info)
    remote_info = {
        "sha": api_check.get("remote_commit", "latest"),
        "date": api_check.get("remote_date", datetime.now().strftime("%Y-%m-%d")),
        "message": api_check.get("remote_message", "تحديث سحابي من GitHub"),
    }

    # 3. Git Pull or Zip Fallback
    pulled = False
    if current_info.get("has_git"):
        logs.append(f"⏳ 2. جاري سحب التحديثات عبر Git (Branch: {branch})...")
        run_git_command(["stash"])
        ok_pull, out_pull = run_git_command(["pull", "origin", branch], timeout=60)
        if ok_pull:
            pulled = True
            logs.append(f"✓ تم سحب التحديثات بنجاح عبر Git.")
        else:
            logs.append(f"⚠️ تعذر السحب عبر Git: {out_pull[:80]}. جاري التحديث المباشر من GitHub...")

    if not pulled:
        ok_zip, out_zip = update_via_zip_download(profile, branch, logs, remote_info)
        if not ok_zip:
            logs.append(f"❌ خطأ أثناء تطبيق التحديث: {out_zip}")
            return {
                "success": False,
                "message": f"فشل سحب التحديثات من GitHub: {out_zip}",
                "logs": logs,
            }

    # 4. Apply Migrations
    logs.append("⏳ 3. جاري تطبيق ترقيات جداول قاعدة البيانات (migrate)...")
    base_dir = Path(settings.BASE_DIR)
    python_bin = sys.executable
    if not Path(python_bin).exists():
        for cand in [base_dir / "runtime" / "python.exe", base_dir.parent / "runtime" / "python.exe"]:
            if cand.exists():
                python_bin = str(cand)
                break

    manage_file = base_dir / "manage.py"
    if not manage_file.exists():
        manage_file = base_dir / "manage.pyc"

    if manage_file.exists():
        try:
            mig_proc = subprocess.run(
                [str(python_bin), "-s", str(manage_file), "migrate", "--noinput"],
                cwd=str(base_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            if mig_proc.returncode == 0:
                logs.append("✓ تم فحص وترقية جداول قاعدة البيانات بنجاح.")
            else:
                err_msg = (mig_proc.stderr or mig_proc.stdout or "").strip()[:150]
                logs.append(f"⚠️ تنبيه أثناء ترقية قاعدة البيانات: {err_msg}")
        except Exception as e:
            logs.append(f"⚠️ تعذر تشغيل migrate تلقائياً: {str(e)}")
    else:
        logs.append("⚠️ لم يتم العثور على manage.py لتطبيق الترقيات.")

    # 4. Check & auto-install Google Contacts libraries if missing
    try:
        import googleapiclient
        import google_auth_oauthlib
    except ImportError:
        logs.append("⏳ 4. جاري فحص وتثبيت مكتبات Google Contacts في بيئة بايثون...")
        try:
            pip_proc = subprocess.run(
                [str(python_bin), "-m", "pip", "install", "--no-warn-script-location", "google-api-python-client", "google-auth-httplib2", "google-auth-oauthlib"],
                cwd=str(base_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            if pip_proc.returncode == 0:
                logs.append("✓ تم تثبيت مكتبات Google Contacts بنجاح.")
            else:
                logs.append("⚠️ تعذر تثبيت حزم Google Contacts تلقائياً (تأكد من توفر اتصال بالإنترنت).")
        except Exception as e:
            logs.append(f"⚠️ ملاحظة أثناء تثبيت الحزم: {e}")

    # 5. Refresh AI Cache
    logs.append("⏳ 4. جاري تحديث ذاكرة التعرف على الوجه...")
    try:
        from apps.face_recognition.engine import get_face_engine
        engine = get_face_engine()
        engine.refresh_cache(force=True)
        logs.append("✓ تم تحديث ذاكرة بصمات الوجه بنجاح.")
    except Exception:
        pass

    # 6. Save version.json and update GymProfile
    new_sha = remote_info.get("sha")
    if not new_sha or new_sha == "latest":
        ok_hash, out_hash = run_git_command(["rev-parse", "--short", "HEAD"])
        if ok_hash and out_hash:
            new_sha = out_hash.strip()
    if not new_sha:
        new_sha = "latest"

    new_date = remote_info.get("date") or datetime.now().strftime("%Y-%m-%d")
    new_msg = remote_info.get("message") or "تحديث تلقائي من GitHub"

    try:
        v_data = {
            "version": "v2.0",
            "commit": new_sha,
            "date": new_date,
            "message": new_msg,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(base_dir / "version.json", "w", encoding="utf-8") as vf:
            json.dump(v_data, vf, ensure_ascii=False, indent=2)
    except Exception as e:
        logs.append(f"⚠️ تنبيه: {e}")

    profile.current_version_tag = f"v2.0 ({new_sha})"
    profile.save(update_fields=["current_version_tag"])

    logs.append(f"🎉 5. اكتمل التحديث بنجاح! الإصدار: {new_sha} ({new_date})")

    return {
        "success": True,
        "message": f"تم تحديث النظام بنجاح إلى آخر إصدار ({new_sha})!",
        "new_info": {
            "commit": new_sha,
            "date": new_date,
            "message": new_msg,
            "version_tag": f"v2.0 ({new_sha})",
        },
        "logs": logs,
    }
