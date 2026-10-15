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
        is_background_or_asset = (
            request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in request.headers.get("accept", "")
            or path.startswith("/messaging/whatsapp/pending")
            or path.startswith("/messaging/whatsapp/dispatch")
            or path.startswith("/face/api/")
            or path.startswith("/api/")
            or path.startswith("/static/")
            or path.startswith("/media/")
            or path.startswith("/favicon")
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
