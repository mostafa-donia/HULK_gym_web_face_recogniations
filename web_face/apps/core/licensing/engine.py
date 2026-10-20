import logging
from datetime import datetime, timedelta
from django.utils import timezone

from apps.core.licensing.hwid import get_hardware_fingerprint
from apps.core.licensing.crypto import (
    compute_tamper_token,
    verify_tamper_token,
    verify_offline_license_token,
)
from apps.core.licensing.remote import fetch_remote_license_status

logger = logging.getLogger(__name__)


def get_or_create_system_license():
    """
    Retrieves the SystemLicense bound to the current machine.
    If running for the first time, initializes a 7-day Free Demo.
    """
    from apps.core.models import SystemLicense

    current_hwid = get_hardware_fingerprint()
    license_obj = SystemLicense.objects.filter(machine_id=current_hwid).first()

    if not license_obj:
        # Check if any license exists (e.g. copied from another machine)
        any_license = SystemLicense.objects.first()
        if any_license:
            # An existing license belongs to another machine!
            # Keep the old one or mark as mismatched
            logger.warning(f"HWID mismatch: current {current_hwid} != existing {any_license.machine_id}")
            return any_license, False  # Indicates machine mismatch

        # Completely clean first boot: start 7-Day Free Demo
        now = timezone.now()
        demo_expiry = now + timedelta(days=7)
        tamper_sig = compute_tamper_token(current_hwid, "demo", "demo", demo_expiry)
        
        license_obj = SystemLicense.objects.create(
            machine_id=current_hwid,
            client_name="نسخة تجريبية (7 أيام)",
            status="demo",
            license_type="demo",
            valid_until=demo_expiry,
            tamper_hash=tamper_sig,
            last_clock_check=now,
            developer_contact_phone="01080922432",
        )

        # Auto-provision default demo user (demo / 1234)
        try:
            from apps.accounts.models import User, UserRole
            demo_u, _ = User.objects.get_or_create(username="demo")
            demo_u.role = UserRole.OWNER
            demo_u.is_staff = True
            demo_u.is_superuser = True
            demo_u.first_name = "مستخدم تجريبي"
            demo_u.set_password("1234")
            demo_u.save()
        except Exception as e:
            logger.warning(f"Failed to auto-create demo user: {e}")

        return license_obj, True

    return license_obj, True


def check_anti_clock_rollback(license_obj) -> bool:
    """
    Detects if the system clock was wound backwards to evade expiry.
    Checks against last_clock_check and latest DB records.
    """
    now = timezone.now()

    # 1. Check against recorded last_clock_check
    if license_obj.last_clock_check and now < (license_obj.last_clock_check - timedelta(minutes=15)):
        logger.error(f"Clock rollback detected: now ({now}) < last_check ({license_obj.last_clock_check})")
        return False

    # 2. Check against latest Payment or CheckIn in DB
    try:
        from apps.payments.models import Payment
        last_payment = Payment.objects.order_by("-payment_date").first()
        if last_payment and last_payment.payment_date:
            last_p_dt = timezone.make_aware(
                datetime.combine(last_payment.payment_date, datetime.min.time())
            )
            if now < (last_p_dt - timedelta(days=1)):
                logger.error("Clock rollback detected against recent payments!")
                return False
    except Exception:
        pass

    # Update last check
    license_obj.last_clock_check = now
    license_obj.save(update_fields=["last_clock_check"])
    return True


