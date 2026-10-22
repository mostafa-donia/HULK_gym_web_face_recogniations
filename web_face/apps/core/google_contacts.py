import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

GOOGLE_CONTACTS_SCOPES = ["https://www.googleapis.com/auth/contacts"]


def ensure_google_libraries_installed() -> Tuple[bool, str]:
    """
    Checks if Google API and OAuth client libraries are installed.
    If missing, attempts to pip install them automatically.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from google_auth_oauthlib.flow import InstalledAppFlow
        return True, "مكتبات Google Contacts مثبتة وجاهزة للعمل بنجاح."
    except ImportError:
        pass

    try:
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-warn-script-location",
            "google-api-python-client",
            "google-auth-httplib2",
            "google-auth-oauthlib",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode == 0:
            return True, "تم تثبيت مكتبات Google Contacts بنجاح في بيئة بايثون!"
        return False, f"فشل تثبيت الحزم عبر pip: {res.stderr or res.stdout}"
    except Exception as exc:
        return False, f"حدث خطأ أثناء محاولة التثبيت التلقائي: {exc}"



def resolve_google_contact_paths() -> Tuple[Path, Path]:
    """
    Finds existing credentials.json and token.json across web data directories
    or legacy v1 directories.
    """
    base_dir = Path(settings.BASE_DIR)
    candidates_credentials = [
        base_dir / "data" / "credentials.json",
        base_dir / "credentials.json",
        base_dir.parent / "old" / "v1" / "credentials.json",
        base_dir.parent / "v1" / "data" / "credentials.json",
    ]
    candidates_token = [
        base_dir / "data" / "token.json",
        base_dir / "token.json",
        base_dir.parent / "old" / "v1" / "token.json",
        base_dir.parent / "v1" / "data" / "token.json",
    ]

    target_data_dir = base_dir / "data"
    target_data_dir.mkdir(parents=True, exist_ok=True)

    cred_target = target_data_dir / "credentials.json"
    token_target = target_data_dir / "token.json"

    if not cred_target.exists():
        for c in candidates_credentials:
            if c.exists() and c != cred_target:
                try:
                    cred_target.write_bytes(c.read_bytes())
                    break
                except Exception as e:
                    logger.warning("Could not copy credentials from %s: %s", c, e)

    if not token_target.exists():
        for t in candidates_token:
            if t.exists() and t != token_target:
                try:
                    token_target.write_bytes(t.read_bytes())
                    break
                except Exception as e:
                    logger.warning("Could not copy token from %s: %s", t, e)

    return cred_target, token_target


def _mirror_google_files_to_dist(cred_path: Path, token_path: Path) -> None:
    """Mirrors credentials.json and token.json between web_face/data and dist/HULK_GYM/data if present."""
    try:
        base_dir = Path(settings.BASE_DIR)
        other_dirs = [
            base_dir.parent / "dist" / "HULK_GYM" / "data",
            base_dir.parent / "web_face" / "data",
        ]
        for d in other_dirs:
            if d.parent.exists() and d.resolve() != cred_path.parent.resolve():
                d.mkdir(parents=True, exist_ok=True)
                if cred_path.exists():
                    (d / "credentials.json").write_bytes(cred_path.read_bytes())
                if token_path.exists():
                    (d / "token.json").write_bytes(token_path.read_bytes())
                elif (d / "token.json").exists():
                    try:
                        (d / "token.json").unlink()
                    except Exception:
                        pass
    except Exception as exc:
        logger.debug("Mirror google files notice: %s", exc)


def get_google_contacts_service() -> Tuple[Optional[Any], str]:
    """
    Builds and returns an authorized Google People API service instance.
    Refreshes expired tokens automatically using refresh_token.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as e:
        logger.warning("Google contacts libraries missing: %s. Attempting auto-install...", e)
        ok_install, _ = ensure_google_libraries_installed()
        if ok_install:
            try:
                from google.auth.transport.requests import Request
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
            except ImportError:
                return None, f"مكتبات Google Contacts غير مثبتة في بيئة بايثون ({e})."
        else:
            return None, f"مكتبات Google Contacts غير مثبتة في بيئة بايثون ({e})."

    cred_path, token_path = resolve_google_contact_paths()

    if not cred_path.exists():
        return None, f"ملف credentials.json غير موجود في {cred_path}"

    if not token_path.exists():
        return None, f"ملف token.json غير موجود (يرجى الضغط على زر ربط حساب Gmail جديد)"

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), GOOGLE_CONTACTS_SCOPES)
        if not creds:
            return None, "تعذر قراءة بيانات الاعتماد من token.json."

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    token_path.write_text(creds.to_json(), encoding="utf-8")
                    _mirror_google_files_to_dist(cred_path, token_path)
                except Exception as refresh_err:
                    return None, f"فشل تجديد التوكن تلقائياً (يرجى إعادة ربط حساب Gmail): {refresh_err}"
            else:
                return None, "رمز المصادقة منتهي ولا يحتوي على refresh_token صالح. يرجى إعادة ربط حساب Gmail."

        service = build("people", "v1", credentials=creds, cache_discovery=False)
        return service, "جاهز"
    except Exception as exc:
        logger.exception("Error initializing Google Contacts service: %s", exc)
        return None, f"خطأ أثناء الاتصال بخدمة جوجل: {exc}"


