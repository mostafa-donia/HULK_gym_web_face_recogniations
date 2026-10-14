import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

GOOGLE_CONTACTS_SCOPES = ["https://www.googleapis.com/auth/contacts"]


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


def get_google_contacts_service() -> Tuple[Optional[Any], str]:
    """
    Builds and returns an authorized Google People API service instance.
    Refreshes expired tokens automatically using refresh_token.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None, "مكتبات Google Contacts غير مثبتة في بيئة بايثون."

    cred_path, token_path = resolve_google_contact_paths()

    if not cred_path.exists():
        return None, f"ملف credentials.json غير موجود في {cred_path}"

    if not token_path.exists():
        return None, f"ملف token.json غير موجود في {token_path}"

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), GOOGLE_CONTACTS_SCOPES)
        if not creds:
            return None, "تعذر قراءة بيانات الاعتماد من token.json."

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    token_path.write_text(creds.to_json(), encoding="utf-8")
                except Exception as refresh_err:
                    return None, f"فشل تجديد التوكن تلقائياً: {refresh_err}"
            else:
                return None, "رمز المصادقة منتهي ولا يحتوي على refresh_token صالح."

        service = build("people", "v1", credentials=creds, cache_discovery=False)
        return service, "جاهز"
    except Exception as exc:
        logger.exception("Error initializing Google Contacts service: %s", exc)
        return None, f"خطأ أثناء الاتصال بخدمة جوجل: {exc}"


def check_google_contacts_status() -> Dict[str, Any]:
    """
    Returns full status dictionary of Google Contacts connectivity,
    file locations, and member sync counts.
    """
    from apps.members.models import Member

    cred_path, token_path = resolve_google_contact_paths()
    total_members = Member.objects.count()
    synced_members = Member.objects.filter(google_contact_synced_at__isnull=False).count()
    pending_members = Member.objects.filter(google_contact_synced_at__isnull=True).count()

    info = {
        "credentials_exist": cred_path.exists(),
        "token_exist": token_path.exists(),
        "credentials_path": str(cred_path),
        "token_path": str(token_path),
        "connected": False,
        "remote_contacts_count": 0,
        "message": "",
        "total_members": total_members,
        "synced_members": synced_members,
        "pending_members": pending_members,
    }

    if not cred_path.exists() or not token_path.exists():
        info["message"] = "ملفات الربط (credentials.json أو token.json) غير مكتملة."
        return info

    service, msg = get_google_contacts_service()
    if not service:
        info["message"] = msg
        return info

    try:
        # Check actual remote contacts count
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
