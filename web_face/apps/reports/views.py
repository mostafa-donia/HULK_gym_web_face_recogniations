from decimal import Decimal
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.contrib.auth.decorators import login_required
from apps.accounts.decorators import manager_required
from apps.payments.models import Payment, PaymentOperationType
from apps.expenses.models import Expense
from apps.members.models import Member, Subscription, CheckInEvent
from apps.payroll.models import PayrollRun, PayrollStatus


@login_required
@manager_required
def financial_report_view(request):
    """
    Comprehensive financial and operational management report.
    Accessible exclusively to Gym Managers.
    Provides filtering by predefined presets (today, this_week, this_month, all_time)
    or custom start and end date ranges.
    """
    today = timezone.localdate()
    period = request.GET.get("period", "this_month")
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")

    if period == "today":
        start_date = today
        end_date = today
    elif period == "yesterday":
        start_date = today - timezone.timedelta(days=1)
        end_date = start_date
    elif period == "this_week":
        start_date = today - timezone.timedelta(days=today.weekday())
        end_date = today
    elif period == "this_month":
        start_date = today.replace(day=1)
        end_date = today
    elif period == "last_month":
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - timezone.timedelta(days=1)
        start_date = last_month_end.replace(day=1)
        end_date = last_month_end
    elif period == "custom" and start_date_str and end_date_str:
        try:
            start_date = timezone.datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = timezone.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            start_date = today.replace(day=1)
            end_date = today
    elif period == "all_time":
        start_date = None
        end_date = None
    else:
        start_date = today.replace(day=1)
        end_date = today
        period = "this_month"

    # Filter base querysets
    payment_qs = Payment.objects.all()
    expense_qs = Expense.objects.all()
    subscription_qs = Subscription.objects.all()
    checkin_qs = CheckInEvent.objects.all()

    if start_date and end_date:
        payment_qs = payment_qs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
        expense_qs = expense_qs.filter(expense_date__gte=start_date, expense_date__lte=end_date)
        subscription_qs = subscription_qs.filter(start_date__gte=start_date, start_date__lte=end_date)
        checkin_qs = checkin_qs.filter(checked_in_at__date__gte=start_date, checked_in_at__date__lte=end_date)
    elif start_date:
        payment_qs = payment_qs.filter(created_at__date__gte=start_date)
        expense_qs = expense_qs.filter(expense_date__gte=start_date)
        subscription_qs = subscription_qs.filter(start_date__gte=start_date)
        checkin_qs = checkin_qs.filter(checked_in_at__date__gte=start_date)

    # 1. Revenue calculations
    total_revenue = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    revenue_by_type = payment_qs.values("operation_type").annotate(
        total=Sum("amount"), count=Count("id")
    ).order_by("-total")

    # Map labels
    type_labels = dict(PaymentOperationType.choices)
    revenue_types_summary = [
        {
            "code": item["operation_type"],
            "label": type_labels.get(item["operation_type"], item["operation_type"]),
            "total": item["total"],
            "count": item["count"],
        }
        for item in revenue_by_type
    ]

    revenue_by_method = payment_qs.values("payment_method").annotate(
        total=Sum("amount"), count=Count("id")
    ).order_by("-total")

    # 2. Expenses calculations
    total_expenses = expense_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    expenses_by_cat = expense_qs.values("category__name").annotate(
        total=Sum("amount"), count=Count("id")
    ).order_by("-total")

    # 3. Payroll cost calculation (Approved payrolls in this date range)
    payroll_runs_qs = PayrollRun.objects.filter(status=PayrollStatus.APPROVED)
    if start_date and end_date:
        payroll_runs_qs = payroll_runs_qs.filter(
            Q(approved_at__date__gte=start_date, approved_at__date__lte=end_date) |
            Q(period__gte=start_date.strftime("%Y-%m"), period__lte=end_date.strftime("%Y-%m"))
        )
    total_payroll_cost = payroll_runs_qs.aggregate(total=Sum("net_payable"))["total"] or Decimal("0.00")
    advances_in_period = expense_qs.filter(category__name="سلف رواتب موظفين ومدربين").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    total_labor_cost = total_payroll_cost + advances_in_period

    # 4. Net Operating Result
    # Note: total_expenses already accounts for cash advances paid out of the treasury.
    # total_payroll_cost is the net remaining payable at month-end.
    # Therefore: net_operating_profit = total_revenue - total_expenses - total_payroll_cost
    # Exactly matches real cash flow without any double-counting.
    net_operating_profit = total_revenue - total_expenses - total_payroll_cost

    # 5. Operational statistics
    new_subscriptions_count = subscription_qs.count()
    checkins_count = checkin_qs.count()

    total_active_members = Member.objects.filter(last_subscription_end__gte=today).count()
    total_expired_members = Member.objects.filter(Q(last_subscription_end__lt=today) | Q(last_subscription_end__isnull=True)).count()
    members_with_debt = Member.objects.filter(current_remaining__gt=Decimal("0.00"))
    debt_members_count = members_with_debt.count()
    total_debt_amount = members_with_debt.aggregate(total=Sum("current_remaining"))["total"] or Decimal("0.00")

    # Detailed transaction items for the period (limit 50 for display)
    recent_payments = payment_qs.select_related("member")[:50]
    recent_expenses = expense_qs.select_related("category", "created_by")[:50]

    context = {
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "start_date_str": start_date.strftime("%Y-%m-%d") if start_date else "",
        "end_date_str": end_date.strftime("%Y-%m-%d") if end_date else "",
        "total_revenue": total_revenue,
        "revenue_types_summary": revenue_types_summary,
        "revenue_by_method": revenue_by_method,
        "total_expenses": total_expenses,
        "expenses_by_cat": expenses_by_cat,
        "total_payroll_cost": total_payroll_cost,
        "advances_in_period": advances_in_period,
        "total_labor_cost": total_labor_cost,
        "net_operating_profit": net_operating_profit,
        "new_subscriptions_count": new_subscriptions_count,
        "checkins_count": checkins_count,
        "total_active_members": total_active_members,
        "total_expired_members": total_expired_members,
        "debt_members_count": debt_members_count,
        "total_debt_amount": total_debt_amount,
        "recent_payments": recent_payments,
        "recent_expenses": recent_expenses,
        "report_generated_at": timezone.now(),
    }
    return render(request, "reports/financial_report.html", context)
