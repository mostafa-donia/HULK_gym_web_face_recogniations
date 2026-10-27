import os
import sys
import shutil
import subprocess
import json
import time
import ssl
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.utils import timezone

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass


# ---------------------------------------------------------------------------
# Global Update State Tracker (Thread-safe & File-Backed)
# ---------------------------------------------------------------------------
_UPDATE_LOCK = threading.Lock()
_UPDATE_STATE = {
    "is_running": False,
    "stage": "idle",       # "idle", "checking", "backup", "downloading", "extracting", "compiling", "migrating", "caching", "completed", "failed"
    "stage_name": "جاهز",
    "percent": 0,
    "detail": "النظام جاهز للتحقق والتحديث",
    "logs": [],
    "success": None,
    "error": None,
    "started_at": None,
    "completed_at": None,
}


def set_update_progress(percent: int, stage: str, stage_name: str, detail: str, log_msg: str = None):
    """
    Updates live update progress state in memory and atomic progress file.
    Tracks percentage (0-100), current stage, human-readable details, and logs.
    """
    global _UPDATE_STATE
    percent = max(0, min(100, int(percent)))
    with _UPDATE_LOCK:
        _UPDATE_STATE["is_running"] = (stage not in ("idle", "completed", "failed"))
        _UPDATE_STATE["percent"] = percent
        _UPDATE_STATE["stage"] = stage
        _UPDATE_STATE["stage_name"] = stage_name
        _UPDATE_STATE["detail"] = detail
        if log_msg:
            _UPDATE_STATE["logs"].append(log_msg)
        if stage == "completed":
            _UPDATE_STATE["success"] = True
            _UPDATE_STATE["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif stage == "failed":
            _UPDATE_STATE["success"] = False
            _UPDATE_STATE["error"] = detail
            _UPDATE_STATE["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        state_copy = dict(_UPDATE_STATE)

    try:
        progress_file = Path(settings.BASE_DIR) / "update_progress.json"
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(state_copy, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_update_progress() -> dict:
    """Returns current system update progress dictionary (from memory or file fallback)."""
    global _UPDATE_STATE
    with _UPDATE_LOCK:
        state = dict(_UPDATE_STATE)
    if not state.get("is_running"):
        try:
            progress_file = Path(settings.BASE_DIR) / "update_progress.json"
            if progress_file.exists():
                with open(progress_file, "r", encoding="utf-8") as f:
                    f_state = json.load(f)
                    if f_state.get("is_running") or (f_state.get("completed_at") and not state.get("completed_at")):
                        return f_state
        except Exception:
            pass
    return state


def reset_update_progress():
    """Resets update progress to clean idle state."""
    global _UPDATE_STATE
    with _UPDATE_LOCK:
        _UPDATE_STATE = {
            "is_running": False,
            "stage": "idle",
            "stage_name": "جاهز",
            "percent": 0,
            "detail": "جاهز للبدء",
            "logs": [],
            "success": None,
            "error": None,
            "started_at": None,
            "completed_at": None,
        }
    try:
        progress_file = Path(settings.BASE_DIR) / "update_progress.json"
        if progress_file.exists():
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(_UPDATE_STATE, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _get_ssl_context() -> ssl.SSLContext:
    """
    Returns an SSL context that will not fail on Windows systems
    missing local root CA certificates.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx



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
        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=12) as resp:
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
    Tracks byte-level download percentage and file extraction progress.
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
    start_msg = f"⏳ جاري تحميل حزمة التحديث من GitHub ({owner}/{repo_name} @ {branch})..."
    logs.append(start_msg)
    set_update_progress(
        percent=30,
        stage="downloading",
        stage_name="تحميل حزمة التحديث من GitHub",
        detail="جاري الاتصال بمستودع GitHub وبدء تنزيل الملفات...",
        log_msg=start_msg,
    )

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
        "update_progress.json",
    }

    try:
        req = urllib.request.Request(
            zip_url,
            headers={"User-Agent": "Systemize-Client-Updater"}
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_zip = Path(tmp_dir) / "update.zip"
            with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=60) as resp:
                content_len = resp.headers.get("Content-Length")
                total_size = int(content_len) if content_len and content_len.isdigit() else 0
                downloaded = 0
                chunk_size = 65536
                with open(tmp_zip, "wb") as out_file:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int(30 + (downloaded / total_size) * 30)  # 30% to 60%
                            pct = min(max(pct, 30), 60)
                            mb_down = downloaded / (1024 * 1024)
                            mb_tot = total_size / (1024 * 1024)
                            set_update_progress(
                                percent=pct,
                                stage="downloading",
                                stage_name="تحميل حزمة التحديث من GitHub",
                                detail=f"تم تنزيل {mb_down:.1f} MB من {mb_tot:.1f} MB ({int(downloaded/total_size*100)}%)",
                            )
                        else:
                            mb_down = downloaded / (1024 * 1024)
                            set_update_progress(
                                percent=45,
                                stage="downloading",
                                stage_name="تحميل حزمة التحديث من GitHub",
                                detail=f"تم تنزيل {mb_down:.1f} MB من حزمة التحديث...",
                            )

            download_done_msg = "✓ تم تحميل حزمة التحديث بنجاح. جاري فحص واستخراج الملفات..."
            logs.append(download_done_msg)
            set_update_progress(
                percent=60,
                stage="extracting",
                stage_name="استخراج وفحص وتثبيت الملفات",
                detail="تم تحميل الحزمة، جاري فحص واستخراج ملفات المنظومة...",
                log_msg=download_done_msg,
            )

            with zipfile.ZipFile(tmp_zip, "r") as zf:
                members = zf.infolist()
                if not members:
                    return False, "ملف التحديث المضغوط فارغ."
                root_prefix = members[0].filename.split("/")[0] + "/"

                total_members = len(members)
                extracted = 0
                for idx, m in enumerate(members):
                    if m.is_dir():
                        continue
                    rel_path = m.filename
                    if rel_path.startswith(root_prefix):
                        rel_path = rel_path[len(root_prefix):]
                    if not rel_path:
                        continue

                    # Map web_face/ -> settings.BASE_DIR
                    if rel_path.startswith("web_face/"):
                        rel_path = rel_path[len("web_face/"):]
                    elif rel_path in ("README.md", "build_client_release.py", "SystemizeLauncher.cs", ".gitignore"):
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
                        try:
                            old_file = dest_file.with_name(dest_file.name + ".old")
                            if old_file.exists():
                                try: old_file.unlink()
                                except Exception: pass
                            dest_file.rename(old_file)
                            with zf.open(m) as src, open(dest_file, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            try: old_file.unlink()
                            except Exception: pass
                        except Exception as e_copy:
                            logs.append(f"⚠️ تنبيه أثناء استبدال {rel_path}: {e_copy}")
                            continue

                    extracted += 1
                    if idx % 15 == 0 or idx == total_members - 1:
                        pct = int(60 + (idx / max(total_members, 1)) * 15)  # 60% to 75%
                        set_update_progress(
                            percent=pct,
                            stage="extracting",
                            stage_name="استخراج وفحص وتثبيت الملفات",
                            detail=f"تثبيت وتحديث ملفات المنظومة: {extracted} من {total_members} ملف ({pct}%)",
                        )

            extract_done_msg = f"✓ تم استخراج وتحديث {extracted} ملفاً بنجاح."
            logs.append(extract_done_msg)
            set_update_progress(
                percent=75,
                stage="extracting",
                stage_name="استخراج وفحص وتثبيت الملفات",
                detail=extract_done_msg,
                log_msg=extract_done_msg,
            )

            # Bytecode compilation for protected client distributions
            is_client = (target_dir / "runtime").exists() or (target_dir / "manage.pyc").exists()
            if is_client:
                comp_msg = "⏳ جاري ترجمة وتأمين الملفات البرمجية الجديدة (.pyc)..."
                logs.append(comp_msg)
                set_update_progress(
                    percent=80,
                    stage="compiling",
                    stage_name="ترجمة وحماية الشيفرات البرمجية",
                    detail="ترجمة الشيفرات البرمجية لتسريع الأداء وحماية الكود...",
                    log_msg=comp_msg,
                )
                try:
                    import compileall
                    for app_sub in [target_dir / "apps", target_dir / "config"]:
                        if app_sub.exists():
                            compileall.compile_dir(str(app_sub), force=True, legacy=True, optimize=2, quiet=1)
                    if (target_dir / "manage.py").exists():
                        compileall.compile_file(str(target_dir / "manage.py"), legacy=True, optimize=2)

                    # Remove newly extracted .py files
                    for root, dirs, files in os.walk(str(target_dir)):
                        if "runtime" in Path(root).parts:
                            continue
                        for f in files:
                            if f.endswith(".py") and f != "updater.py":
                                try: os.remove(os.path.join(root, f))
                                except Exception: pass
                    comp_done = "✓ تم ترجمة وحماية ملفات النظام بنجاح (.pyc)."
                    logs.append(comp_done)
                    set_update_progress(
                        percent=85,
                        stage="compiling",
                        stage_name="ترجمة وحماية الشيفرات البرمجية",
                        detail=comp_done,
                        log_msg=comp_done,
                    )
                except Exception as comp_err:
                    logs.append(f"⚠️ ملاحظة أثناء الترجمة: {comp_err}")

            return True, "تم تحديث الملفات بنجاح من GitHub Archive."
    except Exception as e:
        err_msg = f"فشل تحميل وتطبيق التحديث عبر الإنترنت: {str(e)}"
        set_update_progress(
            percent=50,
            stage="failed",
            stage_name="فشل التحديث",
            detail=err_msg,
            log_msg=f"❌ {err_msg}",
        )
        return False, err_msg


def perform_system_update(profile=None) -> dict:
    """
    Executes the complete system update pipeline with live step-by-step progress tracking:
    1. License & environment check (0% - 10%)
    2. Automated SQLite database backup (10% - 25%)
    3. Git pull or zip package download with byte progress (25% - 60%)
    4. Code extraction and bytecode compilation (60% - 85%)
    5. Database migrations (85% - 95%)
    6. Face recognition cache refresh and version finalizing (95% - 100%)
    """
    from apps.core.models import GymProfile, SystemLicense

    with _UPDATE_LOCK:
        if _UPDATE_STATE.get("is_running"):
            return {
                "success": False,
                "is_running": True,
                "message": "عملية تحديث قيد التنفيذ حالياً، يرجى الانتظار حتى اكتمالها.",
                "logs": _UPDATE_STATE.get("logs", []),
            }
        _UPDATE_STATE["is_running"] = True
        _UPDATE_STATE["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _UPDATE_STATE["logs"] = []

    try:
        set_update_progress(
            percent=5,
            stage="checking",
            stage_name="فحص الاتصال والترخيص السحابي",
            detail="جاري الاتصال والتحقق من التراخيص السحابية وإصدار النظام...",
            log_msg="🚀 بدء عملية التحديث الشاملة لمنظومة Systemize...",
        )

        profile = profile or GymProfile.get_solo()
        branch = profile.github_branch or "main"
        logs = _UPDATE_STATE["logs"]

        # Central Cloud updates permission check
        try:
            lic = SystemLicense.get_solo()
            if not lic.updates_allowed:
                block_msg = lic.update_block_reason or "تم إيقاف التحديثات البرمجية لهذه النسخة مؤقتاً بقرار من إدارة النظام المركزية."
                set_update_progress(
                    percent=0,
                    stage="failed",
                    stage_name="التحديث محظور",
                    detail=block_msg,
                    log_msg=f"❌ التحديث مرفوض ومحظور: {block_msg}",
                )
                return {
                    "success": False,
                    "updates_blocked": True,
                    "message": block_msg,
                    "logs": logs,
                }
        except Exception as exc:
            print(f"[perform_system_update] License check warning: {exc}")

        # 1. Database Backup (10% - 25%)
        set_update_progress(
            percent=15,
            stage="backup",
            stage_name="حفظ نسخة احتياطية آمنة لقاعدة البيانات",
            detail="جاري إنشاء نسخة احتياطية فورية لقاعدة البيانات ومطابقتها...",
            log_msg="⏳ 1. جاري إنشاء نسخة احتياطية آمنة لقاعدة البيانات...",
        )
        backup_ok, backup_path = backup_database()
        if backup_ok:
            b_name = Path(backup_path).name
            set_update_progress(
                percent=25,
                stage="backup",
                stage_name="حفظ نسخة احتياطية آمنة لقاعدة البيانات",
                detail=f"تم حفظ نسخة احتياطية آمنة في: {b_name}",
                log_msg=f"✓ تم حفظ نسخة احتياطية آمنة في: {b_name}",
            )
        else:
            logs.append(f"⚠️ تحذير: {backup_path}")

        # 2. Remote commit metadata
        set_update_progress(
            percent=30,
            stage="checking",
            stage_name="فحص بيانات الإصدار السحابي",
            detail="جاري الاستعلام عن بيانات وتفاصيل الإصدار الأخير من GitHub...",
        )
        current_info = get_current_version_info()
        api_check = check_updates_via_api(profile, current_info)
        remote_info = {
            "sha": api_check.get("remote_commit", "latest"),
            "date": api_check.get("remote_date", datetime.now().strftime("%Y-%m-%d")),
            "message": api_check.get("remote_message", "تحديث سحابي من GitHub"),
        }

        # 3. Pull / Download (30% - 85%)
        pulled = False
        if current_info.get("has_git"):
            set_update_progress(
                percent=35,
                stage="downloading",
                stage_name="سحب التحديثات عبر Git",
                detail=f"جاري سحب التحديثات عبر Git (Branch: {branch})...",
                log_msg=f"⏳ 2. جاري سحب التحديثات عبر Git (Branch: {branch})...",
            )
            run_git_command(["stash"])
            ok_pull, out_pull = run_git_command(["pull", "origin", branch], timeout=60)
            if ok_pull:
                pulled = True
                set_update_progress(
                    percent=85,
                    stage="downloading",
                    stage_name="اكتمل سحب التحديثات عبر Git",
                    detail="تم سحب أحدث ملفات النظام من Git بنجاح.",
                    log_msg="✓ تم سحب التحديثات بنجاح عبر Git.",
                )
            else:
                logs.append(f"⚠️ تعذر السحب عبر Git: {out_pull[:80]}. جاري التحديث المباشر من GitHub...")

        if not pulled:
            ok_zip, out_zip = update_via_zip_download(profile, branch, logs, remote_info)
            if not ok_zip:
                set_update_progress(
                    percent=50,
                    stage="failed",
                    stage_name="فشل التحديث",
                    detail=out_zip,
                    log_msg=f"❌ خطأ أثناء تطبيق التحديث: {out_zip}",
                )
                return {
                    "success": False,
                    "message": f"فشل سحب التحديثات من GitHub: {out_zip}",
                    "logs": logs,
                }

        # 4. Apply Migrations (85% - 95%)
        set_update_progress(
            percent=88,
            stage="migrating",
            stage_name="ترقية جداول قاعدة البيانات (Migrations)",
            detail="جاري فحص وتطبيق ترقيات جداول قاعدة البيانات والحقول الجديدة...",
            log_msg="⏳ 3. جاري تطبيق ترقيات جداول قاعدة البيانات (migrate)...",
        )
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
                    set_update_progress(
                        percent=94,
                        stage="migrating",
                        stage_name="ترقية جداول قاعدة البيانات (Migrations)",
                        detail="تم فحص وترقية جميع جداول قاعدة البيانات بنجاح.",
                        log_msg="✓ تم فحص وترقية جداول قاعدة البيانات بنجاح.",
                    )
                else:
                    err_msg = (mig_proc.stderr or mig_proc.stdout or "").strip()[:150]
                    logs.append(f"⚠️ تنبيه أثناء ترقية قاعدة البيانات: {err_msg}")
            except Exception as e:
                logs.append(f"⚠️ تعذر تشغيل migrate تلقائياً: {str(e)}")
        else:
            logs.append("⚠️ لم يتم العثور على manage.py لتطبيق الترقيات.")

        # 5. Check & auto-install Google Contacts packages if missing
        try:
            import googleapiclient
            import google_auth_oauthlib
        except ImportError:
            set_update_progress(
                percent=95,
                stage="migrating",
                stage_name="تثبيت مكتبات التكامل",
                detail="جاري فحص وتثبيت مكتبات Google Contacts...",
                log_msg="⏳ 4. جاري فحص وتثبيت مكتبات Google Contacts في بيئة بايثون...",
            )
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
                    logs.append("⚠️ تعذر تثبيت حزم Google Contacts تلقائياً.")
            except Exception as e:
                logs.append(f"⚠️ ملاحظة أثناء تثبيت الحزم: {e}")

        # 6. Refresh AI Face Recognition Cache & Finalize (96% - 100%)
        set_update_progress(
            percent=97,
            stage="caching",
            stage_name="تحديث ذاكرة الوجه وإعدادات الإصدار",
            detail="جاري تحديث ذاكرة بصمات الوجه وكتابة بيانات الإصدار المحدث...",
            log_msg="⏳ 5. جاري تحديث ذاكرة التعرف على الوجه...",
        )
        try:
            from apps.face_recognition.engine import get_face_engine
            engine = get_face_engine()
            engine.refresh_cache(force=True)
            logs.append("✓ تم تحديث ذاكرة بصمات الوجه بنجاح.")
        except Exception:
            pass

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

        success_final_msg = f"🎉 6. اكتمل التحديث بنجاح! الإصدار: {new_sha} ({new_date})"
        logs.append(success_final_msg)
        set_update_progress(
            percent=100,
            stage="completed",
            stage_name="اكتمل التحديث بنجاح!",
            detail=f"تم تحديث النظام بنجاح إلى آخر إصدار ({new_sha}) جاهز للعمل 🚀",
            log_msg=success_final_msg,
        )

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

    except Exception as exc:
        err_str = str(exc)
        set_update_progress(
            percent=50,
            stage="failed",
            stage_name="فشل التحديث",
            detail=err_str,
            log_msg=f"❌ خطأ غير متوقع: {err_str}",
        )
        return {
            "success": False,
            "message": f"حدث خطأ أثناء التحديث: {err_str}",
            "logs": _UPDATE_STATE.get("logs", []),
        }
