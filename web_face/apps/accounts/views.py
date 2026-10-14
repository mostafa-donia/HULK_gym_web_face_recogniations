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
            messages.success(request, f"مرحباً بك {user.first_name or user.username} في HULK GYM!")
            return redirect("core:dashboard")
        else:
            messages.error(request, "اسم المستخدم أو كلمة المرور غير صحيحة.")

    return render(request, "accounts/login.html")


def logout_view(request):
    logout(request)
    messages.info(request, "تم تسجيل الخروج بنجاح.")
    return redirect("accounts:login")
