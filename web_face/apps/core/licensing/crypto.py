import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

# Internal Master Signing Salt - Developer Private Salt
_DEVELOPER_MASTER_SECRET = b"HULK_GYM_MASTER_SECURE_KEY_2026_@ANTIGRAVITY_PROTECT"

def _sign_payload(data_str: str) -> str:
    """Signs an arbitrary payload string using HMAC-SHA256."""
    return hmac.new(_DEVELOPER_MASTER_SECRET, data_str.encode("utf-8"), hashlib.sha256).hexdigest()

def normalize_date_for_hash(dt_or_iso) -> str:
    """Normalizes any datetime or iso string into UTC 'YYYY-MM-DD HH:MM:SS'."""
    if not dt_or_iso or dt_or_iso == "NONE":
        return "NONE"
    if isinstance(dt_or_iso, str):
        try:
            dt = datetime.fromisoformat(dt_or_iso)
        except Exception:
            return dt_or_iso.split(".")[0].strip()
    else:
        dt = dt_or_iso
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def compute_tamper_token(machine_id: str, status: str, license_type: str, valid_until) -> str:
    """Computes tamper hash stored in the local DB to detect manual SQLite editing."""
    normalized_date = normalize_date_for_hash(valid_until)
    data_str = f"{machine_id}::{status}::{license_type}::{normalized_date}"
    return _sign_payload(data_str)

def verify_tamper_token(machine_id: str, status: str, license_type: str, valid_until, token: str) -> bool:
    """Verifies that the database record has not been modified manually by the client."""
    if not token:
        return False
    expected = compute_tamper_token(machine_id, status, license_type, valid_until)
    return hmac.compare_digest(expected, token)

def generate_offline_license_token(
    machine_id: str,
    client_name: str,
    license_type: str,
    valid_until_iso: str,
    features: dict = None,
) -> str:
    """
    Generates an encrypted/signed offline license token for the client.
    Can be pasted directly into the system without internet.
    """
    raw_ft = features or {}
    clean_ft = {
        "face": bool(raw_ft.get("face", raw_ft.get("face_recognition", True))),
        "face_recognition": bool(raw_ft.get("face_recognition", raw_ft.get("face", True))),
        "gate_relay": bool(raw_ft.get("gate_relay", raw_ft.get("gate", True))),
        "whatsapp": bool(raw_ft.get("whatsapp", True)),
        "telegram": bool(raw_ft.get("telegram", True)),
        "bar": bool(raw_ft.get("bar", True)),
        "payroll": bool(raw_ft.get("payroll", True)),
        "retention": bool(raw_ft.get("retention", True)),
        "reports": bool(raw_ft.get("reports", True)),
        "barcode": bool(raw_ft.get("barcode", raw_ft.get("barcode_scanner", True))),
        "expenses": bool(raw_ft.get("expenses", True)),
    }
    payload = {
        "mid": machine_id.strip(),
        "cn": client_name.strip(),
        "lt": license_type.strip(),  # demo, monthly, yearly, lifetime
        "exp": valid_until_iso or "NONE",
        "ft": clean_ft,
        "iss": datetime.now(timezone.utc).isoformat(),
    }
    json_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = _sign_payload(json_str)
    
    combined = f"{json_str}:::{sig}"
    token_b64 = base64.urlsafe_b64encode(combined.encode("utf-8")).decode("utf-8").rstrip("=")
    return f"SYSTEMIZE-LIC-{token_b64}"

def verify_offline_license_token(token: str, current_machine_id: str) -> tuple[bool, dict, str]:
    """
    Verifies an offline license token against the current machine HWID.
    Returns: (is_valid, payload_dict, message)
    """
    token = token.strip()
    if token.startswith("SYSTEMIZE-LIC-"):
        raw_b64 = token[len("SYSTEMIZE-LIC-") :]
    elif token.startswith("HULK-LIC-"):
        raw_b64 = token[len("HULK-LIC-") :]
    else:
        return False, {}, "صيغة كود الترخيص غير صالحة. يجب أن يبدأ بـ SYSTEMIZE-LIC-"
    # Add padding back
    missing_padding = len(raw_b64) % 4
    if missing_padding:
        raw_b64 += "=" * (4 - missing_padding)

    try:
        decoded = base64.urlsafe_b64decode(raw_b64.encode("utf-8")).decode("utf-8")
        if ":::" not in decoded:
            return False, {}, "مفتاح الترخيص تالف أو غير صالح."

        json_str, sig = decoded.rsplit(":::", 1)
        expected_sig = _sign_payload(json_str)

        if not hmac.compare_digest(sig, expected_sig):
            return False, {}, "فشل التحقق الرقمي من مفتاح الترخيص (توقيع غير مطابق)."

        payload = json.loads(json_str)

        # 1. HWID Machine Binding Check
        token_mid = payload.get("mid", "")
        if token_mid != current_machine_id:
            return (
                False,
                payload,
                f"هذا الترخيص مخصص لجهاز آخر ({token_mid}) ولا يمكن استخدامه على هذا الجهاز ({current_machine_id}).",
            )

        # 2. Expiration Check
        exp_str = payload.get("exp")
        if exp_str and exp_str != "NONE":
            exp_date = datetime.fromisoformat(exp_str)
            now = datetime.now(timezone.utc)
            if exp_date.tzinfo is None:
                exp_date = exp_date.replace(tzinfo=timezone.utc)
            if now > exp_date:
                return False, payload, "انتهت فترة صلاحية هذا المفتاح."

        return True, payload, "تم التحقق من الترخيص بنجاح."

    except Exception as e:
        return False, {}, f"خطأ في معالجة مفتاح الترخيص: {str(e)}"
