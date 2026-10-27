from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib import messages
from apps.accounts.models import User, UserRole


def login_view(request):
    # If no administrator exists in the database, redirect to first-time setup wizard
    if not User.objects.filter(is_superuser=True).exists():
        return redirect("accounts:initial_setup")

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


def initial_setup_view(request):
    """
    First-time onboarding wizard.
    Only accessible if no superuser/owner exists in database.
    Allows gym owners/installers to define gym name, custom manager credentials, and staff credentials.
    """
    from apps.core.models import GymProfile, Branch, SystemLicense

    if User.objects.filter(is_superuser=True).exists():
        return redirect("accounts:login")

    profile = GymProfile.get_solo()

    if request.method == "POST":
        gym_name = request.POST.get("gym_name", "").strip() or profile.gym_name or "Systemize Gym"
        admin_username = request.POST.get("admin_username", "").strip().lower() or "manager"
        admin_password = request.POST.get("admin_password", "").strip()
        confirm_admin_password = request.POST.get("confirm_admin_password", "").strip()
        reception_username = request.POST.get("reception_username", "").strip().lower() or "reception"
        reception_password = request.POST.get("reception_password", "").strip() or admin_password

        if not admin_password:
            messages.error(request, "يرجى إدخال كلمة مرور لحساب المدير.")
            return render(request, "accounts/initial_setup.html", {
                "gym_name": gym_name,
                "admin_username": admin_username,
                "reception_username": reception_username,
            })

        if len(admin_password) < 4:
            messages.error(request, "كلمة المرور يجب أن تتكون من 4 أحرف أو أرقام على الأقل.")
            return render(request, "accounts/initial_setup.html", {
                "gym_name": gym_name,
                "admin_username": admin_username,
                "reception_username": reception_username,
            })

        if admin_password != confirm_admin_password:
            messages.error(request, "كلمة المرور وتأكيد كلمة المرور غير متطابقين!")
            return render(request, "accounts/initial_setup.html", {
                "gym_name": gym_name,
                "admin_username": admin_username,
                "reception_username": reception_username,
            })

        # Save Gym Profile
        profile.gym_name = gym_name
        profile.trainers_page_password = admin_password
        profile.save()

        # Ensure main branch exists
        main_branch = Branch.objects.filter(is_main=True).first()
        if not main_branch:
            main_branch, _ = Branch.objects.get_or_create(
                code="BR-01",
                defaults={"name": "الفرع الرئيسي", "is_main": True, "is_active": True}
            )

        # Remove any lingering legacy demo user
        User.objects.filter(username__in=["demo", "admin"]).delete()

        # Create Manager Account
        mgr = User.objects.create(
            username=admin_username,
            role=UserRole.OWNER,
            first_name="إدارة الصالة",
            branch=main_branch,
            is_staff=True,
            is_superuser=True
        )
        mgr.set_password(admin_password)
        mgr.save()

        # Create Reception Account
        rec = User.objects.create(
            username=reception_username,
            role=UserRole.RECEPTION,
            first_name="موظف الاستقبال",
            branch=main_branch,
            is_staff=False,
            is_superuser=False
        )
        rec.set_password(reception_password)
        rec.save()

        # Authenticate and login the manager immediately
        user = authenticate(request, username=admin_username, password=admin_password)
        if user:
            login(request, user)
            messages.success(request, f"🎉 تم إعداد صالة '{gym_name}' وحساباتك بنجاح! مرحباً بك في Systemize.")
            return redirect("core:dashboard")

        messages.success(request, "تم حفظ بيانات الدخول بنجاح! يمكنك الآن تسجيل الدخول.")
        return redirect("accounts:login")

    return render(request, "accounts/initial_setup.html", {
        "gym_name": profile.gym_name or "Systemize Gym",
        "admin_username": "manager",
        "reception_username": "reception",
    })



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
