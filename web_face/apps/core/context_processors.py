from apps.core.models import GymProfile
from apps.core.licensing.engine import get_or_create_system_license, validate_system_license

def gym_context(request):
    try:
        profile = GymProfile.get_solo()
    except Exception:
        profile = None

    license_info = getattr(request, "license_info", None)
    license_obj = None
    if not license_info:
        try:
            license_obj, _ = get_or_create_system_license()
            _, _, _, license_info = validate_system_license(allow_remote_sync=False)
        except Exception:
            license_info = {}

    status = (license_info.get("status") or "").lower()
    is_demo = status == "demo"
    features = license_info.get("features", {
        "face_recognition": True,
        "whatsapp": True,
        "telegram": True,
        "bar": True,
        "payroll": True,
    })

    return {
        "gym_profile": profile,
        "system_license": license_obj,
        "license_info": license_info,
        "is_demo": is_demo,
        "remaining_demo_days": license_info.get("remaining_demo_days", 0),
        "remaining_demo_hours": license_info.get("remaining_demo_hours", 0),
        "license_features": features,
    }
