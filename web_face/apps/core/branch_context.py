from apps.core.models import Branch, SystemLicense


def is_multi_branch_active() -> bool:
    """Checks whether the Multi-Branch Add-on is enabled in SystemLicense."""
    try:
        lic = SystemLicense.objects.first()
        return bool(lic and lic.feature_multi_branch)
    except Exception:
        return False


def get_active_branch(request):
    """
    Returns the currently active Branch model instance for the user request, or None for 'All Branches'.
    - Manager / Reception: Always strictly locked to request.user.branch.
    - Owner / Superuser: Can switch via session['active_branch_id'] or view all (None).
    """
    if not is_multi_branch_active():
        return None

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    # Manager / Reception: Locked strictly to their branch
    if not getattr(user, "is_owner", False):
        return getattr(user, "branch", None)

    # Owner / Superuser: Check active session branch
    active_branch_id = request.session.get("active_branch_id")
    if not active_branch_id or str(active_branch_id).lower() in ["all", "0", "none"]:
        return None

    try:
        return Branch.objects.filter(id=active_branch_id, is_active=True).first()
    except Exception:
        return None


def get_active_branch_display(request) -> str:
    """Returns a user-friendly Arabic string for the active branch."""
    if not is_multi_branch_active():
        return "الفرع الافتراضي"

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return "الفرع الافتراضي"

    if getattr(user, "is_owner", False):
        branch = get_active_branch(request)
        if branch:
            return branch.name
        return "كافة الفروع (مجمّع)"

    branch = getattr(user, "branch", None)
    return branch.name if branch else "الفرع الافتراضي"


def filter_by_branch(queryset, request, branch_field="branch"):
    """
    Filters a Django QuerySet according to the user's branch role and active branch selection.
    If multi-branch is disabled, returns the queryset untouched.
    """
    if not is_multi_branch_active():
        return queryset

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return queryset

    if not getattr(user, "is_owner", False):
        # Locked to user's assigned branch
        user_branch = getattr(user, "branch", None)
        if user_branch:
            return queryset.filter(**{branch_field: user_branch})
        return queryset

    # Owner: filter only if a specific branch is selected
    active_branch = get_active_branch(request)
    if active_branch:
        return queryset.filter(**{branch_field: active_branch})

    return queryset