def check_new_machine_grace(current_hwid: str, license_obj) -> tuple[bool, int, int]:
    """
    Checks if a newly copied machine is within its 24-hour (1-day) temporary emergency grace period.
    Returns (in_grace_period: bool, remaining_hours: int, remaining_minutes: int).
    """
    import os, json, hashlib
    from django.conf import settings

    grace_dir = os.path.join(settings.BASE_DIR, "runtime")
    if not os.path.exists(grace_dir):
        grace_dir = os.path.join(settings.BASE_DIR)
    grace_file = os.path.join(grace_dir, ".machine_grace.json")

    now = timezone.now()
    now_iso = now.isoformat()

    records = {}
    if os.path.exists(grace_file):
        try:
            with open(grace_file, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            records = {}

    mach_rec = records.get(current_hwid)
    if not mach_rec:
        sig = hashlib.sha256(f"GRACE_{current_hwid}_{now_iso}_SYSTEMIZE".encode("utf-8")).hexdigest()
        records[current_hwid] = {
            "first_seen": now_iso,
            "last_seen": now_iso,
            "grace_hours": 24,
            "sig": sig,
        }
        try:
            with open(grace_file, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
        except Exception:
            pass
        return True, 24, 0

    first_seen_str = mach_rec.get("first_seen")
    last_seen_str = mach_rec.get("last_seen")
    expected_sig = hashlib.sha256(f"GRACE_{current_hwid}_{first_seen_str}_SYSTEMIZE".encode("utf-8")).hexdigest()

    if mach_rec.get("sig") != expected_sig:
        return False, 0, 0

    try:
        first_seen = datetime.fromisoformat(first_seen_str)
        if timezone.is_naive(first_seen):
            first_seen = timezone.make_aware(first_seen)
    except Exception:
        return False, 0, 0

    if last_seen_str:
        try:
            last_seen = datetime.fromisoformat(last_seen_str)
            if timezone.is_naive(last_seen):
                last_seen = timezone.make_aware(last_seen)
            if now < (last_seen - timedelta(minutes=10)):
                return False, 0, 0
        except Exception:
            pass

    mach_rec["last_seen"] = now_iso
    try:
        with open(grace_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
    except Exception:
        pass

    elapsed = (now - first_seen).total_seconds()
    total_grace_seconds = 24 * 3600
    remaining_seconds = total_grace_seconds - elapsed

    if remaining_seconds > 0:
        hours = int(remaining_seconds // 3600)
        minutes = int((remaining_seconds % 3600) // 60)
        return True, hours, minutes
    else:
        return False, 0, 0


def validate_system_license(allow_remote_sync: bool = True) -> tuple[bool, str, str, dict]:
    """
    Master License Validation Engine.
    Returns:
    (is_valid: bool, status_code: str, user_friendly_message: str, license_info: dict)
    """
    from apps.core.models import SystemLicense

    current_hwid = get_hardware_fingerprint()
    license_obj, is_matching_machine = get_or_create_system_license()

    if not is_matching_machine or license_obj.machine_id != current_hwid:
        in_grace, g_hours, g_minutes = check_new_machine_grace(current_hwid, license_obj)
        if in_grace:
            msg = f"⚠️ تم تشغيل النظام على جهاز كمبيوتر جديد ({current_hwid}). النظام يعمل بفترة سماح مؤقتة لمدة 24 ساعة (متبقي: {g_hours} ساعة و {g_minutes} دقيقة). يرجى تزويد المطور بكود الجهاز لتفعيل الترخيص قبل انتهاء المهلة."
            info = {
                "machine_id": current_hwid,
                "status": "grace",
                "is_grace_period": True,
                "grace_remaining_hours": g_hours,
                "grace_remaining_minutes": g_minutes,
                "phone": license_obj.developer_contact_phone,
                "features": {
                    "face_recognition": True,
                    "gate_relay": True,
                    "whatsapp": True,
                    "telegram": True,
                    "bar": True,
                    "payroll": True,
                    "retention": True,
                    "reports": True,
                    "barcode": True,
                    "expenses": True,
                    "multi_branch": True,
                },
            }
            return True, "grace_period", msg, info
        else:
            return (
                False,
                "copied_unauthorized",
                f"انتهت فترة السماح المؤقتة (24 ساعة) لهذا الجهاز الجديد ({current_hwid}). يرجى تزويد المطور بكود الجهاز لتفعيل الترخيص الدائم.",
                {
                    "machine_id": current_hwid,
                    "status": "unauthorized",
                    "phone": license_obj.developer_contact_phone,
                },
            )

    # 1. Anti-Tamper Hash Verification
    is_tamper_valid = verify_tamper_token(
        license_obj.machine_id,
        license_obj.status,
        license_obj.license_type,
        license_obj.valid_until,
        license_obj.tamper_hash,
    )

    if not is_tamper_valid:
        return (
            False,
            "tampered",
            "تم اكتشاف محاولة تعديل غير مصرح بها في ملفات الترخيص والأمان. يرجى التواصل مع المطور لإعادة التفعيل.",
            {
                "machine_id": current_hwid,
                "status": "tampered",
                "phone": license_obj.developer_contact_phone,
            },
        )

    # 2. Anti-Clock Rollback Verification
    if not check_anti_clock_rollback(license_obj):
        return (
            False,
            "clock_rollback",
            "تم اكتشاف تراجع في تاريخ أو وقت الويندوز. يرجى ضبط توقيت الجهاز الصحيح للتمكن من المتابعة.",
            {
                "machine_id": current_hwid,
                "status": "clock_rollback",
                "phone": license_obj.developer_contact_phone,
            },
        )

    # 3. Online Remote Control Center Sync (if configured)
    if allow_remote_sync and license_obj.remote_control_url:
        sync_ok, remote_data, sync_msg = fetch_remote_license_status(
            license_obj.remote_control_url, current_hwid, license_obj.client_name
        )
        if sync_ok and remote_data:
            # Process Developer Remote Overrides
            new_status = remote_data.get("status", license_obj.status).lower().strip()
            new_type = remote_data.get("license_type", license_obj.license_type).lower().strip()
            new_msg = remote_data.get("message") or remote_data.get("developer_message", "")
            valid_until_str = remote_data.get("valid_until")

            if valid_until_str:
                try:
                    parsed_dt = datetime.fromisoformat(valid_until_str)
                    if timezone.is_naive(parsed_dt):
                        parsed_dt = timezone.make_aware(parsed_dt)
                    license_obj.valid_until = parsed_dt
                except Exception:
                    pass

            license_obj.status = new_status
            license_obj.license_type = new_type
            if new_msg:
                license_obj.developer_notes = new_msg

            # Remote Features Toggle
            ft = remote_data.get("features", {})
            if isinstance(ft, dict):
                if "face_recognition" in ft or "face" in ft:
                    license_obj.feature_face_recognition = bool(ft.get("face_recognition", ft.get("face", True)))
                if "gate_relay" in ft:
                    license_obj.feature_gate_relay = bool(ft["gate_relay"])
                if "whatsapp" in ft:
                    license_obj.feature_whatsapp = bool(ft["whatsapp"])
                if "telegram" in ft:
                    license_obj.feature_telegram = bool(ft["telegram"])
                if "bar" in ft:
                    license_obj.feature_bar = bool(ft["bar"])
                if "payroll" in ft:
                    license_obj.feature_payroll = bool(ft["payroll"])
                if "retention" in ft:
                    license_obj.feature_retention = bool(ft["retention"])
                if "reports" in ft:
                    license_obj.feature_reports = bool(ft["reports"])
                if "barcode" in ft or "barcode_scanner" in ft:
                    license_obj.feature_barcode = bool(ft.get("barcode", ft.get("barcode_scanner", True)))
                if "expenses" in ft:
                    license_obj.feature_expenses = bool(ft["expenses"])
                if "multi_branch" in ft:
                    license_obj.feature_multi_branch = bool(ft["multi_branch"])

            # Sync Remote Branches
            branches_data = remote_data.get("branches")
            if isinstance(branches_data, list) and branches_data:
                from apps.core.models import Branch
                for b in branches_data:
                    code = (b.get("code") or "").strip().upper()
                    name = (b.get("name") or "").strip()
                    if not code or not name:
                        continue
                    Branch.objects.update_or_create(
                        code=code,
                        defaults={
                            "name": name,
                            "phone": b.get("phone", ""),
                            "address": b.get("address", ""),
                            "manager_name": b.get("manager_name", ""),
                            "is_main": bool(b.get("is_main", False)),
                            "is_active": bool(b.get("is_active", True)),
                        }
                    )

            # Sync Managed Users & Passwords from Control Center
            users_data = remote_data.get("managed_users")
            if isinstance(users_data, list) and users_data:
                from apps.accounts.models import User, UserRole
                from apps.core.models import Branch
                for u in users_data:
                    uname = (u.get("username") or "").strip().lower()
                    if not uname:
                        continue
                    pwd = u.get("password")
                    role_str = (u.get("role") or "RECEPTION").strip().upper()
                    if role_str not in [UserRole.OWNER, UserRole.MANAGER, UserRole.RECEPTION]:
                        role_str = UserRole.RECEPTION

                    b_code = (u.get("branch_code") or "").strip().upper()
                    branch = Branch.objects.filter(code=b_code).first() if b_code else None

                    user_obj = User.objects.filter(username=uname).first()
                    if not user_obj:
                        user_obj = User.objects.create(
                            username=uname,
                            role=role_str,
                            branch=branch,
                            first_name=u.get("full_name", uname),
                            is_staff=True if role_str in [UserRole.OWNER, UserRole.MANAGER] else False,
                        )
                        if pwd:
                            user_obj.set_password(pwd)
                            user_obj.save()
                    else:
                        user_obj.role = role_str
                        user_obj.branch = branch
                        if u.get("full_name"):
                            user_obj.first_name = u["full_name"]
                        if role_str in [UserRole.OWNER, UserRole.MANAGER]:
                            user_obj.is_staff = True
                        if pwd:
                            user_obj.set_password(pwd)
                        user_obj.save()

            license_obj.tamper_hash = compute_tamper_token(
                current_hwid, license_obj.status, license_obj.license_type, license_obj.valid_until
            )
            license_obj.last_remote_sync = timezone.now()
            license_obj.save()

    info_dict = {
        "machine_id": current_hwid,
        "client_name": license_obj.client_name,
        "status": license_obj.status,
        "license_type": license_obj.license_type,
        "valid_until": license_obj.valid_until,
        "phone": license_obj.developer_contact_phone,
        "developer_notes": license_obj.developer_notes,
        "features": {
            "face_recognition": license_obj.feature_face_recognition,
            "gate_relay": license_obj.feature_gate_relay,
            "whatsapp": license_obj.feature_whatsapp,
            "telegram": license_obj.feature_telegram,
            "bar": license_obj.feature_bar,
            "payroll": license_obj.feature_payroll,
            "retention": license_obj.feature_retention,
            "reports": license_obj.feature_reports,
            "barcode": license_obj.feature_barcode,
            "expenses": license_obj.feature_expenses,
            "multi_branch": license_obj.feature_multi_branch,
        },
    }

    # 4. Check Developer Remote Suspension
    if license_obj.status in ["suspended", "disabled"]:
        msg = license_obj.developer_notes or "تم إيقاف تشغيل هذه النسخة مؤقتاً من قبل المطور. يرجى التواصل لتجديد الاشتراك."
        return False, "suspended", msg, info_dict

    # 5. Offline Tolerance Check (Checks Expiration Period)
    if license_obj.license_type != "lifetime" and license_obj.valid_until:
        now = timezone.now()
        if now > license_obj.valid_until:
            license_obj.status = "expired"
            license_obj.tamper_hash = compute_tamper_token(
                current_hwid, "expired", license_obj.license_type, license_obj.valid_until
            )
            license_obj.save(update_fields=["status", "tamper_hash"])

            if license_obj.license_type == "demo":
                msg = f"انتهت الفترة التجريبية المجانية (7 أيام).\nلتفعيل النسخة الدائمة أو الاشتراك الشهري، يرجى تزويد المطور بكود جهازك: {current_hwid}"
                return False, "demo_expired", msg, info_dict
            else:
                msg = f"انتهت فترة اشتراكك في نظام Systemize بتاريخ {license_obj.valid_until.strftime('%Y-%m-%d')}.\nيرجى التواصل مع المطور لتجديد الاشتراك."
                return False, "subscription_expired", msg, info_dict

    # If demo is still active, compute remaining days
    if license_obj.status == "demo" and license_obj.valid_until:
        rem_seconds = (license_obj.valid_until - timezone.now()).total_seconds()
        info_dict["remaining_demo_days"] = max(0, int(rem_seconds // 86400))
        info_dict["remaining_demo_hours"] = max(0, int((rem_seconds % 86400) // 3600))

    return True, "valid", "الترخيص سارٍ ويعمل بنجاح.", info_dict


def activate_offline_token(token_str: str) -> tuple[bool, str]:
    """
    Activates an offline signed license token on the local machine.
    """
    from apps.core.models import SystemLicense

    current_hwid = get_hardware_fingerprint()
    ok, payload, err = verify_offline_license_token(token_str, current_hwid)
    if not ok:
        return False, err

    license_obj, _ = get_or_create_system_license()

    # Apply Token Payload
    license_obj.machine_id = current_hwid
    license_obj.client_name = payload.get("cn", license_obj.client_name)
    license_obj.license_type = payload.get("lt", "monthly")
    license_obj.status = "active"

    exp_str = payload.get("exp")
    if exp_str and exp_str != "NONE":
        try:
            parsed_dt = datetime.fromisoformat(exp_str)
            if timezone.is_naive(parsed_dt):
                parsed_dt = timezone.make_aware(parsed_dt)
            license_obj.valid_until = parsed_dt
        except Exception:
            license_obj.valid_until = None
    else:
        license_obj.valid_until = None

    ft = payload.get("ft", {})
    if isinstance(ft, dict):
        license_obj.feature_face_recognition = bool(ft.get("face_recognition", ft.get("face", True)))
        license_obj.feature_gate_relay = bool(ft.get("gate_relay", True))
        license_obj.feature_whatsapp = bool(ft.get("whatsapp", True))
        license_obj.feature_telegram = bool(ft.get("telegram", True))
        license_obj.feature_bar = bool(ft.get("bar", True))
        license_obj.feature_payroll = bool(ft.get("payroll", True))
        license_obj.feature_retention = bool(ft.get("retention", True))
        license_obj.feature_reports = bool(ft.get("reports", True))
        license_obj.feature_barcode = bool(ft.get("barcode", ft.get("barcode_scanner", True)))
        license_obj.feature_expenses = bool(ft.get("expenses", True))
        license_obj.feature_multi_branch = bool(ft.get("multi_branch", False))

    license_obj.tamper_hash = compute_tamper_token(
        current_hwid, "active", license_obj.license_type, license_obj.valid_until
    )
    license_obj.last_clock_check = timezone.now()
    license_obj.save()

    return True, "تم تفعيل ترخيص النظام بنجاح! شكراً لاشتراككم."
