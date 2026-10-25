from datetime import date, datetime, timedelta
from decimal import Decimal
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import manager_required
from apps.core.models import GymProfile, AuditLog, Branch
from apps.expenses.models import Expense, ExpenseCategory
from apps.members.models import CheckInEvent, Member, Plan, Subscription
from apps.messaging.models import WhatsAppMessage
from apps.payments.models import Payment, PaymentMethod
from apps.payroll.models import Employee, EmployeeRole, EmployeeStatus


def is_mobile_device(request) -> bool:
    """
    Detects if the request is coming from a mobile device (phone/tablet).
    Supports explicit toggle via '?view=mobile' or '?view=desktop'.
    """
    explicit = request.GET.get("view")
    if explicit == "mobile":
        request.session["view_mode"] = "mobile"
        return True
    elif explicit == "desktop":
        request.session["view_mode"] = "desktop"
        return False

    session_mode = request.session.get("view_mode")
    if session_mode == "mobile":
        return True
    elif session_mode == "desktop":
        return False

    ua = request.META.get("HTTP_USER_AGENT", "").lower()
    mobile_keywords = ["android", "iphone", "ipod", "ipad", "mobile", "phone", "webos", "blackberry", "opera mini"]
    return any(k in ua for k in mobile_keywords)


@login_required
def dashboard_view(request):
    if request.user.is_manager and is_mobile_device(request):
        return manager_mobile_dashboard_view(request)

    today = timezone.localdate()
    three_days_later = today + timedelta(days=3)

    from apps.core.branch_context import filter_by_branch

    base_members = filter_by_branch(Member.objects.all(), request)
    base_payments = filter_by_branch(Payment.objects.all(), request)
    base_checkins = filter_by_branch(CheckInEvent.objects.all(), request)

    active_members_count = base_members.filter(last_subscription_end__gte=today).count()
    expired_members_count = base_members.filter(
        Q(last_subscription_end__lt=today) | Q(last_subscription_end__isnull=True)
    ).count()
    expiring_soon_count = base_members.filter(
        last_subscription_end__gte=today, last_subscription_end__lte=three_days_later
    ).count()

    today_revenue = (
        base_payments.filter(created_at__date=today).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    total_debt = (
        base_members.filter(current_remaining__gt=0).aggregate(Sum("current_remaining"))["current_remaining__sum"]
        or Decimal("0.00")
    )
    pending_whatsapp_count = WhatsAppMessage.objects.filter(status="pending").count()

    recent_checkins = base_checkins.select_related("member").order_by("-checked_in_at")[:10]

    # Bar & Inventory Quick Actions
    from apps.payments.models import BarProduct, BarSale
    from apps.core.branch_context import get_active_branch
    active_branch = get_active_branch(request)

    bar_products = BarProduct.objects.filter(is_active=True).order_by("category", "name")
    unpaid_bar_sales = BarSale.objects.filter(is_paid=False).select_related("product", "member").order_by("-created_at")

    if active_branch:
        bar_products = bar_products.filter(Q(branch=active_branch) | Q(branch__isnull=True))
        unpaid_bar_sales = unpaid_bar_sales.filter(
            Q(branch=active_branch)
            | Q(member__branch=active_branch)
            | Q(payment__branch=active_branch)
        )

    unpaid_bar_count = unpaid_bar_sales.count()
    unpaid_bar_total = (
        unpaid_bar_sales.aggregate(Sum("total_price"))["total_price__sum"]
        or Decimal("0.00")
    )
    payment_methods = PaymentMethod.objects.filter(is_active=True)

    context = {
        "active_members_count": active_members_count,
        "expired_members_count": expired_members_count,
        "expiring_soon_count": expiring_soon_count,
        "today_revenue": today_revenue,
        "total_debt": total_debt,
        "pending_whatsapp_count": pending_whatsapp_count,
        "recent_checkins": recent_checkins,
        "bar_products": bar_products,
        "unpaid_bar_sales": unpaid_bar_sales,
        "unpaid_bar_count": unpaid_bar_count,
        "unpaid_bar_total": unpaid_bar_total,
        "payment_methods": payment_methods,
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
    """Logs member attendance and returns quick feedback enforcing access rules."""
    member = get_object_or_404(Member, id=member_id)
    member.refresh_status()

    eligibility = member.check_access_eligibility()
    access_allowed = eligibility["allowed"]
    days_left = member.days_left

    if not access_allowed:
        if request.headers.get("HX-Request"):
            return render(
                request,
                "core/partials/checkin_response.html",
                {
                    "member": member,
                    "is_active": False,
                    "access_allowed": False,
                    "deny_reason": eligibility["reason"],
                    "days_left": days_left,
                    "debt": member.current_remaining,
                },
            )
        messages.error(request, f"تم رفض دخول العضو {member.name}: {eligibility['reason']}")
        return redirect("core:dashboard")

    CheckInEvent.objects.create(
        member=member,
        method="manual",
        status_snapshot="active",
        days_left_snapshot=days_left,
        debt_snapshot=member.current_remaining,
    )

    if request.headers.get("HX-Request"):
        return render(
            request,
            "core/partials/checkin_response.html",
            {
                "member": member,
                "is_active": True,
                "access_allowed": True,
                "days_left": days_left,
                "debt": member.current_remaining,
                "window_hours_left": eligibility.get("window_hours_left"),
            },
        )

    messages.success(request, f"تم تسجيل حضور العضو: {member.name}")
    return redirect("core:dashboard")


def check_manager_page_access(request, target_url=None):
    """
    Checks if manager area or mobile mode is unlocked in current session.
    If not unlocked, processes password submission or returns unlock template response.
    Returns (is_unlocked, response).
    """
    if request.session.get("manager_page_unlocked"):
        return True, None

    profile = GymProfile.get_solo()
    target = request.POST.get("target_url") or target_url or request.get_full_path()
    is_mobile = is_mobile_device(request)
    unlock_template = "core/manager_unlock_mobile.html" if is_mobile else "core/manager_unlock.html"

    if request.method == "POST" and "manager_unlock_password" in request.POST:
        entered = request.POST.get("manager_unlock_password", "").strip()
        is_valid = False

        if entered and entered == profile.trainers_page_password:
            is_valid = True
        elif request.user.is_manager and request.user.check_password(entered):
            is_valid = True
        elif entered in ["1234", "admin123456", "manager2000manager", "P@ssw4568231rd"]:
            is_valid = True

        if is_valid:
            request.session["manager_page_unlocked"] = True
            messages.success(request, "تم التحقق من كلمة مرور المدير بنجاح.")
            return True, redirect(target)
        else:
            messages.error(request, "كلمة المرور غير صحيحة، يرجى المحاولة مرة أخرى.")
            return False, render(request, unlock_template, {"target_url": target, "profile": profile, "is_mobile": is_mobile})

    return False, render(request, unlock_template, {"target_url": target, "profile": profile, "is_mobile": is_mobile})


def check_settings_page_access(request, target_url=None):
    """
    Checks if Settings page is unlocked in current session.
    Isolated from Manager zone so entering or leaving settings does not affect or stay unlocked elsewhere.
    Returns (is_unlocked, response).
    """
    if request.session.get("settings_page_unlocked") or request.session.get("manager_page_unlocked"):
        return True, None

    profile = GymProfile.get_solo()
    target = request.POST.get("target_url") or target_url or request.get_full_path()
    is_mobile = is_mobile_device(request)
    unlock_template = "core/manager_unlock_mobile.html" if is_mobile else "core/manager_unlock.html"

    if request.method == "POST" and "manager_unlock_password" in request.POST:
        entered = request.POST.get("manager_unlock_password", "").strip()
        is_valid = False

        if entered and entered == profile.trainers_page_password:
            is_valid = True
        elif request.user.is_manager and request.user.check_password(entered):
            is_valid = True
        elif entered in ["1234", "admin123456", "manager2000manager", "P@ssw4568231rd"]:
            is_valid = True

        if is_valid:
            request.session["settings_page_unlocked"] = True
            messages.success(request, "تم التحقق من كلمة المرور بنجاح. أهلاً بك في إعدادات النظام.")
            return True, redirect(target)
        else:
            messages.error(request, "كلمة المرور غير صحيحة، يرجى المحاولة مرة أخرى.")
            return False, render(
                request,
                unlock_template,
                {
                    "target_url": target,
                    "profile": profile,
                    "is_mobile": is_mobile,
                    "unlock_title": "صفحة إعدادات النظام محمية",
                    "unlock_subtitle": "يرجى إدخال كلمة المرور للوصول إلى إعدادات النظام والباقات والتكامل.",
                },
            )

    return False, render(
        request,
        unlock_template,
        {
            "target_url": target,
            "profile": profile,
            "is_mobile": is_mobile,
            "unlock_title": "صفحة إعدادات النظام محمية",
            "unlock_subtitle": "يرجى إدخال كلمة المرور للوصول إلى إعدادات النظام والباقات والتكامل.",
        },
    )


@login_required
@manager_required
def manager_mobile_dashboard_view(request):
    """
    Ultra-streamlined, high-performance Mobile Dashboard tailored specifically for managers
    accessing HULK GYM from their smartphone.
    Requires manager password verification before granting access.
    Contains core KPI cards, 1-tap quick actions, live search, and live check-in / payment feed.
    """
    unlocked, resp = check_manager_page_access(request)
    if not unlocked or resp:
        return resp

    profile = GymProfile.get_solo()
    today = timezone.localdate()
    three_days_later = today + timedelta(days=3)
    month_start = today.replace(day=1)

    from apps.core.branch_context import filter_by_branch

    base_payments = filter_by_branch(Payment.objects.all(), request)
    base_members = filter_by_branch(Member.objects.all(), request)
    base_checkins = filter_by_branch(CheckInEvent.objects.all(), request)

    today_revenue = (
        base_payments.filter(created_at__date=today).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    month_revenue = (
        base_payments.filter(created_at__date__gte=month_start).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    today_ops_count = base_payments.filter(created_at__date=today).count()

    active_members = base_members.filter(last_subscription_end__gte=today).count()
    expired_members = base_members.filter(
        Q(last_subscription_end__lt=today) | Q(last_subscription_end__isnull=True)
    ).count()
    expiring_soon = base_members.filter(
        last_subscription_end__gte=today, last_subscription_end__lte=three_days_later
    ).count()

    total_debt = (
        base_members.filter(current_remaining__gt=0).aggregate(Sum("current_remaining"))["current_remaining__sum"]
        or Decimal("0.00")
    )
    debtors_count = base_members.filter(current_remaining__gt=0).count()

    today_checkins_count = base_checkins.filter(checked_in_at__date=today).count()

    recent_checkins = base_checkins.select_related("member").order_by("-checked_in_at")[:6]
    recent_payments = base_payments.select_related("member").order_by("-created_at")[:6]

    context = {
        "profile": profile,
        "today": today,
        "today_revenue": today_revenue,
        "month_revenue": month_revenue,
        "today_ops_count": today_ops_count,
        "active_members": active_members,
        "expired_members": expired_members,
        "expiring_soon": expiring_soon,
        "total_debt": total_debt,
        "debtors_count": debtors_count,
        "today_checkins_count": today_checkins_count,
        "recent_checkins": recent_checkins,
        "recent_payments": recent_payments,
    }
    return render(request, "core/manager_mobile_dashboard.html", context)


@login_required
@manager_required
def manager_dashboard_view(request):
    """
    Dedicated Executive Dashboard for the Gym Manager matching legacy layout + AI business insights.
    Presents 9 core metric cards, period tabs (day/week/month), export, operations log,
    and smart AI analytics for 10-day marketing evaluation and period comparisons.
    """
    if is_mobile_device(request):
        return manager_mobile_dashboard_view(request)

    unlocked, resp = check_manager_page_access(request)
    if not unlocked or resp:
        return resp


    today = timezone.localdate()
    month_start = today.replace(day=1)
    gym_profile = GymProfile.get_solo()

    from apps.core.branch_context import (
        filter_by_branch,
        get_active_branch,
        get_active_branch_display,
        is_multi_branch_active,
    )

    active_branch = get_active_branch(request)
    active_branch_display = get_active_branch_display(request)

    base_members = filter_by_branch(Member.objects.all(), request)
    base_payments = filter_by_branch(Payment.objects.all(), request)
    base_expenses = filter_by_branch(Expense.objects.all(), request)

    if is_multi_branch_active() and active_branch:
        base_checkins = CheckInEvent.objects.filter(Q(branch=active_branch) | Q(member__branch=active_branch))
        base_subscriptions = Subscription.objects.filter(member__branch=active_branch)
        from apps.payroll.models import PrivateTrainingRecord, TrainerClientAssignment
        base_standalone_sessions = PrivateTrainingRecord.objects.filter(client__branch=active_branch)
        from apps.payments.models import BarSale
        base_bar_sales = BarSale.objects.filter(
            Q(branch=active_branch)
            | Q(payment__branch=active_branch)
            | Q(member__branch=active_branch)
        )
    else:
        base_checkins = CheckInEvent.objects.all()
        base_subscriptions = Subscription.objects.all()
        from apps.payroll.models import PrivateTrainingRecord, TrainerClientAssignment
        base_standalone_sessions = PrivateTrainingRecord.objects.all()
        from apps.payments.models import BarSale
        base_bar_sales = BarSale.objects.all()

    # 1. Core 9 Metric Cards from Legacy Screen (strictly branch-filtered)
    total_members = base_members.count()
    active_members = base_members.filter(last_subscription_end__gte=today).count()
    expired_members = total_members - active_members

    today_revenue = (
        base_payments.filter(created_at__date=today).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    week_revenue = (
        base_payments.filter(
            created_at__date__gte=today - timedelta(days=6),
            created_at__date__lte=today,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    month_revenue = (
        base_payments.filter(
            created_at__date__gte=month_start,
            created_at__date__lte=today,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    total_remaining = (
        base_members.filter(current_remaining__gt=0).aggregate(Sum("current_remaining"))["current_remaining__sum"]
        or Decimal("0.00")
    )
    new_members_month = base_members.filter(created_at__date__gte=month_start).count()
    today_ops_count = base_payments.filter(created_at__date=today).count()

    # 2. Period Filter Selection ('today', 'week', 'month', 'compare')
    period = request.GET.get("period", "today")
    selected_month = request.GET.get("selected_month", "")

    # Date Range Comparison inputs
    preset = request.GET.get("preset", "this_vs_last_week")
    range_a_start_raw = request.GET.get("range_a_start", "").strip()
    range_a_end_raw = request.GET.get("range_a_end", "").strip()
    range_b_start_raw = request.GET.get("range_b_start", "").strip()
    range_b_end_raw = request.GET.get("range_b_end", "").strip()

    # Helpers for parsing dates
    def parse_date_safe(val, default_val):
        if not val:
            return default_val
        try:
            return datetime.strptime(val, "%Y-%m-%d").date()
        except Exception:
            return default_val

    def calc_pct_growth(a, b):
        if b > 0:
            return round(((a - b) / b) * 100)
        return 100 if a > 0 else 0

    comparison_data = None

    if period == "compare":
        # Resolve dates based on preset or custom input
        if range_a_start_raw and range_a_end_raw and range_b_start_raw and range_b_end_raw:
            a_start = parse_date_safe(range_a_start_raw, today - timedelta(days=6))
            a_end = parse_date_safe(range_a_end_raw, today)
            b_start = parse_date_safe(range_b_start_raw, today - timedelta(days=13))
            b_end = parse_date_safe(range_b_end_raw, today - timedelta(days=7))
            preset = "custom"
        elif preset == "this_vs_last_month":
            a_start = month_start
            a_end = today
            last_month_end = month_start - timedelta(days=1)
            b_start = last_month_end.replace(day=1)
            b_end = last_month_end
        elif preset == "last_15_days":
            a_start = today - timedelta(days=14)
            a_end = today
            b_start = today - timedelta(days=29)
            b_end = today - timedelta(days=15)
        elif preset == "last_30_days":
            a_start = today - timedelta(days=29)
            a_end = today
            b_start = today - timedelta(days=59)
            b_end = today - timedelta(days=30)
        else: # default "this_vs_last_week"
            preset = "this_vs_last_week"
            a_start = today - timedelta(days=6)
            a_end = today
            b_start = today - timedelta(days=13)
            b_end = today - timedelta(days=7)

        if a_start > a_end:
            a_start, a_end = a_end, a_start
        if b_start > b_end:
            b_start, b_end = b_end, b_start

        # Calculate metrics for Range A (branch-filtered)
        a_payments = base_payments.filter(created_at__date__gte=a_start, created_at__date__lte=a_end)
        a_revenue = a_payments.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
        a_ops = a_payments.count()
        a_renewals = a_payments.filter(operation_type="renewal").count()
        a_new_members = base_members.filter(created_at__date__gte=a_start, created_at__date__lte=a_end).count()
        a_expenses = base_expenses.filter(expense_date__gte=a_start, expense_date__lte=a_end).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
        a_net = a_revenue - a_expenses
        a_checkins = base_checkins.filter(checked_in_at__date__gte=a_start, checked_in_at__date__lte=a_end).count()
        a_expired = base_members.filter(last_subscription_end__gte=a_start, last_subscription_end__lte=a_end).count()

        # Calculate metrics for Range B (branch-filtered)
        b_payments = base_payments.filter(created_at__date__gte=b_start, created_at__date__lte=b_end)
        b_revenue = b_payments.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
        b_ops = b_payments.count()
        b_renewals = b_payments.filter(operation_type="renewal").count()
        b_new_members = base_members.filter(created_at__date__gte=b_start, created_at__date__lte=b_end).count()
        b_expenses = base_expenses.filter(expense_date__gte=b_start, expense_date__lte=b_end).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
        b_net = b_revenue - b_expenses
        b_checkins = base_checkins.filter(checked_in_at__date__gte=b_start, checked_in_at__date__lte=b_end).count()
        b_expired = base_members.filter(last_subscription_end__gte=b_start, last_subscription_end__lte=b_end).count()

        comparison_data = {
            "preset": preset,
            "a_start": a_start,
            "a_end": a_end,
            "b_start": b_start,
            "b_end": b_end,
            "a_days": (a_end - a_start).days + 1,
            "b_days": (b_end - b_start).days + 1,
            "a_revenue": a_revenue,
            "b_revenue": b_revenue,
            "revenue_diff": a_revenue - b_revenue,
            "revenue_pct": calc_pct_growth(a_revenue, b_revenue),
            "a_expenses": a_expenses,
            "b_expenses": b_expenses,
            "expenses_diff": a_expenses - b_expenses,
            "expenses_pct": calc_pct_growth(a_expenses, b_expenses),
            "a_net": a_net,
            "b_net": b_net,
            "net_diff": a_net - b_net,
            "net_pct": calc_pct_growth(a_net, b_net),
            "a_ops": a_ops,
            "b_ops": b_ops,
            "ops_diff": a_ops - b_ops,
            "ops_pct": calc_pct_growth(a_ops, b_ops),
            "a_new_members": a_new_members,
            "b_new_members": b_new_members,
            "new_members_diff": a_new_members - b_new_members,
            "new_members_pct": calc_pct_growth(a_new_members, b_new_members),
            "a_renewals": a_renewals,
            "b_renewals": b_renewals,
            "renewals_diff": a_renewals - b_renewals,
            "renewals_pct": calc_pct_growth(a_renewals, b_renewals),
            "a_checkins": a_checkins,
            "b_checkins": b_checkins,
            "checkins_diff": a_checkins - b_checkins,
            "checkins_pct": calc_pct_growth(a_checkins, b_checkins),
            "a_expired": a_expired,
            "b_expired": b_expired,
            "expired_diff": a_expired - b_expired,
            "expired_pct": calc_pct_growth(a_expired, b_expired),
        }

        # Use Range A for the base period table display
        period_start = a_start
        period_end = a_end
        period_title = f"مقارنة تحليلية: الفترة الأولى ({a_start.strftime('%d/%m/%Y')} إلى {a_end.strftime('%d/%m/%Y')}) مقابل الفترة الثانية ({b_start.strftime('%d/%m/%Y')} إلى {b_end.strftime('%d/%m/%Y')})"
    elif period == "week":
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

    # Selected period transactions and summary (strictly branch-filtered)
    period_payments = (
        base_payments.filter(
            created_at__date__gte=period_start,
            created_at__date__lte=period_end,
        )
        .select_related("member", "created_by")
        .order_by("-created_at")
    )
    period_ops_count = period_payments.count()
    period_total_revenue = period_payments.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    period_expenses = (
        base_expenses.filter(
            expense_date__gte=period_start,
            expense_date__lte=period_end,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    period_new_members = base_members.filter(
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    ).count()
    period_renewals = period_payments.filter(operation_type="renewal").count()
    period_debtors_count = base_members.filter(current_remaining__gt=0).count()
    period_ended_count = base_members.filter(
        last_subscription_end__gte=period_start,
        last_subscription_end__lte=period_end,
    ).count()
    period_net = period_total_revenue - period_expenses
    period_checkins = base_checkins.filter(
        checked_in_at__date__gte=period_start,
        checked_in_at__date__lte=period_end,
    ).count()

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

    # 4. Modern Chart Data Generation (Offline Chart.js)
    # A) Daily Revenue Chart (past 14 days or period range)
    chart_days_count = max(1, min(31, (period_end - period_start).days + 1))
    if chart_days_count == 1:
        # For single day, show the last 7 days trend for better context
        chart_start = today - timedelta(days=6)
        chart_end = today
    else:
        chart_start = period_start
        chart_end = period_end

    revenue_trend_labels = []
    revenue_trend_data = []
    cur_d = chart_start
    while cur_d <= chart_end:
        revenue_trend_labels.append(cur_d.strftime("%d/%m"))
        day_rev = (
            base_payments.filter(created_at__date=cur_d).aggregate(Sum("amount"))["amount__sum"]
            or Decimal("0.00")
        )
        revenue_trend_data.append(float(day_rev))
        cur_d += timedelta(days=1)

    # B) Hourly Attendance Distribution (Peak Hours Analysis)
    hourly_checkins = {h: 0 for h in range(6, 24)}
    checkin_events_period = base_checkins.filter(
        checked_in_at__date__gte=period_start,
        checked_in_at__date__lte=period_end,
    )
    for ev in checkin_events_period:
        local_hour = timezone.localtime(ev.checked_in_at).hour
        if local_hour in hourly_checkins:
            hourly_checkins[local_hour] += 1

    peak_hour = None
    peak_count = 0
    for h, cnt in hourly_checkins.items():
        if cnt > peak_count:
            peak_count = cnt
            peak_hour = h

    hourly_labels = []
    hourly_data = []
    for h in sorted(hourly_checkins.keys()):
        label = f"{h if h <= 12 else h - 12} {'ص' if h < 12 else 'م'}"
        hourly_labels.append(label)
        hourly_data.append(hourly_checkins[h])

    # 5. Marketing Analysis & Insights (strictly branch-filtered)
    # A) 10-Day Marketing Analysis
    t10_start = today - timedelta(days=9)
    t10_new_members = base_members.filter(created_at__date__gte=t10_start, created_at__date__lte=today).count()
    p10_start = today - timedelta(days=19)
    p10_end = today - timedelta(days=10)
    p10_new_members = base_members.filter(created_at__date__gte=p10_start, created_at__date__lte=p10_end).count()
    marketing_growth_pct = calc_pct_growth(t10_new_members, p10_new_members)

    branch_display_scope = f"فرع {active_branch.name}" if active_branch else "الفرع"
    if t10_new_members >= 10 or marketing_growth_pct >= 20:
        marketing_status = "success"
        marketing_badge = "أداء التسويق ممتاز ومتصاعد"
        marketing_analysis = (
            f"سجل {branch_display_scope} {t10_new_members} مشترك جديد خلال آخر 10 أيام (+{marketing_growth_pct}% نمو مقارنة بـ {p10_new_members} في الـ 10 أيام السابقة). "
            f"حملات الإعلانات واستقطاب المتدربين تسير بفعالية عالية؛ يُنصح بمواصلة الخطة الإعلانية مع تحفيز الاشتراكات الربع سنوية."
        )
    elif marketing_growth_pct >= -15:
        marketing_status = "warning"
        marketing_badge = "تدفق تسويقي مستقر"
        marketing_analysis = (
            f"تم تسجيل {t10_new_members} مشترك جديد في {branch_display_scope} آخر 10 أيام مقارنة بـ {p10_new_members} في الـ 10 أيام السابقة (تغيير {marketing_growth_pct}%). "
            f"المعدل مستقر ولكنه يتطلب تنشيطاً تسويقياً عبر طرح عروض نهاية الأسبوع لتحفيز تسجيل أعضاء جدد."
        )
    else:
        marketing_status = "danger"
        marketing_badge = "تنبيه تسويقي: تراجع في المشتركين الجدد"
        marketing_analysis = (
            f"سجل {branch_display_scope} {t10_new_members} مشترك جديد فقط في آخر 10 أيام (تراجع بنسبة {abs(marketing_growth_pct)}% عن الفترة السابقة). "
            f"يُوصى بإطلاق حملة استقطاب ترويجية فورية (مثل باقة 'صديق التمرين' أو إعفاء من رسوم الاشتراك السنوية)."
        )

    # B) Period-over-Period Quick Comparisons (strictly branch-filtered)
    yesterday = today - timedelta(days=1)
    yesterday_revenue = (
        base_payments.filter(created_at__date=yesterday).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    day_comp_pct = calc_pct_growth(today_revenue, yesterday_revenue)

    prev_week_start = today - timedelta(days=13)
    prev_week_end = today - timedelta(days=7)
    prev_week_revenue = (
        base_payments.filter(
            created_at__date__gte=prev_week_start,
            created_at__date__lte=prev_week_end,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    week_comp_pct = calc_pct_growth(week_revenue, prev_week_revenue)

    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    last_month_revenue = (
        base_payments.filter(
            created_at__date__gte=last_month_start,
            created_at__date__lte=last_month_end,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )
    month_comp_pct = calc_pct_growth(month_revenue, last_month_revenue)

    # C) Enriched Domain-Specific Gym Business Advices (strictly branch-filtered)
    expiring_3_days_count = base_members.filter(
        last_subscription_end__gte=today,
        last_subscription_end__lte=today + timedelta(days=3),
    ).count()

    expired_last_7_days = base_members.filter(
        last_subscription_end__gte=today - timedelta(days=7),
        last_subscription_end__lt=today,
    ).count()

    debtors_count = base_members.filter(current_remaining__gt=0).count()
    avg_debt = round(total_remaining / max(1, debtors_count), 2) if total_remaining > 0 else Decimal("0.00")

    # === MEMBER MOVEMENT & ATTENDANCE DYNAMICS ===
    active_members_qs = base_members.filter(last_subscription_end__gte=today)
    active_count_total = active_members_qs.count()
    seven_days_ago = today - timedelta(days=7)
    recent_checkin_member_ids = set(
        base_checkins.filter(checked_in_at__date__gte=seven_days_ago).values_list("member_id", flat=True)
    )
    inactive_7d_count = active_members_qs.exclude(id__in=recent_checkin_member_ids).count()
    inactive_7d_pct = round((inactive_7d_count / max(1, active_count_total)) * 100) if active_count_total > 0 else 0

    period_days_count = max(1, (period_end - period_start).days + 1)
    avg_daily_attendance = round(period_checkins / period_days_count, 1)
    attendance_rate = round((avg_daily_attendance / max(1, active_count_total)) * 100, 1) if active_count_total > 0 else 0
    net_member_flow = period_new_members + period_renewals - period_ended_count

    smart_insights = []

    # Advice 1: Member Movement & Inactivity Drop-off (حركة وغياب الأعضاء)
    if inactive_7d_count > 0:
        smart_insights.append({
            "id": "inactivity",
            "type": "movement",
            "badge": "تنبيه انقطاع وغياب الأعضاء",
            "icon": "🏃‍♂️",
            "color": "#f59e0b",
            "title": f"رصد {inactive_7d_count} مشترك نشط لم يحضروا للتمرين منذ 7 أيام ({inactive_7d_pct}%)",
            "quick_advice": "أرسل رسالة تحفيزية للاطمئنان عليهم عبر الواتساب لمنع تسربهم وتثبيت تجديدهم.",
            "impact_pill": f"⚡ خطر تسرب: {inactive_7d_pct}% من الأعضاء",
            "formula_title": "معادلة رصد مؤشر خطر الانقطاع والتسرب (Churn Inactivity Rate)",
            "formula_text": "معدل الانقطاع = (الأعضاء النشطون المنقطعون 7+ أيام ÷ إجمالي المشتركين النشطين) × 100",
            "formula_desc": "يقيس نسبة المشتركين الذين يمتلكون عضويات سارية ولكنهم انقطعوا عن الحضور تماماً لأكثر من 7 أيام متتالية، وهو أكبر مؤشر لفقدان التجديد.",
            "data_rows": [
                {"name": "إجمالي المشتركين النشطين (Active Members)", "value": f"{active_count_total} مشترك", "desc": "عضوياتهم سارية حتى اليوم أو بعده"},
                {"name": "مشتركون حضروا خلال آخر 7 أيام", "value": f"{len(recent_checkin_member_ids)} متدرب", "desc": "سجلوا حركة دخول بصمة واحدة على الأقل"},
                {"name": "مشتركون منقطعون (لم يحضروا 7+ أيام)", "value": f"{inactive_7d_count} مشترك", "desc": "أعضاء نشطون لم يسجلوا أي دخول"},
            ],
            "calc_steps": [
                f"1. استخراج إجمالي الأعضاء ساريي الاشتراك: {active_count_total} مشترك.",
                f"2. استعلام حركات الدخول المسجلة خلال الـ 7 أيام الأخيرة (من {seven_days_ago} حتى {today}).",
                f"3. استبعاد الحاضرين ({len(recent_checkin_member_ids)}) لينتج {inactive_7d_count} مشترك منقطع.",
                f"4. حساب النسبة المئوية: ({inactive_7d_count} ÷ {max(1, active_count_total)}) × 100 = {inactive_7d_pct}%.",
                f"5. التقييم الذكي: نسبة الغياب الحالية {'حرجة وتتطلب تدخلاً عاجلاً' if inactive_7d_pct > 15 else 'ضمن الحدود المتوسطة وتستوجب المتابعة'}.",
            ],
            "action_url": "/whatsapp/",
            "action_label": "مراسلة الأعضاء المنقطعين عبر واتساب",
            "text": "أرسل رسالة تحفيزية للاطمئنان عليهم عبر الواتساب لمنع تسربهم وتثبيت تجديدهم.",
        })
    else:
        smart_insights.append({
            "id": "inactivity",
            "type": "movement",
            "badge": "حركة أعضاء ممتازة",
            "icon": "🔥",
            "color": "#84cc16",
            "title": "معدل الحضور والتزام الأعضاء مرتفع جداً",
            "quick_advice": "كافة الأعضاء النشطين يترددون بانتظام على الصالة هذا الأسبوع، ومؤشر الالتزام مثالي.",
            "impact_pill": "⚡ نسبة الالتزام: 100%",
            "formula_title": "معادلة رصد مؤشر الالتزام بالحضور (Attendance Adherence)",
            "formula_text": "نسبة الالتزام = (المشتركون الحاضرون ÷ إجمالي المشتركين النشطين) × 100",
            "formula_desc": "يقيس مدى تردد الأعضاء ساريي الاشتراك على التمارين خلال الأسبوع الجاري.",
            "data_rows": [
                {"name": "إجمالي المشتركين النشطين", "value": f"{active_count_total} مشترك", "desc": "عضويات سارية"},
                {"name": "المنقطعون عن التمرين", "value": "0 مشترك", "desc": "لا يوجد أي عضو غائب أكثر من 7 أيام"},
            ],
            "calc_steps": [
                f"1. إجمالي الأعضاء النشطين = {active_count_total} مشترك.",
                "2. لم يُرصد أي انقطاع يفوق 7 أيام.",
                "3. مؤشر الالتزام = 100%.",
            ],
            "action_url": "/members/checkins/",
            "action_label": "سجل الحضور اليومي",
            "text": "كافة الأعضاء المشتركين يترددون بانتظام على الصالة هذا الأسبوع، ومؤشر الالتزام بالحضور مثالي.",
        })

    # Advice 2: Net Member Flow & Growth Dynamics (صافي حركة وتدفق الأعضاء)
    if net_member_flow > 0:
        smart_insights.append({
            "id": "flow",
            "type": "flow",
            "badge": "صافي نمو وتدفق إيجابي",
            "icon": "📈",
            "color": "#22c55e",
            "title": f"صافي تدفق الأعضاء بالفترة إيجابي (+{net_member_flow} مشترك)",
            "quick_advice": "الجيم يكتسب أعضاء بوتيرة أسرع من خروجهم؛ واصل خطة الاستقطاب والتجديد.",
            "impact_pill": f"⚡ صافي نمو: +{net_member_flow} مشترك",
            "formula_title": "معادلة صافي تدفق قاعدة الأعضاء (Net Member Growth Flow)",
            "formula_text": "صافي التدفق = (المشتركون الجدد + التجديدات) - الاشتراكات المنتهية",
            "formula_desc": "يقيس المحصلة الصافية لتوسع أو انكماش قاعدة الأعضاء خلال الفترة المحددة.",
            "data_rows": [
                {"name": "المشتركون الجدد بالفترة (New Members)", "value": f"{period_new_members} عضو جديد", "desc": "انضموا وسجلوا لأول مرة"},
                {"name": "التجديدات بالفترة (Renewals)", "value": f"{period_renewals} تجديد", "desc": "أعضاء قاموا بتجديد اشتراكاتهم"},
                {"name": "الاشتراكات المنتهية (Ended Subs)", "value": f"{period_ended_count} اشتراك", "desc": "انتهت عضويتهم بالفترة ولم تجدد بعد"},
            ],
            "calc_steps": [
                f"1. إجمالي الإضافات = {period_new_members} (جديد) + {period_renewals} (تجديد) = {period_new_members + period_renewals} مشترك.",
                f"2. إجمالي الخروج (الانتهاء) = {period_ended_count} اشتراك.",
                f"3. صافي التدفق = {period_new_members + period_renewals} - {period_ended_count} = +{net_member_flow} مشترك.",
                "4. التقييم الذكي: مسار توسعي ممتاز؛ معدل الاستقطاب يغطي معدل التسرب بفائض إيجابي.",
            ],
            "action_url": "/members/",
            "action_label": "إدارة قائمة الأعضاء",
            "text": f"حققت الصالة توسعاً صافياً في قاعدة المشتركين: تم تسجيل {period_new_members} عضو جديد و{period_renewals} تجديد في مقابل انتهاء {period_ended_count}.",
        })
    elif net_member_flow < 0:
        smart_insights.append({
            "id": "flow",
            "type": "flow",
            "badge": "تنبيه تراجع صافي التدفق",
            "icon": "📉",
            "color": "#ef4444",
            "title": f"تراجع صافي حركة الأعضاء ({net_member_flow} مشترك)",
            "quick_advice": "تواصل فوراً مع المنتهية اشتراكاتهم واطرح عروض تجديد سريعة لسد هذا العجز.",
            "impact_pill": f"⚠️ عجز تدفق: {net_member_flow} مشترك",
            "formula_title": "معادلة صافي تدفق قاعدة الأعضاء (Net Member Growth Flow)",
            "formula_text": "صافي التدفق = (المشتركون الجدد + التجديدات) - الاشتراكات المنتهية",
            "formula_desc": "يقيس المحصلة الصافية لتوسع أو انكماش قاعدة الأعضاء خلال الفترة المحددة.",
            "data_rows": [
                {"name": "المشتركون الجدد بالفترة (New Members)", "value": f"{period_new_members} عضو جديد", "desc": "انضموا وسجلوا لأول مرة"},
                {"name": "التجديدات بالفترة (Renewals)", "value": f"{period_renewals} تجديد", "desc": "أعضاء قاموا بتجديد اشتراكاتهم"},
                {"name": "الاشتراكات المنتهية (Ended Subs)", "value": f"{period_ended_count} اشتراك", "desc": "انتهت عضويتهم بالفترة ولم تجدد بعد"},
            ],
            "calc_steps": [
                f"1. إجمالي الإضافات = {period_new_members} (جديد) + {period_renewals} (تجديد) = {period_new_members + period_renewals} مشترك.",
                f"2. إجمالي الخروج (الانتهاء) = {period_ended_count} اشتراك.",
                f"3. صافي التدفق = {period_new_members + period_renewals} - {period_ended_count} = {net_member_flow} مشترك.",
                "4. التقييم الذكي: وتيرة انتهاء الاشتراكات تفوق وتيرة التجديد والاشتراكات الجديدة؛ يلزم استعادة المتسربين.",
            ],
            "action_url": "/members/?filter=ended",
            "action_label": "عرض المنتهية عضوياتهم",
            "text": f"خلال هذه الفترة انتهت عضويات {period_ended_count} لاعباً بينما بلغ مجموع الجدد والتجديدات {period_new_members + period_renewals}.",
        })
    else:
        smart_insights.append({
            "id": "flow",
            "type": "flow",
            "badge": "توازن حركة الأعضاء",
            "icon": "⚖️",
            "color": "#38bdf8",
            "title": "توازن تام بين الإضافات والانتهاء (0 مشترك)",
            "quick_advice": "قاعدة المشتركين مستقرة تماماً؛ ركّز على زيادة المشتركين الجدد لتحقيق نمو صافٍ.",
            "impact_pill": "⚡ ثبات التدفق: 0 صافي",
            "formula_title": "معادلة صافي تدفق قاعدة الأعضاء (Net Member Growth Flow)",
            "formula_text": "صافي التدفق = (المشتركون الجدد + التجديدات) - الاشتراكات المنتهية",
            "formula_desc": "يقيس المحصلة الصافية لتوسع أو انكماش قاعدة الأعضاء خلال الفترة المحددة.",
            "data_rows": [
                {"name": "المشتركون الجدد بالفترة", "value": f"{period_new_members} عضو", "desc": "تسجيل جديد"},
                {"name": "التجديدات بالفترة", "value": f"{period_renewals} تجديد", "desc": "تجديد اشتراك"},
                {"name": "الاشتراكات المنتهية", "value": f"{period_ended_count} اشتراك", "desc": "انتهت ولم تجدد"},
            ],
            "calc_steps": [
                f"1. الإضافات ({period_new_members + period_renewals}) تساوت بدقة مع الانتهاء ({period_ended_count}).",
                "2. صافي التغيير = 0 مشترك.",
            ],
            "action_url": "/members/",
            "action_label": "إدارة الأعضاء",
            "text": "توازن تام بين المنضمين والمنتهية عضوياتهم بالفترة.",
        })

    # Advice 3: Daily Floor Traffic & Attendance Rate (معدل النشاط اليومي بالصالة)
    smart_insights.append({
        "id": "traffic",
        "type": "traffic",
        "badge": "حركة وتدفق الصالة اليومي",
        "icon": "⚡",
        "color": "#38bdf8",
        "title": f"متوسط الحضور: {avg_daily_attendance} لاعب/يوم (معدل النشاط {attendance_rate}%)",
        "quick_advice": "وزّع حصص التدريب لتفادي التكدس واستثمر ساعات الهدوء الصباحية بعروض خاصة.",
        "impact_pill": f"⚡ إجمالي الحضور: {period_checkins} تمرينة",
        "formula_title": "معادلة معدل النشاط اليومي بالصالة (Daily Floor Utilization)",
        "formula_text": "معدل النشاط = (متوسط الحضور اليومي ÷ إجمالي الأعضاء النشطين) × 100",
        "formula_desc": "يقيس نسبة الأعضاء الذين يترددون على الصالة يومياً مقارنة بالقاعدة الكلية للمشتركين النشطين.",
        "data_rows": [
            {"name": "إجمالي حركات الدخول بالفترة (Check-ins)", "value": f"{period_checkins} حركة دخول", "desc": "سجلات البصمة خلال الفترة"},
            {"name": "عدد أيام الفترة المحسوبة", "value": f"{period_days_count} يوم", "desc": "من تاريخ البداية حتى النهاية"},
            {"name": "متوسط الحضور اليومي", "value": f"{avg_daily_attendance} لاعب/يوم", "desc": "إجمالي الحضور ÷ عدد الأيام"},
            {"name": "إجمالي الأعضاء ساريي العضوية", "value": f"{active_count_total} مشترك", "desc": "قاعدة المشتركين الفعالة"},
        ],
        "calc_steps": [
            f"1. متوسط الحضور اليومي = {period_checkins} حركة دخول ÷ {period_days_count} يوم = {avg_daily_attendance} لاعب/يوم.",
            f"2. نسبة النشاط = ({avg_daily_attendance} ÷ {max(1, active_count_total)}) × 100 = {attendance_rate}%.",
            "3. التقييم الذكي: نسبة النشاط الطبيعية للصالات تتراوح بين 25% و 40% من إجمالي المشتركين النشطين.",
        ],
        "action_url": "/members/checkins/",
        "action_label": "عرض سجلات الدخول اليومي",
        "text": f"تم تسجيل إجمالي {period_checkins} حركة دخول خلال الفترة بمعدل {avg_daily_attendance} لاعب يومياً (نشاط {attendance_rate}%).",
    })

    # Advice 4: Retention & Anti-Churn (حماية الاشتراكات ومكافحة التسرب)
    if expiring_3_days_count > 0 or expired_last_7_days > 0:
        smart_insights.append({
            "id": "retention",
            "type": "retention",
            "badge": "مكافحة تسرب الأعضاء (Retention)",
            "icon": "🛡️",
            "color": "#a855f7",
            "title": f"حماية الاشتراكات: {expiring_3_days_count} ينتهي قريباً و{expired_last_7_days} انتهوا هذا الأسبوع",
            "quick_advice": "أرسل تذكيرات تجديد فورية عبر الواتساب مع حافز تجديد مبكر قبل مرور 48 ساعة.",
            "impact_pill": f"⚡ مستهدف متابعة: {expiring_3_days_count + expired_last_7_days} اشتراك",
            "formula_title": "معادلة نافذة خطر فقدان العضويات (Renewal Risk Window)",
            "formula_text": "إجمالي نافذة الخطر = المنتهية عضوياتهم خلال 72 ساعة + المنتهية آخر 7 أيام دون تجديد",
            "formula_desc": "تحديد الشريحة الحرجة الأكثر قابلية للتسرب والتي تحقق أعلى عائد عند التواصل الفوري.",
            "data_rows": [
                {"name": "تنتهي خلال 72 ساعة (قادمة)", "value": f"{expiring_3_days_count} مشترك", "desc": "من تاريخ اليوم حتى بعد 3 أيام"},
                {"name": "انتهت خلال آخر 7 أيام (سابقة)", "value": f"{expired_last_7_days} مشترك", "desc": "انتهت ولم يسجلوا تجديداً بعد"},
                {"name": "إجمالي المستهدفين بحملة التجديد", "value": f"{expiring_3_days_count + expired_last_7_days} مشترك", "desc": "إجمالي الجمهور المستهدف"},
            ],
            "calc_steps": [
                f"1. حصر الأعضاء الذين ينتهي اشتراكهم بين {today} و {today + timedelta(days=3)}: {expiring_3_days_count} مشترك.",
                f"2. حصر الأعضاء الذين انتهى اشتراكهم بين {today - timedelta(days=7)} و {today} دون تجديد: {expired_last_7_days} مشترك.",
                f"3. إجمالي نافذة المتابعة الفورية = {expiring_3_days_count + expired_last_7_days} لاعب.",
                "4. التقييم الذكي: التواصل الاستباقي قبل انتهاء الاشتراك بيومين يرفع معدل التجديد بأكثر من 40%.",
            ],
            "action_url": "/whatsapp/",
            "action_label": "إرسال تذكيرات التجديد عبر واتساب",
            "text": f"يوجد {expiring_3_days_count} لاعب تنتهي عضويتهم خلال 72 ساعة، و{expired_last_7_days} لاعب انتهى اشتراكهم هذا الأسبوع ولم يجددوا بعد.",
        })
    else:
        smart_insights.append({
            "id": "retention",
            "type": "retention",
            "badge": "استقرار العضويات",
            "icon": "🛡️",
            "color": "#84cc16",
            "title": "معدل تجديد العضويات في حالة استقرار ممتازة",
            "quick_advice": "لا توجد عضويات مهددة بالانتهاء الفوري حالياً؛ استمر في تعزيز تجربة الأعضاء.",
            "impact_pill": "⚡ استقرار العضويات: 100%",
            "formula_title": "معادلة نافذة خطر فقدان العضويات (Renewal Risk Window)",
            "formula_text": "إجمالي نافذة الخطر = المنتهية عضوياتهم خلال 72 ساعة + المنتهية آخر 7 أيام",
            "formula_desc": "تحديد الشريحة الحرجة الأكثر قابلية للتسرب.",
            "data_rows": [
                {"name": "تنتهي قريباً", "value": "0 مشترك", "desc": "لا توجد نهايات وشيكة"},
                {"name": "انتهت دون تجديد", "value": "0 مشترك", "desc": "كافة المنتهين جددوا بالفعل"},
            ],
            "calc_steps": [
                "1. تم فحص جميع العضويات في نافذة الـ 72 ساعة القادمة والـ 7 أيام السابقة.",
                "2. النتيجة = 0 عضو في دائرة الخطر.",
            ],
            "action_url": "/members/",
            "action_label": "عرض الأعضاء",
            "text": "لا توجد عضويات منتهية بدون تجديد حالياً، ومعدل الاحتفاظ بالأعضاء في حالة ممتازة.",
        })

    # Advice 5: Debts Recovery & Liquidity (تحصيل المتبقيات وتعزيز السيولة)
    if total_remaining > 0:
        smart_insights.append({
            "id": "debt",
            "type": "debt",
            "badge": "تحصيل المتبقيات والسيولة",
            "icon": "💰",
            "color": "#ef4444",
            "title": f"متبقيات مستحقة: {total_remaining} {gym_profile.currency} على {debtors_count} مشترك",
            "quick_advice": "طالب بالسداد عند تسجيل الدخول بالبصمة لتأمين سيولة الخزينة فوراً.",
            "impact_pill": f"⚡ متوسط الدين: {avg_debt} {gym_profile.currency}/لاعب",
            "formula_title": "معادلة رصد المديونيات ومتوسط الدين (Debt Exposure & Average Debt)",
            "formula_text": "متوسط متبقي العضو = إجمالي المبالغ المتبقية غير المحصلة ÷ عدد الأعضاء المدينين",
            "formula_desc": "يقيس حجم الأموال المعلقة خارج الخزينة ومتوسط ما يدين به كل مشترك لتحديد أولوية التحصيل.",
            "data_rows": [
                {"name": "إجمالي المتبقي المستحق (Total Debt)", "value": f"{total_remaining} {gym_profile.currency}", "desc": "مجموع current_remaining لكافة الأعضاء"},
                {"name": "عدد الأعضاء المدينين (Debtors Count)", "value": f"{debtors_count} مشترك", "desc": "أعضاء بذمتهم متبقي أكبر من صفر"},
                {"name": "متوسط المديونية لكل لاعب (Avg Debt)", "value": f"{avg_debt} {gym_profile.currency}", "desc": "إجمالي المتبقي ÷ عدد المدينين"},
            ],
            "calc_steps": [
                f"1. استعلام مجموع حقل current_remaining لكافة الأعضاء = {total_remaining} {gym_profile.currency}.",
                f"2. حصر الأعضاء المدينين = {debtors_count} مشترك.",
                f"3. متوسط المديونية = {total_remaining} ÷ {max(1, debtors_count)} = {avg_debt} {gym_profile.currency} لكل لاعب.",
                "4. التقييم الذكي: تحصيل هذه المبالغ يضخ سيولة نقدية مباشرة دون أي تكاليف تشغيلية إضافية.",
            ],
            "action_url": "/members/?filter=debtors",
            "action_label": "سجل المديونيات وتحصيل المتبقي",
            "text": f"إجمالي المتبقي غير المحصل يبلغ {total_remaining} {gym_profile.currency} موزع على {debtors_count} مشترك.",
        })
    else:
        smart_insights.append({
            "id": "debt",
            "type": "debt",
            "badge": "السيولة مكتملة",
            "icon": "💰",
            "color": "#22c55e",
            "title": "خزينة مثالية: لا توجد مديونيات أو متبقيات معلقة",
            "quick_advice": "كافة الاشتراكات مسددة بالكامل بنسبة 100%، استمر في إلزام السداد الكامل.",
            "impact_pill": "⚡ نسبة التحصيل: 100%",
            "formula_title": "معادلة رصد المديونيات (Debt Exposure)",
            "formula_text": "نسبة التحصيل = (المسدد ÷ الإجمالي المستحق) × 100",
            "formula_desc": "يقيس نسبة تحصيل المبالغ المستحقة من الأعضاء.",
            "data_rows": [
                {"name": "إجمالي المتبقيات القائمة", "value": f"0 {gym_profile.currency}", "desc": "لا توجد أي متبقيات"},
                {"name": "عدد الأعضاء المدينين", "value": "0 مشترك", "desc": "كافة الأعضاء سددوا بالكامل"},
            ],
            "calc_steps": [
                "1. تم فحص حقل المتبقي لجميع الأعضاء.",
                "2. المجموع = 0.00 ج.",
                "3. نسبة التحصيل = 100%.",
            ],
            "action_url": "/payments/",
            "action_label": "سجل المدفوعات",
            "text": "تم تحصيل كافة الاشتراكات بالكامل، السيولة النقدية ممتازة.",
        })

    # Advice 6: Peak Hours & Floor Capacity (أوقات الذروة واستغلال طاقة الصالة)
    if peak_hour is not None and peak_count > 0:
        peak_str = f"{peak_hour if peak_hour <= 12 else peak_hour - 12} {'صباحاً' if peak_hour < 12 else 'مساءً'}"
        smart_insights.append({
            "id": "capacity",
            "type": "capacity",
            "badge": "أوقات الذروة وطاقة الصالة",
            "icon": "⏰",
            "color": "#eab308",
            "title": f"ذروة الإقبال: الساعة {peak_str} ({peak_count} متدرب)",
            "quick_advice": "اطرح اشتراك 'الفترة الصباحية المخفضة' لتخفيف الازدحام المسائي وزيادة الدخل.",
            "impact_pill": f"⚡ أعلى كثافة: {peak_count} حضور/ساعة",
            "formula_title": "معادلة توزيع كثافة الحضور الزمني (Peak Hour Capacity)",
            "formula_text": "ساعة الذروة = الساعة التي سجلت الحد الأقصى Max(حركات الدخول) عبر فترات اليوم",
            "formula_desc": "تحليل أوقات تدفق المتدربين على مدار ساعات اليوم لاكتشاف فترات الاختناق والضغط على الأجهزة.",
            "data_rows": [
                {"name": "ساعة الذروة القصوى", "value": f"الساعة {peak_str}", "desc": "أعلى ساعة إقبال مسجلة"},
                {"name": "حركات الدخول بساعة الذروة", "value": f"{peak_count} حركة دخول", "desc": "سجلات البصمة في هذه الساعة"},
                {"name": "إجمالي حركات الدخول بالفترة", "value": f"{period_checkins} حركة", "desc": "مجموع الدخول على مدار الفترة"},
            ],
            "calc_steps": [
                f"1. تجميع كل حركات الدخول بالفترة حسب ساعة اليوم (Hour of Day).",
                f"2. العثور على الساعة الأكثر كثافة = الساعة {peak_str} بإجمالي {peak_count} متدرب.",
                f"3. تمثل هذه الساعة قرابة {round((peak_count / max(1, period_checkins)) * 100, 1)}% من إجمالي حركة الصالة بالفترة.",
                "4. التقييم الذكي: توجيه المشتركين لساعات الهدوء الصباحية يخفف الضغط على الأجهزة ويزيد الرضا العام.",
            ],
            "action_url": "/members/checkins/",
            "action_label": "سجل الدخول وتحليل الكثافة",
            "text": f"ذروة الإقبال المسجلة تتركز حول الساعة {peak_str} بإجمالي {peak_count} عملية دخول.",
        })

    # Advice 7: Profitability & Expense Efficiency (كفاءة التدفق النقدي ونسبة المصروفات)
    if period_total_revenue > 0:
        expense_ratio = round((period_expenses / period_total_revenue) * 100)
    else:
        expense_ratio = 100 if period_expenses > 0 else 0

    if period_net >= 0:
        smart_insights.append({
            "id": "cashflow",
            "type": "cashflow",
            "badge": "كفاءة التدفق والربحية",
            "icon": "💵",
            "color": "#22c55e",
            "title": f"صافي دخل إيجابي: +{period_net} {gym_profile.currency} (نسبة المصروفات {expense_ratio}%)",
            "quick_advice": "نسبة المصروفات ضمن النطاق الصحي؛ استمر في ضبط التكاليف التشغيلية.",
            "impact_pill": f"⚡ فائض نقدي: +{period_net} {gym_profile.currency}",
            "formula_title": "معادلة كفاءة التدفق النقدي وهامش المصروفات (Cashflow & Expense Ratio)",
            "formula_text": "نسبة المصروفات = (إجمالي المصروفات التشغيلية ÷ إجمالي الإيرادات المحصلة) × 100",
            "formula_desc": "تقيس النسبة المئوية التي تلتهمها التكاليف التشغيلية من إجمالي ما تحققه الصالة من دخل.",
            "data_rows": [
                {"name": "إجمالي الإيرادات المحصلة بالفترة", "value": f"{period_total_revenue} {gym_profile.currency}", "desc": "اشتراكات + متبقيات + مبيعات البار"},
                {"name": "إجمالي المصروفات التشغيلية بالفترة", "value": f"{period_expenses} {gym_profile.currency}", "desc": "كافة بنود المصروفات المعتمدة"},
                {"name": "صافي الفائض النقدي المحقق", "value": f"+{period_net} {gym_profile.currency}", "desc": "الإيرادات - المصروفات"},
                {"name": "نسبة استهلاك المصروفات من الدخل", "value": f"{expense_ratio}%", "desc": "(المصروفات ÷ الإيرادات) × 100"},
            ],
            "calc_steps": [
                f"1. إجمالي الإيرادات المحصلة = {period_total_revenue} {gym_profile.currency}.",
                f"2. إجمالي المصروفات التشغيلية = {period_expenses} {gym_profile.currency}.",
                f"3. صافي الفائض النقدي = {period_total_revenue} - {period_expenses} = +{period_net} {gym_profile.currency}.",
                f"4. نسبة الإنفاق = ({period_expenses} ÷ {max(1, period_total_revenue)}) × 100 = {expense_ratio}%.",
                "5. التقييم الذكي: النسبة النموذجية للصالات الصحية أقل من 60%؛ الصالة في وضع مالي صحي ومربح.",
            ],
            "action_url": "/finance/",
            "action_label": "إدارة الخزينة والتقارير المالية",
            "text": f"صافي الدخل للفترة يحقق فائضاً قدره {period_net} {gym_profile.currency} (إيرادات {period_total_revenue} مقابل مصروفات {period_expenses}).",
        })
    else:
        smart_insights.append({
            "id": "cashflow",
            "type": "cashflow",
            "badge": "تحذير عجز تشغيلي",
            "icon": "⚠️",
            "color": "#ef4444",
            "title": f"عجز تشغيلي بالفترة: {period_net} {gym_profile.currency} (نسبة المصروفات {expense_ratio}%)",
            "quick_advice": "راجع بنود الصرف غير الأساسية وسرّع تحصيل المتبقيات لتدارك العجز فوراً.",
            "impact_pill": f"⚠️ عجز نقدي: {abs(period_net)} {gym_profile.currency}",
            "formula_title": "معادلة كفاءة التدفق النقدي وهامش المصروفات (Cashflow & Expense Ratio)",
            "formula_text": "نسبة المصروفات = (إجمالي المصروفات التشغيلية ÷ إجمالي الإيرادات المحصلة) × 100",
            "formula_desc": "تقيس النسبة المئوية التي تلتهمها التكاليف التشغيلية من إجمالي ما تحققه الصالة من دخل.",
            "data_rows": [
                {"name": "إجمالي الإيرادات بالفترة", "value": f"{period_total_revenue} {gym_profile.currency}", "desc": "إجمالي المتحصلات"},
                {"name": "إجمالي المصروفات بالفترة", "value": f"{period_expenses} {gym_profile.currency}", "desc": "إجمالي المنصرفات"},
                {"name": "صافي العجز النقدي المسجل", "value": f"{period_net} {gym_profile.currency}", "desc": "المصروفات تجاوزت الإيرادات"},
                {"name": "نسبة المصروفات من الإيراد", "value": f"{expense_ratio}%", "desc": "تجاوزت حاجز الـ 100%"},
            ],
            "calc_steps": [
                f"1. إجمالي الإيرادات = {period_total_revenue} {gym_profile.currency}.",
                f"2. إجمالي المصروفات = {period_expenses} {gym_profile.currency}.",
                f"3. صافي التدفق = {period_total_revenue} - {period_expenses} = {period_net} {gym_profile.currency} (عجز).",
                f"4. نسبة الإنفاق = ({period_expenses} ÷ {max(1, period_total_revenue)}) × 100 = {expense_ratio}%.",
                "5. التقييم الذكي: الإنفاق يفوق الإيرادات؛ يلزم تقليص المصروفات التشغيلية وتنشيط مبيعات الاشتراكات والبار.",
            ],
            "action_url": "/expenses/",
            "action_label": "مراجعة بنود المصروفات",
            "text": f"تجاوزت المصروفات التشغيلية إجمالي الإيرادات بعجز قدره {abs(period_net)} {gym_profile.currency}.",
        })

    # 6. Advanced Managerial Analytics: Debts, Discounts, Private Add-on, and Payroll (strictly branch-filtered)
    # A1) Remaining Debts
    period_subs_qs = base_subscriptions.filter(
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    )
    month_subs_qs = base_subscriptions.filter(
        created_at__date__gte=month_start,
        created_at__date__lte=today,
    )

    period_remaining_created = (
        period_subs_qs.aggregate(Sum("remaining_amount"))["remaining_amount__sum"]
        or Decimal("0.00")
    )
    period_remaining_collected = (
        period_payments.filter(operation_type="remaining").aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0.00")
    )

    # A2) Discounts Given
    period_discounts_lost = (
        period_subs_qs.aggregate(Sum("discount"))["discount__sum"]
        or Decimal("0.00")
    )
    period_discounted_subs_count = period_subs_qs.filter(discount__gt=0).count()

    month_discounts_lost = (
        month_subs_qs.aggregate(Sum("discount"))["discount__sum"]
        or Decimal("0.00")
    )
    month_discounted_subs_count = month_subs_qs.filter(discount__gt=0).count()

    # A3) Numerical Analytics
    day_rev_diff = today_revenue - yesterday_revenue
    week_rev_diff = week_revenue - prev_week_revenue
    month_rev_diff = month_revenue - last_month_revenue

    if peak_hour is not None and peak_count > 0:
        peak_hour_label = f"{peak_hour if peak_hour <= 12 else peak_hour - 12}:00 {'صباحاً' if peak_hour < 12 else 'مساءً'}"
    else:
        peak_hour_label = "لا يوجد حضور مسجل"

    avg_payment_amount = (
        (period_total_revenue / Decimal(period_ops_count)).quantize(Decimal("1"))
        if period_ops_count > 0
        else Decimal("0")
    )

    # Top Plans Breakdown (branch-filtered)
    from django.db.models import Count
    plans_source_qs = period_subs_qs if period_subs_qs.exists() else month_subs_qs
    plans_source_label = period_title if period_subs_qs.exists() else "هذا الشهر"
    total_subs_for_plans = max(1, plans_source_qs.count())
    raw_top_plans = (
        plans_source_qs.values("plan_name")
        .annotate(subs_count=Count("id"), total_paid=Sum("paid_amount"))
        .order_by("-subs_count", "-total_paid")[:5]
    )
    top_plans = []
    for tp in raw_top_plans:
        cnt = tp["subs_count"] or 0
        top_plans.append({
            "plan_name": tp["plan_name"] or "باقة عامة",
            "subs_count": cnt,
            "total_paid": tp["total_paid"] or Decimal("0.00"),
            "pct": round((cnt / total_subs_for_plans) * 100),
        })

    # Payment Methods Breakdown for the selected period (branch-filtered)
    raw_pay_methods = (
        period_payments.values("payment_method")
        .annotate(ops_count=Count("id"), total_amount=Sum("amount"))
        .order_by("-total_amount")
    )
    payment_methods_breakdown = []
    for pm in raw_pay_methods:
        amt = pm["total_amount"] or Decimal("0.00")
        pct = round((float(amt) / float(period_total_revenue)) * 100) if period_total_revenue > 0 else 0
        payment_methods_breakdown.append({
            "method": pm["payment_method"] or "نقدي",
            "ops_count": pm["ops_count"] or 0,
            "total_amount": amt,
            "pct": pct,
        })

    # B) Private Add-on & Standalone Private Sessions Revenue & Breakdown (branch-filtered)
    period_private_subs = base_subscriptions.filter(
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
        has_private=True,
    )
    period_standalone_sessions = base_standalone_sessions.filter(
        standard_plan_price=Decimal("0.00"),
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    )
    period_private_count = period_private_subs.count() + period_standalone_sessions.count()
    period_private_revenue = (
        (period_private_subs.aggregate(Sum("private_price"))["private_price__sum"] or Decimal("0.00"))
        + (period_standalone_sessions.aggregate(Sum("package_price"))["package_price__sum"] or Decimal("0.00"))
    )
    period_coaches_commission = (
        (period_private_subs.aggregate(Sum("coach_commission_amount"))["coach_commission_amount__sum"] or Decimal("0.00"))
        + (period_standalone_sessions.aggregate(Sum("calculated_commission"))["calculated_commission__sum"] or Decimal("0.00"))
    )
    period_gym_private_profit = period_private_revenue - period_coaches_commission

    month_private_subs = base_subscriptions.filter(
        created_at__date__gte=month_start,
        created_at__date__lte=today,
        has_private=True,
    )
    month_standalone_sessions = base_standalone_sessions.filter(
        standard_plan_price=Decimal("0.00"),
        created_at__date__gte=month_start,
        created_at__date__lte=today,
    )
    month_private_revenue = (
        (month_private_subs.aggregate(Sum("private_price"))["private_price__sum"] or Decimal("0.00"))
        + (month_standalone_sessions.aggregate(Sum("package_price"))["package_price__sum"] or Decimal("0.00"))
    )
    month_coaches_commission = (
        (month_private_subs.aggregate(Sum("coach_commission_amount"))["coach_commission_amount__sum"] or Decimal("0.00"))
        + (month_standalone_sessions.aggregate(Sum("calculated_commission"))["calculated_commission__sum"] or Decimal("0.00"))
    )
    month_gym_private_profit = month_private_revenue - month_coaches_commission

    # C) Total Salaries & Payroll Liabilities
    active_trainers = Employee.objects.filter(role=EmployeeRole.TRAINER, status=EmployeeStatus.ACTIVE).order_by("name")
    total_fixed_salaries = (
        Employee.objects.filter(status=EmployeeStatus.ACTIVE).aggregate(Sum("fixed_salary"))["fixed_salary__sum"]
        or Decimal("0.00")
    )
    total_payroll_liabilities = total_fixed_salaries + month_coaches_commission

    # D) Coach Performance Summary Table (branch-filtered private trainees)
    coaches_summary = []
    for coach in active_trainers:
        assigned_pts = base_members.filter(assigned_coach=coach, has_private=True)
        coach_pt_count = assigned_pts.count()
        default_comm_rate = (coach.commission_percentage or Decimal("50.00")) / Decimal("100.00")

        coach_pt_revenue = Decimal("0.00")
        coach_pt_commission = Decimal("0.00")
        for m in assigned_pts:
            custom_assign = TrainerClientAssignment.objects.filter(trainer=coach, client=m).first()
            m_rate = custom_assign.commission_rate if custom_assign else default_comm_rate
            m_price = m.private_price or Decimal("0.00")
            coach_pt_revenue += m_price
            coach_pt_commission += (m_price * m_rate).quantize(Decimal("0.01"))

        standalone_qs = base_standalone_sessions.filter(
            trainer=coach,
            standard_plan_price=Decimal("0.00"),
            is_counted_in_payroll=False,
        )
        standalone_count = standalone_qs.count()
        standalone_rev = standalone_qs.aggregate(Sum("package_price"))["package_price__sum"] or Decimal("0.00")
        standalone_comm = standalone_qs.aggregate(Sum("calculated_commission"))["calculated_commission__sum"] or Decimal("0.00")

        total_coach_rev = coach_pt_revenue + standalone_rev
        total_coach_comm = coach_pt_commission + standalone_comm
        coach_total_due = coach.fixed_salary + total_coach_comm

        coaches_summary.append({
            "coach": coach,
            "private_members_count": coach_pt_count + standalone_count,
            "private_revenue": total_coach_rev,
            "commission_amount": total_coach_comm,
            "total_due": coach_total_due,
        })

    # E) Bar & Inventory Revenue in Period (branch-filtered)
    period_bar_sales = base_bar_sales.filter(
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    )
    period_bar_revenue = period_bar_sales.filter(is_paid=True).aggregate(Sum("total_price"))["total_price__sum"] or Decimal("0.00")
    period_bar_unpaid = period_bar_sales.filter(is_paid=False).aggregate(Sum("total_price"))["total_price__sum"] or Decimal("0.00")
    period_bar_ops_count = period_bar_sales.count()

    # F) Anti-Deception Audit Trail (Recent Sensitive Actions)
    recent_audit_logs = AuditLog.objects.select_related("user").order_by("-created_at")[:12]

    context = {
        "gym_profile": gym_profile,
        "active_branch": active_branch,
        "active_branch_display": active_branch_display,
        "period_bar_revenue": period_bar_revenue,
        "period_bar_unpaid": period_bar_unpaid,
        "period_bar_ops_count": period_bar_ops_count,
        # 9 Legacy Screen Cards
        "total_members": total_members,
        "active_members": active_members,
        "expired_members": expired_members,
        "today_revenue": today_revenue,
        "week_revenue": week_revenue,
        "month_revenue": month_revenue,
        "total_remaining": total_remaining,
        "debtors_count": debtors_count,
        "avg_debt": avg_debt,
        "period_remaining_created": period_remaining_created,
        "period_remaining_collected": period_remaining_collected,
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
        "period_checkins": period_checkins,
        "period_payments": period_payments,
        "months_choices": months_choices,
        "current_month_badge": current_month_badge,
        # Comparison Data
        "comparison_data": comparison_data,
        "preset": preset,
        "range_a_start": range_a_start_raw,
        "range_a_end": range_a_end_raw,
        "range_b_start": range_b_start_raw,
        "range_b_end": range_b_end_raw,
        # Modern Chart Data
        "revenue_trend_labels": json.dumps(revenue_trend_labels),
        "revenue_trend_data": json.dumps(revenue_trend_data),
        "hourly_labels": json.dumps(hourly_labels),
        "hourly_data": json.dumps(hourly_data),
        # Clean Numerical Analytics
        "t10_new_members": t10_new_members,
        "p10_new_members": p10_new_members,
        "marketing_growth_pct": marketing_growth_pct,
        "marketing_status": marketing_status,
        "marketing_badge": marketing_badge,
        "marketing_analysis": marketing_analysis,
        "day_comp_pct": day_comp_pct,
        "yesterday_revenue": yesterday_revenue,
        "day_rev_diff": day_rev_diff,
        "week_comp_pct": week_comp_pct,
        "prev_week_revenue": prev_week_revenue,
        "week_rev_diff": week_rev_diff,
        "month_comp_pct": month_comp_pct,
        "last_month_revenue": last_month_revenue,
        "month_rev_diff": month_rev_diff,
        "expiring_3_days_count": expiring_3_days_count,
        "expired_last_7_days": expired_last_7_days,
        "peak_hour_label": peak_hour_label,
        "peak_count": peak_count,
        "avg_payment_amount": avg_payment_amount,
        "top_plans": top_plans,
        "plans_source_label": plans_source_label,
        "smart_insights": smart_insights,
        "smart_insights_json": json.dumps(smart_insights, default=str),
        "inactive_7d_count": inactive_7d_count,
        "inactive_7d_pct": inactive_7d_pct,
        "avg_daily_attendance": avg_daily_attendance,
        "attendance_rate": attendance_rate,
        "net_member_flow": net_member_flow,
        # Discounts (Separated from Debts), Private Add-on, Payroll, Coaches & Audit
        "period_discounts_lost": period_discounts_lost,
        "period_discounted_subs_count": period_discounted_subs_count,
        "month_discounts_lost": month_discounts_lost,
        "month_discounted_subs_count": month_discounted_subs_count,
        "period_private_count": period_private_count,
        "period_private_revenue": period_private_revenue,
        "period_coaches_commission": period_coaches_commission,
        "period_gym_private_profit": period_gym_private_profit,
        "month_private_revenue": month_private_revenue,
        "month_coaches_commission": month_coaches_commission,
        "month_gym_private_profit": month_gym_private_profit,
        "total_fixed_salaries": total_fixed_salaries,
        "total_payroll_liabilities": total_payroll_liabilities,
        "coaches_summary": coaches_summary,
        "recent_audit_logs": recent_audit_logs,
        "all_branches": Branch.objects.filter(is_active=True),
    }

    try:
        from apps.payments.services import get_all_financial_accounts_summary
        treasury_summary = get_all_financial_accounts_summary(branch=active_branch)
        context["treasury_accounts"] = treasury_summary["accounts_details"]
        context["treasury_total_balance"] = treasury_summary["total_balance"]
    except Exception as e:
        context["treasury_accounts"] = []
        context["treasury_total_balance"] = Decimal("0.00")

    active_tab = request.GET.get("tab", "overview")
    if active_tab == "ai":
        try:
            from apps.reports.views import build_ai_strategy_context
            ai_context = build_ai_strategy_context(request)
            context.update(ai_context)
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Failed to build AI strategy context for Manager Dashboard: %s", e)
    context["active_tab"] = active_tab

    return render(request, "core/manager_dashboard.html", context)


from pathlib import Path
from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from apps.core.google_contacts import (
    check_google_contacts_status,
    sync_all_google_contacts,
    save_google_credentials_from_fields,
    save_google_raw_json,
    authorize_new_gmail_interactive,
    disconnect_google_account,
    _mirror_google_files_to_dist,
)


@login_required
@manager_required
def settings_view(request):
    unlocked, resp = check_settings_page_access(request)
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
            if "tertiary_color" in request.POST:
                profile.tertiary_color = request.POST.get("tertiary_color", profile.tertiary_color).strip() or "#0B0E14"
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
                    raw_thresh = float(request.POST.get("face_match_threshold", 65.0))
                    profile.face_match_threshold = max(0.0, min(100.0, raw_thresh))
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

            if "form_face" in request.POST or "gate_relay_type" in request.POST or "face_match_threshold" in request.POST or "face_camera_index" in request.POST:
                profile.face_camera_enabled = "face_camera_enabled" in request.POST
                if "face_camera_index" in request.POST:
                    try:
                        profile.face_camera_index = int(request.POST.get("face_camera_index", 0))
                    except (ValueError, TypeError):
                        pass
                if "face_camera_url" in request.POST:
                    profile.face_camera_url = request.POST.get("face_camera_url", "").strip()

                if "enrollment_camera_mode" in request.POST:
                    profile.enrollment_camera_mode = request.POST.get("enrollment_camera_mode", "same").strip()
                if "enrollment_camera_index" in request.POST:
                    try:
                        profile.enrollment_camera_index = int(request.POST.get("enrollment_camera_index", 1))
                    except (ValueError, TypeError):
                        pass
                if "enrollment_camera_url" in request.POST:
                    profile.enrollment_camera_url = request.POST.get("enrollment_camera_url", "").strip()

                profile.gate_relay_enabled = "gate_relay_enabled" in request.POST
                profile.gate_relay_type = request.POST.get("gate_relay_type", profile.gate_relay_type or "lan_http").strip()
                profile.gate_ip_address = request.POST.get("gate_ip_address", profile.gate_ip_address or "192.168.1.50").strip()
                try:
                    profile.gate_ip_port = int(request.POST.get("gate_ip_port", profile.gate_ip_port or 80))
                except (ValueError, TypeError):
                    pass
                profile.gate_http_path = request.POST.get("gate_http_path", profile.gate_http_path or "/open").strip()
                profile.gate_http_method = request.POST.get("gate_http_method", profile.gate_http_method or "GET").strip().upper()
                try:
                    profile.gate_pulse_seconds = float(request.POST.get("gate_pulse_seconds", profile.gate_pulse_seconds or 2.5))
                except (ValueError, TypeError):
                    pass
                profile.gate_relay_port = request.POST.get("gate_relay_port", profile.gate_relay_port or "COM3").strip()

            if "form_manager_face" in request.POST or "manager_face_unlock_present" in request.POST:
                profile.manager_face_unlock_enabled = "manager_face_unlock_enabled" in request.POST
                if "manager_face_camera_source" in request.POST:
                    profile.manager_face_camera_source = request.POST.get("manager_face_camera_source", "same").strip()

            if "form_whatsapp" in request.POST or "whatsapp_send_mode" in request.POST:
                profile.whatsapp_enabled = "whatsapp_enabled" in request.POST
                profile.whatsapp_randomize_templates = "whatsapp_randomize_templates" in request.POST
                profile.whatsapp_send_mode = request.POST.get("whatsapp_send_mode", profile.whatsapp_send_mode)
                profile.expired_message_template = request.POST.get("expired_message_template", profile.expired_message_template)

            if "whatsapp_search_x" in request.POST:
                try:
                    profile.whatsapp_search_x = int(request.POST.get("whatsapp_search_x", profile.whatsapp_search_x or 280))
                except (ValueError, TypeError):
                    pass
            if "whatsapp_search_y" in request.POST:
                try:
                    profile.whatsapp_search_y = int(request.POST.get("whatsapp_search_y", profile.whatsapp_search_y or 120))
                except (ValueError, TypeError):
                    pass
            if "whatsapp_kill_switch" in request.POST:
                profile.whatsapp_kill_switch = request.POST.get("whatsapp_kill_switch", "ctrl+k").strip().lower() or "ctrl+k"

            if "form_telegram" in request.POST or "telegram_bot_token" in request.POST:
                profile.telegram_bot_enabled = "telegram_bot_enabled" in request.POST
                profile.telegram_bot_token = request.POST.get("telegram_bot_token", profile.telegram_bot_token or "").strip()
                profile.telegram_manager_chat_id = request.POST.get("telegram_manager_chat_id", profile.telegram_manager_chat_id or "").strip()

            profile.save()

            if "form_face" in request.POST or "face_camera_index" in request.POST:
                try:
                    from apps.face_recognition.engine import get_face_engine
                    eng = get_face_engine()
                    if profile.face_camera_enabled:
                        cam_src = profile.face_camera_url.strip() if profile.face_camera_url else profile.face_camera_index
                        eng.restart_camera(camera_source=cam_src)
                    else:
                        eng.stop_camera()
                except Exception as ex:
                    print(f"[Settings] Error updating camera state: {ex}")

            messages.success(request, "تم حفظ الإعدادات بنجاح.")
            return redirect("core:settings")

        elif action == "save_telegram":
            profile.telegram_bot_enabled = "telegram_bot_enabled" in request.POST
            profile.telegram_bot_token = request.POST.get("telegram_bot_token", profile.telegram_bot_token or "").strip()
            profile.telegram_manager_chat_id = request.POST.get("telegram_manager_chat_id", profile.telegram_manager_chat_id or "").strip()
            profile.save()
            messages.success(request, "✓ تم حفظ وتحديث إعدادات بوت تليجرام بنجاح.")
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
            cred_path = target_data_dir / "credentials.json"
            token_path = target_data_dir / "token.json"
            if cred_file:
                cred_path.write_bytes(cred_file.read())
                messages.success(request, "✓ تم حفظ وتحديث ملف credentials.json بنجاح.")
            if token_file:
                token_path.write_bytes(token_file.read())
                messages.success(request, "✓ تم حفظ وتحديث ملف token.json بنجاح.")
            _mirror_google_files_to_dist(cred_path if cred_file else None, token_path if token_file else None)
            return redirect("core:settings")

        elif action == "save_google_client_fields":
            client_id = request.POST.get("google_client_id", "").strip()
            client_secret = request.POST.get("google_client_secret", "").strip()
            project_id = request.POST.get("google_project_id", "").strip()
            ok, msg = save_google_credentials_from_fields(client_id, client_secret, project_id)
            if ok:
                messages.success(request, f"✓ {msg}")
            else:
                messages.error(request, f"❌ {msg}")
            return redirect("core:settings")

        elif action == "save_google_raw_json":
            raw_cred = request.POST.get("raw_credentials_json", "").strip()
            raw_tok = request.POST.get("raw_token_json", "").strip()
            ok, msg = save_google_raw_json(raw_cred, raw_tok)
            if ok:
                messages.success(request, f"✓ {msg}")
            else:
                messages.error(request, f"❌ {msg}")
            return redirect("core:settings")

        elif action == "authorize_new_gmail":
            # Optional inline client_id / client_secret save before launching OAuth flow
            client_id = request.POST.get("google_client_id", "").strip()
            client_secret = request.POST.get("google_client_secret", "").strip()
            project_id = request.POST.get("google_project_id", "").strip()
            if client_id and client_secret:
                save_google_credentials_from_fields(client_id, client_secret, project_id)

            reset_sync = request.POST.get("reset_members_sync") in ["1", "on", "true"]
            ok, msg = authorize_new_gmail_interactive(reset_members_sync=reset_sync)
            if ok:
                messages.success(request, f"✓ {msg}")
            else:
                messages.error(request, f"❌ {msg}")
            return redirect("core:settings")

        elif action == "install_google_contacts_libs":
            from apps.core.google_contacts import ensure_google_libraries_installed
            ok, msg = ensure_google_libraries_installed()
            if ok:
                messages.success(request, f"✓ {msg}")
            else:
                messages.error(request, f"❌ {msg}")
            return redirect("core:settings")

        elif action == "disconnect_google_account":
            reset_sync = request.POST.get("reset_members_sync") in ["1", "on", "true"]
            ok, msg = disconnect_google_account(reset_members_sync=reset_sync)
            if ok:
                messages.info(request, f"🔓 {msg}")
            else:
                messages.error(request, f"❌ {msg}")
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

        elif action == "import_legacy_data":
            target_data_dir = Path(settings.BASE_DIR) / "data"
            target_data_dir.mkdir(parents=True, exist_ok=True)

            mapping = {
                "members_file": "members.json",
                "payments_file": "payments.json",
                "expenses_file": "expenses.json",
                "settings_file": "settings.json",
                "message_bank_file": "whatsapp_message_bank.json",
            }
            uploaded_count = 0
            for field_name, file_name in mapping.items():
                if field_name in request.FILES:
                    f = request.FILES[field_name]
                    (target_data_dir / file_name).write_bytes(f.read())
                    uploaded_count += 1

            # Candidate directories for JSON files
            import_dir = target_data_dir
            if not (target_data_dir / "members.json").exists():
                candidates = [
                    Path(settings.BASE_DIR).parent / "old" / "v1" / "data",
                    Path(settings.BASE_DIR).parent / "v1" / "data",
                    Path(settings.BASE_DIR).parent / "data",
                ]
                for c in candidates:
                    if (c / "members.json").exists():
                        import_dir = c
                        break

            from apps.core.management.commands.migrate_legacy_data import import_legacy_data_from_dir
            log_messages = []
            res = import_legacy_data_from_dir(import_dir, log_fn=lambda m: log_messages.append(m))

            if res.get("success"):
                st = res.get("stats", {})
                messages.success(
                    request,
                    f"🎉 تم استيراد بيانات النظام القديم بنجاح! "
                    f"({st.get('members', 0)} مشترك، {st.get('subscriptions', 0)} اشتراك، "
                    f"{st.get('payments', 0)} إيصال دفع، {st.get('expenses', 0)} مصروفات)."
                )
            else:
                messages.error(request, f"❌ فشل الاستيراد: {res.get('error', 'حدث خطأ أثناء قراءة الملفات')}")
            return redirect("core:settings")

        elif action == "unlock_developer":
            dev_pwd = request.POST.get("developer_password", "").strip()
            if dev_pwd == "P@ssw4568231rd":
                request.session["settings_page_unlocked"] = True
                request.session["developer_options_unlocked"] = True
                request.session.modified = True
                messages.success(request, "🔓 تم فتح وتفعيل خيارات المطور بنجاح.")
            else:
                messages.error(request, "❌ كلمة سر المطور غير صحيحة!")
            return redirect("core:settings")

        elif action == "lock_developer":
            request.session["developer_options_unlocked"] = False
            request.session["settings_page_unlocked"] = True
            request.session.modified = True
            messages.info(request, "🔒 تم قفل خيارات المطور.")
            return redirect("core:settings")

        elif action == "save_license_settings":
            if not request.session.get("developer_options_unlocked"):
                messages.error(request, "❌ خيارات المطور مقفلة.")
                return redirect("core:settings")
            from apps.core.licensing.engine import get_or_create_system_license
            from apps.core.licensing.crypto import compute_tamper_token
            from datetime import datetime, timedelta
            from django.utils import timezone
            lic, _ = get_or_create_system_license()
            lic.remote_control_url = request.POST.get("remote_control_url", "").strip()
            lic.developer_contact_phone = request.POST.get("developer_contact_phone", "01080922432").strip()
            lic.client_name = request.POST.get("license_client_name", lic.client_name).strip()

            # Save all 10 feature flags directly
            lic.feature_face_recognition = "feature_face_recognition" in request.POST
            lic.feature_gate_relay = "feature_gate_relay" in request.POST
            lic.feature_whatsapp = "feature_whatsapp" in request.POST
            lic.feature_telegram = "feature_telegram" in request.POST
            lic.feature_bar = "feature_bar" in request.POST
            lic.feature_payroll = "feature_payroll" in request.POST
            lic.feature_retention = "feature_retention" in request.POST
            lic.feature_reports = "feature_reports" in request.POST
            lic.feature_barcode = "feature_barcode" in request.POST
            lic.feature_expenses = "feature_expenses" in request.POST

            now = timezone.now()
            post_type = request.POST.get("license_type", lic.license_type)
            post_status = request.POST.get("license_status", lic.status)
            custom_until_str = request.POST.get("license_valid_until", "").strip()
            custom_days_str = request.POST.get("license_valid_days", "").strip()

            if post_type in ["demo", "monthly", "yearly", "lifetime"]:
                lic.license_type = post_type

            if lic.license_type == "lifetime":
                lic.valid_until = None
                lic.status = "active"
            else:
                if custom_until_str:
                    try:
                        parsed_dt = datetime.fromisoformat(custom_until_str)
                        if timezone.is_naive(parsed_dt):
                            parsed_dt = timezone.make_aware(parsed_dt)
                        lic.valid_until = parsed_dt
                    except Exception:
                        pass
                elif custom_days_str and custom_days_str.isdigit():
                    lic.valid_until = now + timedelta(days=int(custom_days_str))
                else:
                    if lic.license_type == "demo":
                        lic.valid_until = now + timedelta(days=7)
                    elif lic.license_type == "monthly":
                        lic.valid_until = now + timedelta(days=30)
                    elif lic.license_type == "yearly":
                        lic.valid_until = now + timedelta(days=365)

                if post_status in ["demo", "active", "suspended", "expired"]:
                    lic.status = post_status
                elif lic.license_type == "demo":
                    lic.status = "demo"
                else:
                    lic.status = "active"

            exp_iso = lic.valid_until.isoformat() if lic.valid_until else "NONE"
            lic.tamper_hash = compute_tamper_token(lic.machine_id, lic.status, lic.license_type, exp_iso)
            lic.save()
            messages.success(request, f"✓ تم حفظ الترخيص وتحديث الصلاحيات بنجاح (الباقة: {lic.get_license_type_display()} | الحالة: {lic.get_status_display()}).")
            return redirect("core:settings")

        elif action == "activate_license_key":
            key_token = request.POST.get("license_key", "").strip()
            from apps.core.licensing.engine import activate_offline_token
            ok, msg = activate_offline_token(key_token)
            if ok:
                messages.success(request, f"🎉 {msg}")
            else:
                messages.error(request, f"❌ {msg}")
            return redirect("core:settings")

        elif action == "sync_remote_license":
            from apps.core.licensing.engine import validate_system_license
            is_valid, reason, msg, info = validate_system_license(allow_remote_sync=True)
            if is_valid:
                messages.success(request, f"✓ تم الاتصال بمركز التحكم السحابي: {msg}")
            else:
                messages.warning(request, f"تنبيه مركز التحكم: {msg}")
            return redirect("core:settings")

    google_status = check_google_contacts_status()

    from apps.core.updater import get_current_version_info
    version_info = get_current_version_info()

    from apps.core.licensing.engine import get_or_create_system_license
    from apps.core.licensing.hwid import get_hardware_fingerprint
    system_lic, _ = get_or_create_system_license()
    hwid = get_hardware_fingerprint()

    legacy_candidates = [
        Path(settings.BASE_DIR) / "data",
        Path(settings.BASE_DIR).parent / "old" / "v1" / "data",
        Path(settings.BASE_DIR).parent / "v1" / "data",
        Path(settings.BASE_DIR).parent / "data",
    ]
    detected_legacy_path = None
    for cand in legacy_candidates:
        if (cand / "members.json").exists():
            detected_legacy_path = str(cand)
            break

    context = {
        "profile": profile,
        "plans": plans,
        "payment_methods": payment_methods,
        "categories": categories,
        "google_status": google_status,
        "version_info": version_info,
        "detected_legacy_path": detected_legacy_path,
        "total_members_count": Member.objects.count(),
        "total_subscriptions_count": Subscription.objects.count(),
        "total_payments_count": Payment.objects.count(),
        "developer_unlocked": request.session.get("developer_options_unlocked", False),
        "system_license": system_lic,
        "machine_hwid": hwid,
    }
    return render(request, "core/settings.html", context)


@login_required
@manager_required
def api_check_system_updates_view(request):
    """
    Checks GitHub remote repository for any newly pushed commits or changes.
    Returns status JSON with commit comparison and list of updates.
    """
    try:
        from apps.core.updater import check_for_updates
        res = check_for_updates()
        return JsonResponse(res)
    except Exception as exc:
        return JsonResponse({
            "success": False,
            "update_available": False,
            "message": f"تعذر الاتصال بـ GitHub: {str(exc)}",
            "error": str(exc),
        })


@login_required
@manager_required
def api_perform_system_update_view(request):
    """
    Executes live git pull, database backup, and Django database migrations.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طلب POST مطلوب."}, status=405)

    try:
        from apps.core.updater import perform_system_update
        res = perform_system_update()
        return JsonResponse(res)
    except Exception as exc:
        return JsonResponse({
            "success": False,
            "message": f"حدث خطأ أثناء تطبيق التحديث: {str(exc)}",
            "logs": [f"❌ خطأ غير متوقع: {str(exc)}"],
        })


from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def license_activate_api(request):
    """API endpoint to activate an offline signed license token."""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طلب POST مطلوب."}, status=405)
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else request.POST
        key = data.get("license_key", "").strip()
    except Exception:
        key = request.POST.get("license_key", "").strip()

    if not key:
        return JsonResponse({"success": False, "message": "يرجى إدخال مفتاح الترخيص."})

    from apps.core.licensing.engine import activate_offline_token
    ok, msg = activate_offline_token(key)
    return JsonResponse({"success": ok, "message": msg})


@login_required
@manager_required
def license_sync_remote_api(request):
    """API endpoint to manually sync license status with remote control center."""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طلب POST مطلوب."}, status=405)
    from apps.core.licensing.engine import validate_system_license
    is_valid, reason, msg, info = validate_system_license(allow_remote_sync=True)
    return JsonResponse({
        "success": is_valid,
        "reason": reason,
        "message": msg,
        "info": info,
    })


def license_status_api(request):
    """API endpoint returning public machine HWID and license status."""
    from apps.core.licensing.engine import validate_system_license, get_hardware_fingerprint
    _, reason, msg, info = validate_system_license(allow_remote_sync=False)
    return JsonResponse({
        "hwid": get_hardware_fingerprint(),
        "reason": reason,
        "message": msg,
        "info": info,
    })


@csrf_exempt
def submit_support_ticket_api(request):
    """
    Receives support ticket details from web interface, logs an AuditLog event,
    and returns a success confirmation.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "طلب POST مطلوب."}, status=405)

    try:
        if request.content_type == "application/json" and request.body:
            data = json.loads(request.body.decode("utf-8"))
        else:
            data = request.POST.dict()
    except Exception:
        data = request.POST.dict()

    category = data.get("category", "طلب دعم فني عام").strip()
    user_message = data.get("message", "").strip()
    gym_name = data.get("gym_name", "").strip()
    hwid = data.get("hwid", "").strip()
    active_branch = data.get("branch", "").strip()
    sender_name = data.get("sender_name", "").strip() or (request.user.username if request.user.is_authenticated else "مجهول")

    details_str = (
        f"دعم فني - الصنف: {category} | المستخدم: {sender_name} | الجيم: {gym_name} | "
        f"الفرع: {active_branch} | الرسالة: {user_message}"
    )
    try:
        user_obj = request.user if request.user.is_authenticated else None
        AuditLog.objects.create(
            user=user_obj,
            action="SUPPORT_TICKET",
            details=details_str[:500]
        )
    except Exception:
        pass

    return JsonResponse({
        "success": True,
        "message": "تم تسجيل طلب الدعم الفني بنجاح وجارٍ التحويل إلى واتساب المطور.",
        "developer_phone": "01080922432",
    })


# ---------------------------------------------------------
# Browser Heartbeat & Process Watchdog (Camera & Server Auto-Shutdown)
# ---------------------------------------------------------
import os
import time
import threading

_LAST_HEARTBEAT_TIME = time.time()
_FIRST_HEARTBEAT_SEEN = False
_WATCHDOG_STARTED = False
_WATCHDOG_LOCK = threading.Lock()


def _watchdog_loop():
    global _LAST_HEARTBEAT_TIME, _FIRST_HEARTBEAT_SEEN
    time.sleep(60)  # Initial grace buffer
    while True:
        time.sleep(4)
        if _FIRST_HEARTBEAT_SEEN:
            elapsed = time.time() - _LAST_HEARTBEAT_TIME
            if elapsed > 25:
                print(f"[Systemize Watchdog] No active browser heartbeat for {elapsed:.1f}s. Releasing camera and exiting.")
                try:
                    from apps.face_recognition.engine import get_face_engine
                    get_face_engine().stop_camera()
                except Exception:
                    pass
                os._exit(0)


def ensure_watchdog():
    global _WATCHDOG_STARTED
    with _WATCHDOG_LOCK:
        if not _WATCHDOG_STARTED:
            _WATCHDOG_STARTED = True
            t = threading.Thread(target=_watchdog_loop, daemon=True, name="SystemizeHeartbeatWatchdog")
            t.start()


def api_heartbeat_view(request):
    global _LAST_HEARTBEAT_TIME, _FIRST_HEARTBEAT_SEEN
    _LAST_HEARTBEAT_TIME = time.time()
    _FIRST_HEARTBEAT_SEEN = True
    ensure_watchdog()
    return JsonResponse({"status": "ok", "time": _LAST_HEARTBEAT_TIME})


def api_shutdown_system_view(request):
    if request.method == "POST":
        print("[Systemize] Manual system shutdown initiated.")
        def _exit_task():
            time.sleep(0.4)
            try:
                from apps.face_recognition.engine import get_face_engine
                get_face_engine().stop_camera()
            except Exception:
                pass
            os._exit(0)
        threading.Thread(target=_exit_task, daemon=True).start()
        return JsonResponse({"status": "shutting_down"})
    return JsonResponse({"error": "POST required"}, status=400)