def check_google_contacts_status() -> Dict[str, Any]:
    """
    Returns full status dictionary of Google Contacts connectivity,
    extracted OAuth client details, file locations, and member sync counts.
    """
    from apps.members.models import Member

    cred_path, token_path = resolve_google_contact_paths()
    total_members = Member.objects.count()
    synced_members = Member.objects.filter(google_contact_synced_at__isnull=False).count()
    pending_members = Member.objects.filter(google_contact_synced_at__isnull=True).count()

    client_id = ""
    client_secret = ""
    project_id = ""
    raw_credentials_json = ""
    raw_token_json = ""

    if cred_path.exists():
        try:
            raw_credentials_json = cred_path.read_text(encoding="utf-8").strip()
            data = json.loads(raw_credentials_json)
            block = data.get("installed") or data.get("web") or data
            if isinstance(block, dict):
                client_id = block.get("client_id", "")
                client_secret = block.get("client_secret", "")
                project_id = block.get("project_id", "")
        except Exception:
            pass

    if token_path.exists():
        try:
            raw_token_json = token_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    info = {
        "credentials_exist": cred_path.exists(),
        "token_exist": token_path.exists(),
        "credentials_path": str(cred_path),
        "token_path": str(token_path),
        "client_id": client_id,
        "client_secret": client_secret,
        "project_id": project_id,
        "raw_credentials_json": raw_credentials_json,
        "raw_token_json": raw_token_json,
        "connected": False,
        "remote_contacts_count": 0,
        "message": "",
        "total_members": total_members,
        "synced_members": synced_members,
        "pending_members": pending_members,
        "libs_installed": True,
        "libs_missing": False,
    }

    try:
        import googleapiclient
        import google_auth_oauthlib
    except ImportError:
        info["libs_installed"] = False
        info["libs_missing"] = True
        info["message"] = "مكتبات Google Contacts غير مثبتة في بيئة بايثون (اضغط على زر التثبيت التلقائي أدناه)."
        return info

    if not cred_path.exists():
        info["message"] = "بيانات الربط (credentials.json / Client ID) غير مضافة بعد."
        return info

    if not token_path.exists():
        info["message"] = "ملف credentials.json جاهز — اضغط على (ربط حساب Gmail جديد) لتسجيل الدخول."
        return info

    service, msg = get_google_contacts_service()
    if not service:
        info["message"] = msg
        if "غير مثبتة" in msg:
            info["libs_installed"] = False
            info["libs_missing"] = True
        return info

    try:
        res = service.people().connections().list(
            resourceName="people/me",
            pageSize=1,
            personFields="names"
        ).execute()
        remote_count = res.get("totalPeople", res.get("totalItems", 0))
        info["connected"] = True
        info["remote_contacts_count"] = remote_count
        info["message"] = f"متصل بالخدمة بنجاح ({remote_count:,} جهة اتصال في حساب جوجل)."
    except Exception as e:
        info["connected"] = True
        info["message"] = f"متصل ولكن تعذر جلب إجمالي جهات الاتصال: {e}"

    return info


def save_google_credentials_from_fields(
    client_id: str,
    client_secret: str,
    project_id: str = "gym-contacts-sync",
) -> Tuple[bool, str]:
    """
    Generates and saves a standard Google OAuth Desktop credentials.json file
    from Client ID, Client Secret, and Project ID.
    """
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    project_id = (project_id or "gym-contacts-sync").strip() or "gym-contacts-sync"

    if not client_id or not client_secret:
        return False, "يرجى إدخال كلاً من Client ID و Client Secret."

    payload = {
        "installed": {
            "client_id": client_id,
            "project_id": project_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"],
        }
    }

    cred_path, token_path = resolve_google_contact_paths()
    cred_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _mirror_google_files_to_dist(cred_path, token_path)
    return True, "تم حفظ بيانات Client ID و Client Secret في ملف credentials.json بنجاح."


def save_google_raw_json(
    raw_credentials: str = "",
    raw_token: str = "",
) -> Tuple[bool, str]:
    """
    Validates and saves raw JSON strings directly into credentials.json and/or token.json.
    """
    cred_path, token_path = resolve_google_contact_paths()
    saved_parts = []

    if raw_credentials and raw_credentials.strip():
        try:
            parsed_cred = json.loads(raw_credentials.strip())
            cred_path.write_text(json.dumps(parsed_cred, indent=2, ensure_ascii=False), encoding="utf-8")
            saved_parts.append("credentials.json")
        except Exception as e:
            return False, f"صيغة JSON غير صحيحة في ملف credentials.json: {e}"

    if raw_token and raw_token.strip():
        try:
            parsed_tok = json.loads(raw_token.strip())
            token_path.write_text(json.dumps(parsed_tok, indent=2, ensure_ascii=False), encoding="utf-8")
            saved_parts.append("token.json")
        except Exception as e:
            return False, f"صيغة JSON غير صحيحة في ملف token.json: {e}"

    if not saved_parts:
        return False, "لم يتم إدخال أي محتوى JSON للحفظ."

    _mirror_google_files_to_dist(cred_path, token_path)
    return True, f"تم حفظ وتحديث ({' + '.join(saved_parts)}) بنجاح."


