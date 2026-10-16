import logging
from django.http import JsonResponse
from django.shortcuts import render
from apps.core.licensing.engine import validate_system_license

logger = logging.getLogger(__name__)


class LicenseEnforcementMiddleware:
    """
    Enforces Software Licensing, Hardware ID anti-copy binding, and SaaS Expiration.
    - Permits static/media/assets/ping/license-activation endpoints.
    - Fast local validation (cached / 0.1ms).
    - If locked:
      - Returns 403 JSON for API/AJAX requests.
      - Renders license_locked.html for browser navigation.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""

        # Exempt paths
        if path.startswith((
            "/static/",
            "/media/",
            "/favicon",
            "/ping",
            "/license/activate",
            "/license/status",
        )) or path.endswith((".ico", ".png", ".jpg", ".jpeg", ".svg", ".css", ".js", ".map", ".json")):
            return self.get_response(request)

        # License validation
        allow_remote = path in ["/", "/settings/"]
        try:
            is_valid, reason, message, info = validate_system_license(allow_remote_sync=allow_remote)
        except Exception as exc:
            logger.error(f"[LicenseEnforcementMiddleware] Error validating license: {exc}")
            is_valid, reason, message, info = True, "fallback", "", {}

        request.license_valid = is_valid
        request.license_info = info
        request.license_reason = reason

        if not is_valid:
            accept = (request.headers.get("accept") or "").lower()
            is_ajax = (
                request.headers.get("x-requested-with") == "XMLHttpRequest"
                or "application/json" in accept
                or "/api/" in path
            )

            if is_ajax:
                return JsonResponse({
                    "success": False,
                    "license_locked": True,
                    "reason": reason,
                    "message": message,
                    "hwid": info.get("machine_id", ""),
                }, status=403)

            return render(request, "core/license_locked.html", {
                "license_reason": reason,
                "license_message": message,
                "license_info": info,
            }, status=403)

        return self.get_response(request)


class ManagerPageAutoLockMiddleware:
    """
    Granular Auto-Lock Middleware:
    Automatically re-locks password-protected sections (Manager Dashboard, Settings, Developer Options,
    Trainers & Coaches) as soon as the user navigates away from each respective zone.
    Background AJAX/API requests, polling endpoints, and static/media assets do NOT trigger a re-lock.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""

        # Background AJAX/polling requests or assets should never clear the unlock status
        sec_dest = (request.headers.get("sec-fetch-dest") or "").lower()
        sec_mode = (request.headers.get("sec-fetch-mode") or "").lower()
        accept = (request.headers.get("accept") or "").lower()

        is_background_or_asset = (
            request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in accept
            or sec_dest in ["empty", "image", "script", "style", "font", "video", "audio"]
            or sec_mode in ["cors", "no-cors"]
            or "/api/" in path
            or path.startswith((
                "/static/",
                "/media/",
                "/favicon",
                "/ping",
                "/quick-search",
                "/messaging/api",
                "/face/",
                "/settings/updates/",
            ))
            or path.endswith((".ico", ".png", ".jpg", ".jpeg", ".svg", ".css", ".js", ".map", ".json"))
            or "ping" in request.GET
        )

        if not is_background_or_asset:
            # 1. Settings & Developer Options Zone
            is_settings_zone = path.startswith("/settings")
            if not is_settings_zone:
                if request.session.get("settings_page_unlocked"):
                    request.session["settings_page_unlocked"] = False
                    request.session.modified = True
                if request.session.get("developer_options_unlocked"):
                    request.session["developer_options_unlocked"] = False
                    request.session.modified = True

            # 2. Trainers & Coaches Zone
            is_trainers_zone = (
                path.startswith("/payroll/trainers")
                or path.startswith("/payroll/coaches")
                or path.startswith("/payroll/trainer-assignments")
                or path.startswith("/payroll/private-training")
            )
            if not is_trainers_zone:
                if request.session.get("trainers_page_unlocked"):
                    request.session["trainers_page_unlocked"] = False
                    request.session.modified = True

            # 3. Manager & Mobile Dashboard Zone
            is_manager_zone = (
                path.startswith("/manager")
                or path.startswith("/mobile")
                or (path == "/" and request.session.get("view_mode") == "mobile")
            )
            if not is_manager_zone:
                if request.session.get("manager_page_unlocked"):
                    request.session["manager_page_unlocked"] = False
                    request.session.modified = True

        response = self.get_response(request)
        return response
