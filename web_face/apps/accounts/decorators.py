from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from apps.accounts.models import UserRole


def manager_required(view_func):
    """Restricts access exclusively to Managers and Superusers."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if not (request.user.role == UserRole.MANAGER or request.user.is_superuser):
            messages.error(request, "عذراً، هذه الصفحة مخصصة لمدير الصالة فقط.")
            raise PermissionDenied("Manager role required.")
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
