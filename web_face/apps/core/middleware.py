class ManagerPageAutoLockMiddleware:
    """
    Automatically re-locks the Manager Dashboard and Settings pages
    as soon as the user navigates away to any other part of the system
    (e.g., Home Dashboard, Members, Payments, Expenses, Payroll, etc.).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""

        # Paths that maintain the unlocked manager session
        is_manager_zone = (
            path.startswith("/manager") or
            path.startswith("/settings") or
            path.startswith("/static") or
            path.startswith("/media") or
            path.startswith("/favicon")
        )

        # If navigating anywhere outside the manager zone, immediately clear unlock flag
        if not is_manager_zone:
            if request.session.get("manager_page_unlocked"):
                request.session["manager_page_unlocked"] = False
                request.session.modified = True

        response = self.get_response(request)
        return response
