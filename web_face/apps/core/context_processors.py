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
    lic_type = (license_info.get("license_type") or "").lower()
    is_demo = (status == "demo") and (lic_type not in ["lifetime", "perpetual"])
    features = license_info.get("features", {
        "face_recognition": True,
        "whatsapp": True,
        "telegram": True,
        "bar": True,
        "payroll": True,
        "multi_branch": False,
    })

    # Multi-branch context
    from apps.core.branch_context import (
        is_multi_branch_active,
        get_active_branch,
        get_active_branch_display,
    )
    from apps.core.models import Branch

    is_mb = is_multi_branch_active()
    active_b = get_active_branch(request) if is_mb else None
    active_b_name = get_active_branch_display(request) if is_mb else "الفرع الافتراضي"
    branches = Branch.objects.filter(is_active=True).order_by("-is_main", "name") if is_mb else []

    valid_until_dt = (license_obj.valid_until if license_obj else None) or license_info.get("valid_until")
    valid_until_str = valid_until_dt.strftime("%Y-%m-%d %H:%M") if valid_until_dt else None

    return {
        "gym_profile": profile,
        "system_license": license_obj,
        "license_info": license_info,
        "is_demo": is_demo,
        "is_grace_period": bool(license_info.get("is_grace_period", False)),
        "grace_remaining_hours": license_info.get("grace_remaining_hours", 0),
        "grace_remaining_minutes": license_info.get("grace_remaining_minutes", 0),
        "license_valid_until_date": valid_until_str,
        "remaining_demo_days": license_info.get("remaining_demo_days", 0),
        "remaining_demo_hours": license_info.get("remaining_demo_hours", 0),
        "license_features": features,
        "is_multi_branch_enabled": is_mb,
        "active_branch": active_b,
        "active_branch_name": active_b_name,
        "all_branches": branches,
    }
