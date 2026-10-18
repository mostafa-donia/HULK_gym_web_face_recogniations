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
        return (
            False,
            "copied_unauthorized",
            f"تم حظر تشغيل النظام: هذا المجلد تم نسخه لجهاز كمبيوتر آخر غير مصرح به.\nكود هذا الجهاز الجديد: {current_hwid}",
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

    license_obj.tamper_hash = compute_tamper_token(
        current_hwid, "active", license_obj.license_type, license_obj.valid_until
    )
    license_obj.last_clock_check = timezone.now()
    license_obj.save()

    return True, "تم تفعيل ترخيص النظام بنجاح! شكراً لاشتراككم."