def authorize_new_gmail_interactive(reset_members_sync: bool = False) -> Tuple[bool, str]:
    """
    Launches the interactive Google OAuth browser flow on the local machine
    so the user can sign in with a new Gmail account (for another business/gym)
    and automatically generates a fresh token.json.
    """
    cred_path, token_path = resolve_google_contact_paths()
    if not cred_path.exists():
        return False, "ملف credentials.json غير موجود. يرجى رفع الملف أو إدخال Client ID و Client Secret أولاً."

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), GOOGLE_CONTACTS_SCOPES)
        creds = flow.run_local_server(
            port=0,
            prompt="consent select_account",
            access_type="offline",
            open_browser=True,
        )
        token_path.write_text(creds.to_json(), encoding="utf-8")
        _mirror_google_files_to_dist(cred_path, token_path)

        if reset_members_sync:
            from apps.members.models import Member
            Member.objects.all().update(google_contact_synced_at=None)

        return True, "تم تسجيل الدخول بحساب Gmail الجديد وتوليد ملف token.json بنجاح!"
    except Exception as exc:
        logger.exception("Error during interactive Google OAuth flow: %s", exc)
        return False, f"تعذر إكمال تسجيل الدخول عبر جوجل: {exc}"


def disconnect_google_account(reset_members_sync: bool = True) -> Tuple[bool, str]:
    """
    Deletes token.json to unlink the current Gmail account and optionally resets
    member sync timestamps so they can be synced cleanly to a new Gmail account.
    """
    cred_path, token_path = resolve_google_contact_paths()
    try:
        if token_path.exists():
            token_path.unlink()
        _mirror_google_files_to_dist(cred_path, token_path)
        if reset_members_sync:
            from apps.members.models import Member
            Member.objects.all().update(google_contact_synced_at=None)
        return True, "تم فصل حساب Gmail الحالي وحذف token.json بنجاح (جاهز لربط حساب جديد)."
    except Exception as exc:
        return False, f"تعذر حذف ملف التوكن: {exc}"


def sync_single_member_to_google(member: Any) -> Tuple[bool, str]:
    """
    Syncs a single Member instance to Google Contacts.
    Updates member.google_contact_synced_at upon success.
    """
    service, msg = get_google_contacts_service()
    if not service:
        return False, msg

    name = str(member.name or "").strip()
    mobile = str(member.mobile or "").strip()

    if not name or not mobile:
        return False, "اسم العضو أو رقم الهاتف فارغ."

    contact_body = {
        "names": [{"givenName": name}],
        "phoneNumbers": [{"value": mobile}],
    }

    try:
        service.people().createContact(body=contact_body).execute()
        member.google_contact_synced_at = timezone.now()
        member.save(update_fields=["google_contact_synced_at"])
        return True, f"تمت مزامنة العضو {name} ({mobile}) بنجاح."
    except Exception as exc:
        logger.warning("Google Contacts createContact error for %s: %s", name, exc)
        return False, f"فشل إنشاء جهة الاتصال: {exc}"


def trigger_async_member_google_sync(member: Any) -> None:
    """
    Fires a background daemon thread to sync a newly added or updated member's phone number
    to Google Contacts immediately without blocking the HTTP response.
    """
    if not member or not getattr(member, "mobile", None):
        return
    try:
        threading.Thread(target=sync_single_member_to_google, args=(member,), daemon=True).start()
    except Exception as exc:
        logger.debug("Could not start async Google sync thread: %s", exc)


def sync_all_google_contacts(force: bool = False) -> Tuple[int, int, int, List[str]]:
    """
    Syncs members to Google Contacts.
    If force is False, only syncs members with google_contact_synced_at=None.
    If force is True, attempts to sync all members.
    Returns: (synced_count, skipped_count, failed_count, error_messages)
    """
    from apps.members.models import Member

    service, msg = get_google_contacts_service()
    if not service:
        return 0, 0, 0, [msg]

    if force:
        queryset = Member.objects.all().order_by("id")
    else:
        queryset = Member.objects.filter(google_contact_synced_at__isnull=True).order_by("id")

    synced_count = 0
    skipped_count = 0
    failed_count = 0
    errors: List[str] = []

    for member in queryset:
        name = str(member.name or "").strip()
        mobile = str(member.mobile or "").strip()

        if not name or not mobile:
            skipped_count += 1
            continue

        contact_body = {
            "names": [{"givenName": name}],
            "phoneNumbers": [{"value": mobile}],
        }

        try:
            service.people().createContact(body=contact_body).execute()
            member.google_contact_synced_at = timezone.now()
            member.save(update_fields=["google_contact_synced_at"])
            synced_count += 1
        except Exception as exc:
            failed_count += 1
            if len(errors) < 5:
                errors.append(f"{name}: {exc}")

    return synced_count, skipped_count, failed_count, errors
