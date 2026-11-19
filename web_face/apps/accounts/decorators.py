from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from apps.accounts.models import UserRole


def manager_required(view_func):
    """Restricts access to Managers, Owners, Superusers, or sessions temporarily unlocked by Manager face/password."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        from apps.core.security import is_manager_authorized
        if is_manager_authorized(request):
            return view_func(request, *args, **kwargs)
        from apps.core.views import check_manager_page_access
        unlocked, resp = check_manager_page_access(request, target_url=request.get_full_path())
        if not unlocked or resp:
            return resp
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def owner_required(view_func):
    """Restricts access exclusively to the System Owner and Superusers."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if not getattr(request.user, "is_owner", False):
            messages.error(request, "عذراً، هذه الصفحة مخصصة لمالك الصالات فقط.")
            raise PermissionDenied("Owner role required.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def role_required(allowed_roles):
    """Restricts access to specific role choices."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("accounts:login")
            if request.user.role not in allowed_roles and not request.user.is_superuser:
                messages.error(request, "ليس لديك صلاحية للوصول إلى هذه الصفحة.")
                raise PermissionDenied("Access denied.")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
