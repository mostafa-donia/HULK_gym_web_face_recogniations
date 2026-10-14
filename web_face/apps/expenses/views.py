from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.expenses.models import Expense, ExpenseCategory


@login_required
def expense_list_view(request):
    category_id = request.GET.get("category")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    expenses = Expense.objects.select_related("category", "created_by").all().order_by("-expense_date", "-created_at")

    if category_id:
        expenses = expenses.filter(category_id=category_id)
    if start_date:
        expenses = expenses.filter(expense_date__gte=start_date)
    if end_date:
        expenses = expenses.filter(expense_date__lte=end_date)

    total_amount = expenses.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    categories = ExpenseCategory.objects.filter(is_active=True)

    context = {
        "expenses": expenses[:100],
        "categories": categories,
        "total_amount": total_amount,
        "selected_category": category_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    return render(request, "expenses/expense_list.html", context)


@login_required
def expense_create_view(request):
    categories = ExpenseCategory.objects.filter(is_active=True)
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
            messages.error(request, "مبلغ المصروف يجب أن يكون أكبر من الصفر.")
            return render(request, "expenses/expense_form.html", {"categories": categories, "today": today})

        expense = Expense.objects.create(
            category=category,
            amount=amount,
            description=description,
            expense_date=expense_date,
            created_by=request.user,
        )
        messages.success(request, f"تم تسجيل مصروف {category.name} بمبلغ {amount} ج.م بنجاح.")
        return redirect("expenses:expense_list")

    return render(request, "expenses/expense_form.html", {"categories": categories, "today": today})
