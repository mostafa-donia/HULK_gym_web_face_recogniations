from decimal import Decimal
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.http import JsonResponse

from apps.expenses.models import Expense, ExpenseCategory


@login_required
def expense_list_view(request):
    from apps.core.branch_context import filter_by_branch, get_active_branch

    category_id = request.GET.get("category", "").strip()
    period = request.GET.get("period", "").strip()
    start_date = request.GET.get("start_date", "").strip()
    end_date = request.GET.get("end_date", "").strip()
    search_q = request.GET.get("q", "").strip()

    today = timezone.localdate()

    # Time period filter
    if not period and not start_date and not end_date:
        period = "this_month"

    if period == "today":
        start_date = today.strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif period == "yesterday":
        yesterday = today - timedelta(days=1)
        start_date = yesterday.strftime("%Y-%m-%d")
        end_date = yesterday.strftime("%Y-%m-%d")
    elif period == "this_week":
        week_start = today - timedelta(days=today.weekday())
        start_date = week_start.strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif period == "this_month":
        month_start = today.replace(day=1)
        start_date = month_start.strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif period == "last_month":
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        start_date = first_day_last_month.strftime("%Y-%m-%d")
        end_date = last_day_last_month.strftime("%Y-%m-%d")
    elif period == "all":
        start_date = ""
        end_date = ""

    expenses_qs = Expense.objects.select_related("category", "created_by").all().order_by("-expense_date", "-created_at")
    expenses_qs = filter_by_branch(expenses_qs, request)

    if category_id:
        expenses_qs = expenses_qs.filter(category_id=category_id)
    if start_date:
        expenses_qs = expenses_qs.filter(expense_date__gte=start_date)
    if end_date:
        expenses_qs = expenses_qs.filter(expense_date__lte=end_date)
    if search_q:
        expenses_qs = expenses_qs.filter(
            Q(description__icontains=search_q) |
            Q(category__name__icontains=search_q) |
            Q(created_by__username__icontains=search_q) |
            Q(created_by__first_name__icontains=search_q)
        )

    # Segmented KPI totals
    total_amount = expenses_qs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    total_count = expenses_qs.count()

    bar_expenses_total = expenses_qs.filter(
        Q(category__name__icontains="بار") | Q(description__icontains="بار")
    ).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    salaries_expenses_total = expenses_qs.filter(
        Q(category__name__icontains="رواتب") | Q(category__name__icontains="أجور") | Q(description__icontains="راتب") | Q(description__icontains="عمولة")
    ).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    rent_utilities_total = expenses_qs.filter(
        Q(category__name__icontains="إيجار") | Q(category__name__icontains="كهرباء") | Q(category__name__icontains="مياه") | Q(category__name__icontains="فواتير") | Q(category__name__icontains="انترنت")
    ).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    maintenance_total = expenses_qs.filter(
        Q(category__name__icontains="صيانة") | Q(category__name__icontains="معدات") | Q(category__name__icontains="نظافة") | Q(category__name__icontains="تعقيم")
    ).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    other_expenses_total = total_amount - (bar_expenses_total + salaries_expenses_total + rent_utilities_total + maintenance_total)
    if other_expenses_total < Decimal("0.00"):
        other_expenses_total = Decimal("0.00")

    categories = ExpenseCategory.objects.filter(is_active=True).order_by("name")

    paginator = Paginator(expenses_qs, 40)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "expenses": page_obj,
        "page_obj": page_obj,
        "categories": categories,
        "total_amount": total_amount,
        "total_count": total_count,
        "bar_expenses_total": bar_expenses_total,
        "salaries_expenses_total": salaries_expenses_total,
        "rent_utilities_total": rent_utilities_total,
        "maintenance_total": maintenance_total,
        "other_expenses_total": other_expenses_total,
        "selected_category": category_id,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "search_q": search_q,
        "today": today,
    }
    return render(request, "expenses/expense_list.html", context)


@login_required
def expense_create_view(request):
    from apps.core.branch_context import get_active_branch

    categories = ExpenseCategory.objects.filter(is_active=True).order_by("name")
    today = timezone.localdate()

    if request.method == "POST":
        category_id = request.POST.get("category_id")
        category = get_object_or_404(ExpenseCategory, id=category_id)
        amount = Decimal(request.POST.get("amount", "0.00") or "0.00")
        description = request.POST.get("description", "").strip()
        expense_date_str = request.POST.get("expense_date")
        expense_date = today
        if expense_date_str:
            try:
                expense_date = timezone.datetime.strptime(expense_date_str, "%Y-%m-%d").date()
            except Exception:
                pass

        if amount <= 0:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": "مبلغ المصروف يجب أن يكون أكبر من الصفر."})
            messages.error(request, "مبلغ المصروف يجب أن يكون أكبر من الصفر.")
            return render(request, "expenses/expense_form.html", {"categories": categories, "today": today})

        target_branch = None
        if not getattr(request.user, "is_owner", False):
            target_branch = getattr(request.user, "branch", None)
        else:
            target_branch = get_active_branch(request)

        expense = Expense.objects.create(
            category=category,
            amount=amount,
            description=description,
            expense_date=expense_date,
            created_by=request.user,
            branch=target_branch,
        )
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "message": f"تم تسجيل مصروف {category.name} بمبلغ {amount} ج.م بنجاح."})

        messages.success(request, f"تم تسجيل مصروف {category.name} بمبلغ {amount} ج.م بنجاح.")
        return redirect("expenses:expense_list")

    return render(request, "expenses/expense_form.html", {"categories": categories, "today": today})


@login_required
def expense_delete_view(request, expense_id):
    """Allows deleting an erroneous expense with safety check."""
    if request.method != "POST":
        return redirect("expenses:expense_list")

    expense = get_object_or_404(Expense, id=expense_id)
    exp_name = f"{expense.category.name} ({expense.amount} ج.م)"
    expense.delete()
    messages.success(request, f"تم حذف سند المصروف '{exp_name}' بنجاح.")
    return redirect(request.META.get("HTTP_REFERER", "expenses:expense_list"))

