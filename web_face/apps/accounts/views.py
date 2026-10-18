from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib import messages


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"مرحباً بك {user.first_name or user.username} في Systemize!")
            return redirect("core:dashboard")
        else:
            messages.error(request, "اسم المستخدم أو كلمة المرور غير صحيحة.")

    return render(request, "accounts/login.html")


def logout_view(request):
    logout(request)
    messages.info(request, "تم تسجيل الخروج بنجاح.")
    return redirect("accounts:login")


def switch_branch(request, branch_id):
    """Allows Owner to switch between branches or 'all'."""
    from apps.core.models import Branch
    from apps.core.branch_context import is_multi_branch_active

    if not is_multi_branch_active():
        return redirect(request.META.get("HTTP_REFERER", "/"))

    if not getattr(request.user, "is_owner", False):
        messages.error(request, "عذراً، هذه الخاصية مخصصة للمالك فقط.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    target = str(branch_id).strip().lower()
    if target in ["all", "0", "none"]:
        request.session["active_branch_id"] = "all"
        messages.success(request, "تم التبديل إلى عرض كافة الفروع (نظرة مجمّعة).")
    else:
        try:
            branch = Branch.objects.get(id=branch_id, is_active=True)
            request.session["active_branch_id"] = branch.id
            messages.success(request, f"تم التبديل بنجاح إلى: {branch.name}")
        except Branch.DoesNotExist:
            messages.error(request, "الفرع المحدد غير موجود أو غير مفعل.")

    return redirect(request.META.get("HTTP_REFERER", "/"))
