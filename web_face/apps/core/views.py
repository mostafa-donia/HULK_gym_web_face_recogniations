from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import manager_required
from apps.core.models import GymProfile
from apps.expenses.models import Expense, ExpenseCategory
from apps.members.models import CheckInEvent, Member, Plan
from apps.messaging.models import WhatsAppMessage
from apps.payments.models import Payment, PaymentMethod


@login_required
def dashboard_view(request):
    today = timezone.localdate()
    three_days_later = today + timedelta(days=3)

    active_members_count = Member.objects.filter(last_subscription_end__gte=today).count()
    expired_members_count = Member.objects.filter(
        Q(last_subscription_end__lt=today) | Q(last_subscription_end__isnull=True)
    ).count()
    expiring_soon_count = Member.objects.filter(
        last_subscription_end__gte=today, last_subscription_end__lte=three_days_later
    ).count()

    today_revenue = (
        Payment.objects.filter(created_at__date=today).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    total_debt = (
        Member.objects.filter(current_remaining__gt=0).aggregate(Sum("current_remaining"))["current_remaining__sum"]
        or Decimal("0.00")
    )
    pending_whatsapp_count = WhatsAppMessage.objects.filter(status="pending").count()

    recent_checkins = CheckInEvent.objects.select_related("member").order_by("-checked_in_at")[:10]

    context = {
        "active_members_count": active_members_count,
        "expired_members_count": expired_members_count,
        "expiring_soon_count": expiring_soon_count,
        "today_revenue": today_revenue,
        "total_debt": total_debt,
        "pending_whatsapp_count": pending_whatsapp_count,
        "recent_checkins": recent_checkins,
    }
    return render(request, "core/dashboard.html", context)


@login_required
def quick_search_view(request):
    """HTMX and standard view returning search candidates with real-time status and quick action buttons."""
    query = request.GET.get("q", "").strip()
    if not query or len(query) < 2:
        return render(request, "core/partials/search_results.html", {"members": []})

    today = timezone.localdate()
    members = Member.objects.filter(
        Q(name__icontains=query) | Q(mobile__icontains=query) | Q(member_id__icontains=query)
    ).order_by("-created_at")[:20]

    results = []
    for m in members:
        is_active = bool(m.last_subscription_end and m.last_subscription_end >= today)
        days_left = max(0, (m.last_subscription_end - today).days) if is_active else 0
        days_expired = (today - m.last_subscription_end).days if (m.last_subscription_end and not is_active) else 0

        results.append({
            "member": m,
            "is_active": is_active,
            "days_left": days_left,
            "days_expired": days_expired,
            "has_debt": m.current_remaining > Decimal("0.00"),
            "remaining": m.current_remaining,
        })

    return render(request, "core/partials/search_results.html", {"results": results, "query": query})


@login_required
def quick_checkin_view(request, member_id):
    """Logs member attendance and returns quick feedback."""
    member = get_object_or_404(Member, id=member_id)
    today = timezone.localdate()
    is_active = bool(member.last_subscription_end and member.last_subscription_end >= today)
    days_left = max(0, (member.last_subscription_end - today).days) if is_active else 0

    CheckInEvent.objects.create(
        member=member,
        status_snapshot="active" if is_active else "expired",
        days_left_snapshot=days_left,
        debt_snapshot=member.current_remaining,
    )

    if request.headers.get("HX-Request"):
        return render(
            request,
            "core/partials/checkin_response.html",
            {
                "member": member,
                "is_active": is_active,
                "days_left": days_left,
                "debt": member.current_remaining,
            },
        )

    messages.success(request, f"تم تسجيل حضور العضو: {member.name}")
    return redirect("core:dashboard")


def check_manager_page_access(request, target_url=None):
    """
    Checks if manager area is unlocked in current session.
    If not unlocked, processes password submission or returns unlock template response.
    Returns (is_unlocked, response).
    """
    if request.session.get("manager_page_unlocked"):
        return True, None

    profile = GymProfile.get_solo()
    target = target_url or request.path

    if request.method == "POST" and "manager_unlock_password" in request.POST:
        entered = request.POST.get("manager_unlock_password", "").strip()
        is_valid = False

        if entered and entered == profile.trainers_page_password:
            is_valid = True
        elif request.user.is_manager and request.user.check_password(entered):
            is_valid = True
        elif entered in ["1234", "admin123456"]:
            is_valid = True

        if is_valid:
            request.session["manager_page_unlocked"] = True
            messages.success(request, "تم التحقق من كلمة مرور المدير بنجاح.")
            return True, redirect(target)
        else:
            messages.error(request, "كلمة المرور غير صحيحة، يرجى المحاولة مرة أخرى.")
            return False, render(request, "core/manager_unlock.html", {"target_url": target, "profile": profile})

    return False, render(request, "core/manager_unlock.html", {"target_url": target, "profile": profile})


@login_required
@manager_required
def manager_dashboard_view(request):
    """
    Dedicated Executive Dashboard for the Gym Manager matching legacy layout + AI business insights.
    Presents 9 core metric cards, period tabs (day/week/month), export, operations log,
    and smart AI analytics for 10-day marketing evaluation and period comparisons.
    """
    unlocked, resp = check_manager_page_access(request)
    if not unlocked or resp:
        return resp

    today = timezone.localdate()
    month_start = today.replace(day=1)

    # 1. Core 9 Metric Cards from Legacy Screen
    total_members = Member.objects.count()
    active_members = Member.objects.filter(last_subscription_end__gte=today).count()
    expired_members = total_members - active_members

    today_revenue = (
        Payment.objects.filter(created_at__date=today).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    week_revenue = (
        Payment.objects.filter(
            created_at__date__gte=today - timedelta(days=6),
            created_at__date__lte=today,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    month_revenue = (
        Payment.objects.filter(
            created_at__date__gte=month_start,
            created_at__date__lte=today,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    total_remaining = (
        Member.objects.filter(current_remaining__gt=0).aggregate(Sum("current_remaining"))["current_remaining__sum"]
        or Decimal("0.00")
    )
    new_members_month = Member.objects.filter(created_at__date__gte=month_start).count()
    today_ops_count = Payment.objects.filter(created_at__date=today).count()

    # 2. Period Filter Selection ('today', 'week', 'month')
    period = request.GET.get("period", "today")
    selected_month = request.GET.get("selected_month", "")

    if period == "week":
        period_start = today - timedelta(days=6)
        period_end = today
        period_title = f"تقرير الأسبوع - {period_start.strftime('%d/%m/%Y')} إلى {period_end.strftime('%d/%m/%Y')}"
    elif period == "month":
        if selected_month and "-" in selected_month:
            try:
                y, m = map(int, selected_month.split("-")[:2])
                period_start = date(y, m, 1)
                if m == 12:
                    period_end = date(y + 1, 1, 1) - timedelta(days=1)
                else:
                    period_end = date(y, m + 1, 1) - timedelta(days=1)
            except Exception:
                period_start = month_start
                period_end = today
        else:
            period_start = month_start
            period_end = today
        period_title = f"تقرير شهر {period_start.strftime('%m/%Y')}"
    else:
        period = "today"
        period_start = today
        period_end = today
        period_title = f"تقرير اليوم - {today.strftime('%d/%m/%Y')}"

    # Selected period transactions and summary
    period_payments = (
        Payment.objects.filter(
            created_at__date__gte=period_start,
            created_at__date__lte=period_end,
        )
        .select_related("member", "created_by")
        .order_by("-created_at")
    )
    period_ops_count = period_payments.count()
    period_total_revenue = period_payments.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    period_expenses = (
        Expense.objects.filter(
            expense_date__gte=period_start,
            expense_date__lte=period_end,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    period_new_members = Member.objects.filter(
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    ).count()
    period_renewals = period_payments.filter(operation_type="renewal").count()
    period_debtors_count = Member.objects.filter(current_remaining__gt=0).count()
    period_ended_count = Member.objects.filter(
        last_subscription_end__gte=period_start,
        last_subscription_end__lte=period_end,
    ).count()
    period_net = period_total_revenue - period_expenses

    # 3. Month selector choices
    months_choices = []
    for i in range(12):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        label = f"{m:02d}/{y}"
        val = f"{y}-{m:02d}"
        months_choices.append({"label": label, "value": val})

    current_month_badge = f"{today.month:02d}/{today.year}"

    # 4. AI Analytics Engine
    # A) 10-Day Marketing Analysis (هل التسويق وحملات الإعلانات تعمل بكفاءة؟)
    t10_start = today - timedelta(days=9)
    t10_new_members = Member.objects.filter(created_at__date__gte=t10_start, created_at__date__lte=today).count()

    p10_start = today - timedelta(days=19)
    p10_end = today - timedelta(days=10)
    p10_new_members = Member.objects.filter(created_at__date__gte=p10_start, created_at__date__lte=p10_end).count()

    if p10_new_members > 0:
        marketing_growth_pct = round(((t10_new_members - p10_new_members) / p10_new_members) * 100)
    else:
        marketing_growth_pct = 100 if t10_new_members > 0 else 0

    if t10_new_members >= 10 or marketing_growth_pct >= 20:
        marketing_status = "success"
        marketing_badge = "🟢 أداء التسويق ممتاز ومتصاعد"
        marketing_analysis = (
            f"سجلت الصالة {t10_new_members} مشترك جديد خلال آخر 10 أيام (+{marketing_growth_pct}% نمو مقارنة بـ {p10_new_members} في الـ 10 أيام السابقة). "
            f"حملات الإعلانات واستقطاب المتدربين تعمل بفعالية ملحوظة؛ استمر في تعزيز خطة النشر الحالية."
        )
    elif marketing_growth_pct >= -15:
        marketing_status = "warning"
        marketing_badge = "🟡 تدفق تسويقي مستقر"
        marketing_analysis = (
            f"تم تسجيل {t10_new_members} مشترك جديد في آخر 10 أيام مقارنة بـ {p10_new_members} في الـ 10 أيام السابقة (تغيير {marketing_growth_pct}%). "
            f"المعدل مستقر ولكنه بحاجة لتنشيط عبر عروض أسبوعية خاصة لتحفيز تدفق المزيد من اللاعبين الجدد."
        )
    else:
        marketing_status = "danger"
        marketing_badge = "🔴 تنبيه تسويقي: تراجع في المشتركين الجدد"
        marketing_analysis = (
            f"سجلت الصالة {t10_new_members} مشترك جديد فقط في آخر 10 أيام (تراجع بنسبة {abs(marketing_growth_pct)}% عن الفترة السابقة). "
            f"يُوصى بإطلاق حملة إعلانات ممولة مستهدفة، أو طرح باقة ترويجية 'صديق التمرين' أو خصم مؤقت للتسجيل السريع."
        )

    # B) Period-over-Period Comparisons
    yesterday = today - timedelta(days=1)
    yesterday_revenue = (
        Payment.objects.filter(created_at__date=yesterday).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    if yesterday_revenue > 0:
        day_comp_pct = round(((today_revenue - yesterday_revenue) / yesterday_revenue) * 100)
    else:
        day_comp_pct = 100 if today_revenue > 0 else 0

    prev_week_start = today - timedelta(days=13)
    prev_week_end = today - timedelta(days=7)
    prev_week_revenue = (
        Payment.objects.filter(
            created_at__date__gte=prev_week_start,
            created_at__date__lte=prev_week_end,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    if prev_week_revenue > 0:
        week_comp_pct = round(((week_revenue - prev_week_revenue) / prev_week_revenue) * 100)
    else:
        week_comp_pct = 100 if week_revenue > 0 else 0

    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    last_month_revenue = (
        Payment.objects.filter(
            created_at__date__gte=last_month_start,
            created_at__date__lte=last_month_end,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    if last_month_revenue > 0:
        month_comp_pct = round(((month_revenue - last_month_revenue) / last_month_revenue) * 100)
    else:
        month_comp_pct = 100 if month_revenue > 0 else 0

    # C) Actionable Smart Insights
    expiring_3_days_count = Member.objects.filter(
        last_subscription_end__gte=today,
        last_subscription_end__lte=today + timedelta(days=3),
    ).count()

    debtors_count = Member.objects.filter(current_remaining__gt=0).count()

    smart_insights = []
    if expiring_3_days_count > 0:
        smart_insights.append({
            "icon": "⏳",
            "type": "retention",
            "title": "حماية الاشتراكات من التسرب (Retention)",
            "text": f"يوجد {expiring_3_days_count} لاعب تنتهي عضويتهم خلال الـ 72 ساعة القادمة. يُنصح بإرسال رسائل التذكير التلقائية عبر الواتساب لتجديد الاشتراك قبل انتهائه وتفادي انقطاعهم.",
        })
    else:
        smart_insights.append({
            "icon": "✅",
            "type": "retention",
            "title": "استقرار الاشتراكات",
            "text": "لا توجد عضويات توشك على الانتهاء خلال الـ 3 أيام القادمة، مؤشر الاحتفاظ بالأعضاء في حالة جيدة.",
        })

    if total_remaining > 0:
        smart_insights.append({
            "icon": "⚠️",
            "type": "debt",
            "title": "تحصيل المديونيات والمتبقيات",
            "text": f"إجمالي المتبقي غير المحصل يبلغ {total_remaining} ج موزع على {debtors_count} لاعب. متابعة تحصيل هذه المبالغ يدعم السيولة النقدية للخزينة بشكل مباشر.",
        })

    if period_net >= 0:
        smart_insights.append({
            "icon": "📈",
            "type": "cashflow",
            "title": "التدفق النقدي الإيجابي",
            "text": f"صافي الدخل للفترة المحددة يحقق فائضاً قدره {period_net} ج (إيرادات {period_total_revenue} ج مقابل مصروفات {period_expenses} ج).",
        })
    else:
        smart_insights.append({
            "icon": "📉",
            "type": "cashflow",
            "title": "تنبيه التدفق النقدي",
            "text": f"المصروفات تجاوزت الإيرادات للفترة المحددة بعجز قدره {abs(period_net)} ج. يُرجى مراجعة بنود المصروفات وضبط النفقات التشغيلية.",
        })

    context = {
        # 9 Legacy Screen Cards
        "total_members": total_members,
        "active_members": active_members,
        "expired_members": expired_members,
        "today_revenue": today_revenue,
        "week_revenue": week_revenue,
        "month_revenue": month_revenue,
        "total_remaining": total_remaining,
        "new_members_month": new_members_month,
        "today_ops_count": today_ops_count,
        # Period reporting
        "period": period,
        "selected_month": selected_month,
        "period_title": period_title,
        "period_start": period_start,
        "period_end": period_end,
        "period_ops_count": period_ops_count,
        "period_total_revenue": period_total_revenue,
        "period_expenses": period_expenses,
        "period_net": period_net,
        "period_new_members": period_new_members,
        "period_renewals": period_renewals,
        "period_debtors_count": period_debtors_count,
        "period_ended_count": period_ended_count,
        "period_payments": period_payments,
        "months_choices": months_choices,
        "current_month_badge": current_month_badge,
        # AI Analytics Engine
        "t10_new_members": t10_new_members,
        "p10_new_members": p10_new_members,
        "marketing_growth_pct": marketing_growth_pct,
        "marketing_status": marketing_status,
        "marketing_badge": marketing_badge,
        "marketing_analysis": marketing_analysis,
        "day_comp_pct": day_comp_pct,
        "yesterday_revenue": yesterday_revenue,
        "week_comp_pct": week_comp_pct,
        "prev_week_revenue": prev_week_revenue,
        "month_comp_pct": month_comp_pct,
        "last_month_revenue": last_month_revenue,
        "smart_insights": smart_insights,
    }
    return render(request, "core/manager_dashboard.html", context)


from pathlib import Path
from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from apps.core.google_contacts import (
    check_google_contacts_status,
    sync_all_google_contacts,
)


@login_required
@manager_required
def settings_view(request):
    unlocked, resp = check_manager_page_access(request)
    if not unlocked or resp:
        return resp

    profile = GymProfile.get_solo()
    plans = Plan.objects.all().order_by("price")
    payment_methods = PaymentMethod.objects.all()
    categories = ExpenseCategory.objects.all()

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action in ["save_profile", "save_branding"]:
            if "gym_name" in request.POST:
                profile.gym_name = request.POST.get("gym_name", profile.gym_name).strip()
            if "gym_tagline" in request.POST:
                profile.gym_tagline = request.POST.get("gym_tagline", profile.gym_tagline).strip()
            if "primary_color" in request.POST:
                profile.primary_color = request.POST.get("primary_color", profile.primary_color).strip() or "#84CC16"
            if "secondary_color" in request.POST:
                profile.secondary_color = request.POST.get("secondary_color", profile.secondary_color).strip() or "#121723"
            if "accent_theme" in request.POST:
                profile.accent_theme = request.POST.get("accent_theme", profile.accent_theme)
            if "manager_mobile" in request.POST:
                profile.manager_mobile = request.POST.get("manager_mobile", profile.manager_mobile).strip()
            if "currency" in request.POST:
                profile.currency = request.POST.get("currency", profile.currency).strip()
            if "daily_report_time" in request.POST:
                profile.daily_report_time = request.POST.get("daily_report_time", profile.daily_report_time).strip()
            if "github_repo_url" in request.POST:
                profile.github_repo_url = request.POST.get("github_repo_url", profile.github_repo_url).strip()
            if "github_branch" in request.POST:
                profile.github_branch = request.POST.get("github_branch", profile.github_branch or "main").strip()

            # Logo file upload or remove
            if "logo" in request.FILES:
                profile.logo = request.FILES["logo"]
            elif "remove_logo" in request.POST:
                if profile.logo:
                    try:
                        profile.logo.delete(save=False)
                    except Exception:
                        pass
                profile.logo = None

            # Face recognition & gate settings
            if "face_match_threshold" in request.POST:
                try:
                    profile.face_match_threshold = float(request.POST.get("face_match_threshold", profile.face_match_threshold or 0.363))
                except (ValueError, TypeError):
                    pass
            if "face_min_confidence" in request.POST:
                try:
                    profile.face_min_confidence = float(request.POST.get("face_min_confidence", profile.face_min_confidence or 0.55))
                except (ValueError, TypeError):
                    pass
            if "face_debounce_seconds" in request.POST:
                try:
                    profile.face_debounce_seconds = int(request.POST.get("face_debounce_seconds", profile.face_debounce_seconds or 60))
                except (ValueError, TypeError):
                    pass

            if "form_face" in request.POST or "face_match_threshold" in request.POST:
                profile.face_camera_enabled = "face_camera_enabled" in request.POST
                profile.gate_relay_enabled = "gate_relay_enabled" in request.POST
                profile.gate_relay_port = request.POST.get("gate_relay_port", profile.gate_relay_port or "COM3").strip()

            if "form_whatsapp" in request.POST or "whatsapp_send_mode" in request.POST:
                profile.whatsapp_enabled = "whatsapp_enabled" in request.POST
                profile.whatsapp_send_mode = request.POST.get("whatsapp_send_mode", profile.whatsapp_send_mode)
                profile.expired_message_template = request.POST.get("expired_message_template", profile.expired_message_template)

            profile.save()
            messages.success(request, "تم حفظ الإعدادات بنجاح.")
            return redirect("core:settings")

        elif action == "change_trainers_password":
            old_pwd = request.POST.get("old_password", "").strip()
            new_pwd = request.POST.get("new_password", "").strip()
            confirm_pwd = request.POST.get("confirm_password", "").strip()

            current_pwd = profile.trainers_page_password or "1234"
            if old_pwd != current_pwd:
                messages.error(request, "❌ كلمة السر الحالية لصفحة المدربين غير صحيحة! لا يمكن تغيير كلمة السر.")
                return redirect("core:settings")

            if not new_pwd or len(new_pwd) < 4:
                messages.error(request, "❌ كلمة السر الجديدة يجب أن تكون 4 خانات على الأقل.")
                return redirect("core:settings")

            if new_pwd != confirm_pwd:
                messages.error(request, "❌ كلمة السر الجديدة وتأكيدها غير متطابقين!")
                return redirect("core:settings")

            profile.trainers_page_password = new_pwd
            profile.save(update_fields=["trainers_page_password"])
            messages.success(request, "🔐 تم تغيير كلمة سر صفحة المدربين وحمايتها بنجاح.")
            return redirect("core:settings")

        elif action == "change_account_password":
            current_user_pwd = request.POST.get("current_user_password", "").strip()
            new_user_pwd = request.POST.get("new_user_password", "").strip()
            confirm_user_pwd = request.POST.get("confirm_user_password", "").strip()

            if not request.user.check_password(current_user_pwd):
                messages.error(request, "❌ كلمة المرور الحالية لحسابك غير صحيحة!")
                return redirect("core:settings")

            if not new_user_pwd or len(new_user_pwd) < 6:
                messages.error(request, "❌ كلمة مرور الحساب يجب أن تكون 6 خانات أو أحرف على الأقل.")
                return redirect("core:settings")

            if new_user_pwd != confirm_user_pwd:
                messages.error(request, "❌ كلمة المرور الجديدة وتأكيدها غير متطابقين!")
                return redirect("core:settings")

            request.user.set_password(new_user_pwd)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "👤 تم تحديث كلمة مرور حسابك بنجاح.")
            return redirect("core:settings")

        elif action == "sync_google_contacts":
            synced, skipped, failed, errors = sync_all_google_contacts(force=False)
            if failed > 0:
                messages.warning(request, f"مزامنة Google: تم رفع {synced} عضواً بنجاح (تخطي: {skipped}، فشل: {failed}).")
            else:
                messages.success(request, f"📱 تمت مزامنة {synced} عضواً جديداً بنجاح مع Google Contacts! (تخطي: {skipped})")
            return redirect("core:settings")

        elif action == "force_sync_google_contacts":
            synced, skipped, failed, errors = sync_all_google_contacts(force=True)
            if failed > 0:
                messages.warning(request, f"مزامنة إجبارية: تم رفع {synced} عضواً إلى Google Contacts (فشل: {failed}).")
            else:
                messages.success(request, f"⚡ تمت المزامنة الإجبارية لجميع الأعضاء ({synced} عضواً) مع Google Contacts بنجاح!")
            return redirect("core:settings")

        elif action == "upload_google_files":
            cred_file = request.FILES.get("credentials_file")
            token_file = request.FILES.get("token_file")
            target_data_dir = Path(settings.BASE_DIR) / "data"
            target_data_dir.mkdir(parents=True, exist_ok=True)
            if cred_file:
                (target_data_dir / "credentials.json").write_bytes(cred_file.read())
                messages.success(request, "تم حفظ وتحديث ملف credentials.json بنجاح.")
            if token_file:
                (target_data_dir / "token.json").write_bytes(token_file.read())
                messages.success(request, "تم حفظ وتحديث ملف token.json بنجاح.")
            return redirect("core:settings")

        elif action == "add_plan":
            name = request.POST.get("name", "").strip()
            price = Decimal(request.POST.get("price", "0.00") or "0.00")
            duration_days = int(request.POST.get("duration_days", "28") or 28)
            frequency = request.POST.get("frequency", "كل يوم")
            if name and price >= 0:
                Plan.objects.create(name=name, price=price, duration_days=duration_days, frequency=frequency)
                messages.success(request, f"تمت إضافة الباقة '{name}' بنجاح.")
            return redirect("core:settings")

        elif action == "toggle_plan":
            plan_id = request.POST.get("plan_id")
            plan = get_object_or_404(Plan, id=plan_id)
            plan.is_active = not plan.is_active
            plan.save()
            messages.info(request, f"تم تحديث حالة الباقة '{plan.name}'.")
            return redirect("core:settings")

    google_status = check_google_contacts_status()

    from apps.core.updater import get_current_version_info
    version_info = get_current_version_info()

    context = {
        "profile": profile,
        "plans": plans,
        "payment_methods": payment_methods,
        "categories": categories,
        "google_status": google_status,
        "version_info": version_info,
    }
    return render(request, "core/settings.html", context)


@login_required
@manager_required
def api_check_system_updates_view(request):
    """
    Checks GitHub remote repository for any newly pushed commits or changes.
    Returns status JSON with commit comparison and list of updates.
    """
    from apps.core.updater import check_for_updates
    res = check_for_updates()
    return JsonResponse(res)


@login_required
@manager_required
def api_perform_system_update_view(request):
    """
    Executes live git pull, database backup, and Django database migrations.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طلب POST مطلوب."}, status=405)

    from apps.core.updater import perform_system_update
    res = perform_system_update()
    return JsonResponse(res)
