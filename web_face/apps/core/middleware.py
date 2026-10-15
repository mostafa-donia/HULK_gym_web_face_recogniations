class ManagerPageAutoLockMiddleware:
    """
    Automatically re-locks the Manager Dashboard, Mobile Dashboard, and Settings pages
    as soon as the user navigates away to any other non-manager part of the system
    (e.g., Home Dashboard, Members, Payments, Expenses, etc.).
    Background AJAX/API requests and asset loading do NOT trigger a re-lock.
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

        # Paths that maintain the unlocked manager session
        is_manager_zone = (
            path.startswith("/manager") or
            path.startswith("/mobile") or
            path.startswith("/settings") or
            path.startswith("/payroll") or
            path.startswith("/reports") or
            (path == "/" and request.session.get("view_mode") == "mobile")
        )

        # If navigating anywhere outside the manager zone, immediately clear unlock flag
        if not is_background_or_asset and not is_manager_zone:
            if request.session.get("manager_page_unlocked"):
                request.session["manager_page_unlocked"] = False
                request.session.modified = True

        response = self.get_response(request)
        return response
