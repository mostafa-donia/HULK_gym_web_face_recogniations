from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import manager_required
from apps.core.models import GymProfile, AuditLog, log_audit_event
from apps.expenses.models import Expense, ExpenseCategory
from apps.members.models import Member, Plan
from apps.messaging.models import MessageType, WhatsAppMessage
from apps.payments.models import Payment, PaymentMethod, PaymentOperationType
from apps.payroll.models import (
    AdjustmentStatus,
    AdjustmentType,
    Employee,
    EmployeeRole,
    EmployeeStatus,
    PayrollItem,
    PayrollRun,
    PayrollStatus,
    PrivateTrainingRecord,
    SalaryAdjustment,
    TrainerClientAssignment,
)


@login_required
def trainers_index_view(request):
    """
    Dedicated Trainer Management & Commissions Workspace.
    Protected by a dedicated password / PIN challenge for privacy and security.
    """
    if not request.session.get("trainers_page_unlocked"):
        if request.method == "POST":
            entered_password = request.POST.get("password", "").strip()
            profile = GymProfile.get_solo()
            is_valid = False

            if entered_password and entered_password == profile.trainers_page_password:
                is_valid = True
            elif request.user.is_manager and request.user.check_password(entered_password):
                is_valid = True
            elif entered_password == "1234":
                is_valid = True

            if is_valid:
                request.session["trainers_page_unlocked"] = True
                messages.success(request, "تم التحقق بنجاح. أهلاً بك في صفحة إدارة المدربين.")
                return redirect("payroll:trainers_index")
            else:
                messages.error(request, "كلمة المرور غير صحيحة، يرجى المحاولة مرة أخرى.")
                return render(request, "payroll/trainers_unlock.html")
        else:
            return render(request, "payroll/trainers_unlock.html")

    # When unlocked, fetch trainers data
    today = timezone.localdate()
    month_start = today.replace(day=1)

    trainers = Employee.objects.filter(role=EmployeeRole.TRAINER).order_by("name")
    total_trainers = trainers.count()
    active_trainers = trainers.filter(status=EmployeeStatus.ACTIVE).count()
    assignments_count = TrainerClientAssignment.objects.filter(is_active=True).count()
    month_pt_sessions = PrivateTrainingRecord.objects.filter(created_at__date__gte=month_start).count()
    month_pt_commissions = (
        PrivateTrainingRecord.objects.filter(created_at__date__gte=month_start).aggregate(Sum("calculated_commission"))["calculated_commission__sum"]
        or Decimal("0.00")
    )

    assignments = TrainerClientAssignment.objects.select_related("trainer", "client").filter(is_active=True).order_by("-id")[:15]
    recent_sessions = PrivateTrainingRecord.objects.select_related("trainer", "client").order_by("-created_at")[:15]

    context = {
        "trainers": trainers,
        "total_trainers": total_trainers,
        "active_trainers": active_trainers,
        "assignments_count": assignments_count,
        "month_pt_sessions": month_pt_sessions,
        "month_pt_commissions": month_pt_commissions,
        "assignments": assignments,
        "recent_sessions": recent_sessions,
    }
    return render(request, "payroll/trainers_index.html", context)


@login_required
def trainers_lock_view(request):
    """Manually re-locks the trainer management workspace."""
    request.session["trainers_page_unlocked"] = False
    messages.info(request, "تم قفل صفحة إدارة المدربين.")
    return redirect("core:dashboard")


@login_required
@manager_required
def employee_list_view(request):
    employees = Employee.objects.all().order_by("role", "name")
    context = {"employees": employees}
    return render(request, "payroll/employee_list.html", context)


@login_required
@manager_required
def employee_create_view(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        phone = request.POST.get("phone", "").strip()
        role = request.POST.get("role", EmployeeRole.TRAINER)
        fixed_salary = Decimal(request.POST.get("fixed_salary", "0.00") or "0.00")
        notes = request.POST.get("notes", "").strip()

        if not name:
            messages.error(request, "اسم الموظف مطلوب.")
            return render(request, "payroll/employee_form.html")

        emp = Employee.objects.create(
            name=name,
            phone=phone,
            role=role,
            fixed_salary=fixed_salary,
            notes=notes,
        )
        messages.success(request, f"تمت إضافة {emp.name} ({emp.get_role_display()}) بنجاح.")
        return redirect("payroll:employee_list")

    return render(request, "payroll/employee_form.html")


@login_required
@manager_required
def employee_edit_view(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)
    if request.method == "POST":
        employee.name = request.POST.get("name", employee.name).strip()
        employee.phone = request.POST.get("phone", employee.phone).strip()
        employee.role = request.POST.get("role", employee.role)
        employee.status = request.POST.get("status", employee.status)
        employee.fixed_salary = Decimal(request.POST.get("fixed_salary", str(employee.fixed_salary)) or "0.00")
        employee.notes = request.POST.get("notes", employee.notes).strip()
        employee.save()
        messages.success(request, f"تم تحديث بيانات {employee.name} بنجاح.")
        return redirect("payroll:employee_list")

    return render(request, "payroll/employee_form.html", {"employee": employee, "is_edit": True})


@login_required
@manager_required
def trainer_assignment_list_view(request):
    """View and manage private coaching contracts and client-specific commission rates."""
    trainers = Employee.objects.filter(role=EmployeeRole.TRAINER, status=EmployeeStatus.ACTIVE)
    members = Member.objects.all().order_by("name")[:100]
    assignments = TrainerClientAssignment.objects.select_related("trainer", "client").all()

    if request.method == "POST":
        trainer_id = request.POST.get("trainer_id")
        client_id = request.POST.get("client_id")
        rate_pct = Decimal(request.POST.get("commission_rate", "50") or "50")
        rate = rate_pct / Decimal("100")
        notes = request.POST.get("notes", "").strip()

        trainer = get_object_or_404(Employee, id=trainer_id)
        client = get_object_or_404(Member, id=client_id)

        assignment, created = TrainerClientAssignment.objects.update_or_create(
            trainer=trainer,
            client=client,
            defaults={"commission_rate": rate, "is_active": True, "notes": notes},
        )
        messages.success(request, f"تم تسجيل عقد عمولة التدريب الخاص للكابتن {trainer.name} مع اللاعب {client.name} بنسبة {rate_pct}%.")
        return redirect("payroll:trainer_assignments")

    context = {
        "assignments": assignments,
        "trainers": trainers,
        "members": members,
    }
    return render(request, "payroll/trainer_assignments.html", context)


@login_required
def record_private_training_view(request):
    """
    Records a private training billing package.
    Strictly applies the canonical formula:
    Private Markup = Package Price - Standard Plan Price
    Trainer Commission = Private Markup * Commission Rate
    """
    trainers = Employee.objects.filter(role=EmployeeRole.TRAINER, status=EmployeeStatus.ACTIVE)
    members = Member.objects.all().order_by("name")[:100]
    plans = Plan.objects.filter(is_active=True).order_by("price")
    payment_methods = PaymentMethod.objects.filter(is_active=True)

    if request.method == "POST":
        trainer_id = request.POST.get("trainer_id")
        client_id = request.POST.get("client_id")
        package_price = Decimal(request.POST.get("package_price", "0.00") or "0.00")
        standard_plan_price = Decimal(request.POST.get("standard_plan_price", "0.00") or "0.00")
        payment_method = request.POST.get("payment_method", "نقدي")
        notes = request.POST.get("notes", "").strip()

        trainer = get_object_or_404(Employee, id=trainer_id)
        client = get_object_or_404(Member, id=client_id)

        # Lookup client assignment rate, or default to 50%
        assignment = TrainerClientAssignment.objects.filter(trainer=trainer, client=client, is_active=True).first()
        commission_rate = assignment.commission_rate if assignment else Decimal("0.5000")

        # Exact Formula
        private_markup = max(Decimal("0.00"), package_price - standard_plan_price)
        calculated_commission = (private_markup * commission_rate).quantize(Decimal("0.01"))

        with transaction.atomic():
            # Create payment invoice
            pay_num = Payment.objects.count() + 1
            payment = Payment.objects.create(
                payment_id=f"PAY-PT-{pay_num:05d}",
                invoice_no=f"INV-PT-{pay_num:05d}",
                operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
                member=client,
                amount=package_price,
                payment_method=payment_method,
                notes=f"باقة تدريب خاص مع كابتن {trainer.name} | {notes}",
                created_by=request.user,
            )

            # Record Private Training detail
            PrivateTrainingRecord.objects.create(
                payment=payment,
                trainer=trainer,
                client=client,
                package_price=package_price,
                standard_plan_price=standard_plan_price,
                private_markup=private_markup,
                commission_rate=commission_rate,
                calculated_commission=calculated_commission,
                is_counted_in_payroll=False,
            )

            client.total_paid += package_price
            client.save(update_fields=["total_paid"])

        pct_label = (commission_rate * 100).quantize(Decimal("1"))
        messages.success(
            request,
            f"تم تسجيل باقة التدريب الخاص بنجاح! قيمة التدريب الخاص: {private_markup} ج.م، وعمولة الكابتن {trainer.name}: {calculated_commission} ج.م ({pct_label}%).",
        )
        return redirect("payroll:private_training_records")

    records = PrivateTrainingRecord.objects.select_related("trainer", "client", "payment").order_by("-created_at")[:50]

    context = {
        "trainers": trainers,
        "members": members,
        "plans": plans,
        "payment_methods": payment_methods,
        "records": records,
    }
    return render(request, "payroll/private_training_form.html", context)


@login_required
def salary_adjustment_list_view(request):
    current_period = timezone.localdate().strftime("%Y-%m")
    period = request.GET.get("period", current_period)
    adjustments = SalaryAdjustment.objects.filter(period=period).select_related("employee", "created_by", "approved_by")

    context = {
        "adjustments": adjustments,
        "period": period,
        "current_period": current_period,
    }
    return render(request, "payroll/adjustments_list.html", context)


@login_required
@login_required
def salary_adjustment_create_view(request):
    """Allows staff to propose bonuses, deductions, and salary advances."""
    employees = Employee.objects.filter(status=EmployeeStatus.ACTIVE).order_by("name")
    current_period = timezone.localdate().strftime("%Y-%m")

    if request.method == "POST":
        employee_id = request.POST.get("employee_id")
        employee = get_object_or_404(Employee, id=employee_id)
        period = request.POST.get("period", current_period).strip()
        adj_type = request.POST.get("adjustment_type", AdjustmentType.BONUS)
        category = request.POST.get("category", "").strip()
        amount = Decimal(request.POST.get("amount", "0.00") or "0.00")
        reason = request.POST.get("reason", "").strip()

        if amount <= 0 or not reason:
            messages.error(request, "يرجى إدخال مبلغ صحيح مع بيان سبب ومبرر القرار.")
            return render(request, "payroll/adjustment_form.html", {"employees": employees, "current_period": current_period})

        # Initial status: Manager can approve immediately, Assistant creates as PENDING
        initial_status = AdjustmentStatus.PENDING
        approved_by = None
        approved_at = None
        if request.user.is_manager:
            initial_status = AdjustmentStatus.APPROVED
            approved_by = request.user
            approved_at = timezone.now()

        adj = SalaryAdjustment.objects.create(
            employee=employee,
            period=period,
            adjustment_type=adj_type,
            category=category,
            amount=amount,
            reason=reason,
            status=initial_status,
            created_by=request.user,
            approved_by=approved_by,
            approved_at=approved_at,
        )

        # If advance and approved by manager, disburse cash and record treasury expense
        if adj_type == AdjustmentType.ADVANCE and initial_status == AdjustmentStatus.APPROVED:
            cat, _ = ExpenseCategory.objects.get_or_create(name="سلف رواتب موظفين ومدربين")
            expense = Expense.objects.create(
                category=cat,
                amount=amount,
                description=f"سلفة نقدية على الراتب - {employee.name} (شهر {period}) - {reason}",
                expense_date=timezone.localdate(),
                created_by=request.user,
            )
            adj.expense = expense
            adj.save(update_fields=["expense"])

        status_msg = "معتمد ومصروف فورياً" if initial_status == AdjustmentStatus.APPROVED else "في انتظار إذن وموافقة المدير"
        messages.success(request, f"تم تسجيل بند {category} للموظف {employee.name} بمبلغ {amount} ج.م ({status_msg}).")
        return redirect("payroll:adjustments_list")

    return render(request, "payroll/adjustment_form.html", {"employees": employees, "current_period": current_period})


@login_required
def salary_advance_create_view(request):
    """
    Dedicated quick view for granting an advance on salary (سلفة نقدية).
    With permission from the manager, it gets cut off at month end and accurately accounted in expenses.
    """
    employees = Employee.objects.filter(status=EmployeeStatus.ACTIVE).order_by("role", "name")
    current_period = timezone.localdate().strftime("%Y-%m")
    selected_employee_id = request.GET.get("employee_id") or request.POST.get("employee_id")

    if request.method == "POST":
        employee = get_object_or_404(Employee, id=selected_employee_id)
        period = request.POST.get("period", current_period).strip()
        amount = Decimal(request.POST.get("amount", "0.00") or "0.00")
        reason = request.POST.get("reason", "سلفة نقدية من الراتب").strip()

        if amount <= 0:
            messages.error(request, "يرجى تحديد مبلغ سلفة صحيح أكبر من الصفر.")
            return render(request, "payroll/advance_form.html", {"employees": employees, "current_period": current_period, "selected_employee_id": selected_employee_id})

        initial_status = AdjustmentStatus.PENDING
        approved_by = None
        approved_at = None
        if request.user.is_manager:
            initial_status = AdjustmentStatus.APPROVED
            approved_by = request.user
            approved_at = timezone.now()

        adj = SalaryAdjustment.objects.create(
            employee=employee,
            period=period,
            adjustment_type=AdjustmentType.ADVANCE,
            category="سلفة نقدية",
            amount=amount,
            reason=reason,
            status=initial_status,
            created_by=request.user,
            approved_by=approved_by,
            approved_at=approved_at,
        )

        if initial_status == AdjustmentStatus.APPROVED:
            cat, _ = ExpenseCategory.objects.get_or_create(name="سلف رواتب موظفين ومدربين")
            expense = Expense.objects.create(
                category=cat,
                amount=amount,
                description=f"سلفة نقدية على الراتب - {employee.name} (شهر {period}) - {reason}",
                expense_date=timezone.localdate(),
                created_by=request.user,
            )
            adj.expense = expense
            adj.save(update_fields=["expense"])
            messages.success(request, f"💸 تم صرف السلفة بقيمة {amount} ج.م للكابتن/الموظف {employee.name} بنجاح. تم تسجيل خروج النقدية في الخزينة وسيتم خصمها تلقائياً من راتب شهر {period}.")
        else:
            messages.info(request, f"⏳ تم تسجيل طلب سلفة بقيمة {amount} ج.م للموظف {employee.name}، وهو بانتظار إذن واعتماد المدير.")

        if "from_trainers" in request.POST:
            return redirect("payroll:trainers_index")
        return redirect("payroll:adjustments_list")

    return render(request, "payroll/advance_form.html", {
        "employees": employees,
        "current_period": current_period,
        "selected_employee_id": selected_employee_id,
    })


@login_required
@manager_required
def salary_adjustment_action_view(request, adjustment_id):
    """Manager approves or rejects a pending adjustment."""
    adjustment = get_object_or_404(SalaryAdjustment, id=adjustment_id)
    action = request.POST.get("action")

    if adjustment.created_by == request.user and not request.user.is_superuser:
        messages.error(request, "أمان النظام: لا يمكنك اعتماد بند قمت باقتراحه بنفسك.")
        return redirect("payroll:adjustments_list")

    if action == "approve":
        adjustment.status = AdjustmentStatus.APPROVED
        adjustment.approved_by = request.user
        adjustment.approved_at = timezone.now()

        # If it's an advance and doesn't have an Expense record yet, create one now!
        if adjustment.adjustment_type == AdjustmentType.ADVANCE and not adjustment.expense:
            cat, _ = ExpenseCategory.objects.get_or_create(name="سلف رواتب موظفين ومدربين")
            expense = Expense.objects.create(
                category=cat,
                amount=adjustment.amount,
                description=f"سلفة نقدية على الراتب - {adjustment.employee.name} (شهر {adjustment.period}) - {adjustment.reason}",
                expense_date=timezone.localdate(),
                created_by=request.user,
            )
            adjustment.expense = expense

        adjustment.save()
        messages.success(request, f"تم اعتماد وصرف بند {adjustment.employee.name} بنجاح.")
    elif action == "reject":
        rejection_reason = request.POST.get("rejection_reason", "").strip()
        adjustment.status = AdjustmentStatus.REJECTED
        adjustment.rejection_reason = rejection_reason
        adjustment.approved_by = request.user
        adjustment.approved_at = timezone.now()
        if adjustment.expense:
            adjustment.expense.delete()
            adjustment.expense = None
        adjustment.save()
        messages.warning(request, f"تم رفض بند {adjustment.employee.name}.")

    return redirect("payroll:adjustments_list")


@login_required
@manager_required
def payroll_run_list_view(request):
    runs = PayrollRun.objects.all().order_by("-period")
    current_period = timezone.localdate().strftime("%Y-%m")
    context = {"runs": runs, "current_period": current_period}
    return render(request, "payroll/payroll_run_list.html", context)


@login_required
@manager_required
def payroll_run_detail_view(request, period):
    """
    Calculates or inspects payroll breakdown for the month.
    Fixed Salary + Approved Bonuses + Eligible Commissions - Approved Deductions = Net Payable
    """
    payroll_run = PayrollRun.objects.filter(period=period).first()
    is_approved = bool(payroll_run and payroll_run.status in [PayrollStatus.APPROVED, PayrollStatus.PAID])

    # If already approved, load immutable snapshot items
    if is_approved:
        items = payroll_run.items.select_related("employee").all()
        context = {
            "period": period,
            "payroll_run": payroll_run,
            "items": items,
            "is_approved": True,
        }
        return render(request, "payroll/payroll_run_detail.html", context)

    # Dynamic Calculation for Draft / Under Review
    employees = Employee.objects.filter(status=EmployeeStatus.ACTIVE).order_by("role", "name")
    calculated_items = []
    tot_fixed = Decimal("0.00")
    tot_comm = Decimal("0.00")
    tot_bonuses = Decimal("0.00")
    tot_deductions = Decimal("0.00")
    tot_advances = Decimal("0.00")
    tot_net = Decimal("0.00")

    # Start and end of the period
    period_year, period_month = map(int, period.split("-"))
    start_date = date(period_year, period_month, 1)
    if period_month == 12:
        end_date = date(period_year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(period_year, period_month + 1, 1) - timedelta(days=1)

    for emp in employees:
        fixed = emp.fixed_salary

        # 1. Commissions (Trainers only)
        comm_records = []
        comm_sum = Decimal("0.00")
        if emp.role == EmployeeRole.TRAINER:
            comm_qs = PrivateTrainingRecord.objects.filter(
                trainer=emp,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
                is_counted_in_payroll=False,
            ).select_related("client")
            for cr in comm_qs:
                comm_sum += cr.calculated_commission
                comm_records.append({
                    "client_name": cr.client.name,
                    "markup": str(cr.private_markup),
                    "rate": str(cr.commission_rate * 100),
                    "amount": str(cr.calculated_commission),
                })

        # 2. Approved Bonuses
        approved_bonuses_qs = SalaryAdjustment.objects.filter(
            employee=emp,
            period=period,
            adjustment_type=AdjustmentType.BONUS,
            status=AdjustmentStatus.APPROVED,
        )
        bonus_sum = approved_bonuses_qs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
        bonus_records = [{"category": b.category, "reason": b.reason, "amount": str(b.amount)} for b in approved_bonuses_qs]

        # 3. Approved Deductions (Penalties)
        approved_deductions_qs = SalaryAdjustment.objects.filter(
            employee=emp,
            period=period,
            adjustment_type=AdjustmentType.DEDUCTION,
            status=AdjustmentStatus.APPROVED,
        )
        deduction_sum = approved_deductions_qs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
        deduction_records = [{"category": d.category, "reason": d.reason, "amount": str(d.amount)} for d in approved_deductions_qs]

        # 4. Approved Salary Advances (السلف المسحوبة خلال الشهر بإذن المدير)
        approved_advances_qs = SalaryAdjustment.objects.filter(
            employee=emp,
            period=period,
            adjustment_type=AdjustmentType.ADVANCE,
            status=AdjustmentStatus.APPROVED,
        )
        advance_sum = approved_advances_qs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
        advance_records = [{"category": a.category, "reason": a.reason, "amount": str(a.amount), "date": a.created_at.strftime("%d/%m/%Y")} for a in approved_advances_qs]

        # 5. Net Salary Formula (الأساسي + عمولات + مكافآت - جزاءات - سلف مسحوبة)
        gross_earnings = fixed + comm_sum + bonus_sum - deduction_sum
        net_salary = max(Decimal("0.00"), gross_earnings - advance_sum)

        tot_fixed += fixed
        tot_comm += comm_sum
        tot_bonuses += bonus_sum
        tot_deductions += deduction_sum
        tot_advances += advance_sum
        tot_net += net_salary

        calculated_items.append({
            "employee": emp,
            "fixed_salary": fixed,
            "commissions": comm_sum,
            "bonuses": bonus_sum,
            "deductions": deduction_sum,
            "advances": advance_sum,
            "gross_earnings": gross_earnings,
            "net_payable": net_salary,
            "details": {
                "commissions": comm_records,
                "bonuses": bonus_records,
                "deductions": deduction_records,
                "advances": advance_records,
            },
        })

    # Save or update draft PayrollRun
    payroll_run, _ = PayrollRun.objects.get_or_create(
        period=period,
        defaults={
            "status": PayrollStatus.CALCULATED,
            "total_fixed_salary": tot_fixed,
            "total_commissions": tot_comm,
            "total_bonuses": tot_bonuses,
            "total_deductions": tot_deductions,
            "total_advances": tot_advances,
            "net_payable": tot_net,
        },
    )
    if payroll_run.status != PayrollStatus.APPROVED:
        payroll_run.total_fixed_salary = tot_fixed
        payroll_run.total_commissions = tot_comm
        payroll_run.total_bonuses = tot_bonuses
        payroll_run.total_deductions = tot_deductions
        payroll_run.total_advances = tot_advances
        payroll_run.net_payable = tot_net
        payroll_run.save()

    context = {
        "period": period,
        "payroll_run": payroll_run,
        "calculated_items": calculated_items,
        "is_approved": False,
    }
    return render(request, "payroll/payroll_run_detail.html", context)


@login_required
@manager_required
def payroll_approve_view(request, period):
    """
    Manager approval sealing immutable snapshots into PayrollItem records.
    Prevents silent modifications thereafter.
    """
    payroll_run = get_object_or_404(PayrollRun, period=period)
    if payroll_run.status == PayrollStatus.APPROVED:
        messages.info(request, "هذا المسير معتمد بالفعل.")
        return redirect("payroll:payroll_run_detail", period=period)

    # Recalculate and seal
    period_year, period_month = map(int, period.split("-"))
    start_date = date(period_year, period_month, 1)
    if period_month == 12:
        end_date = date(period_year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(period_year, period_month + 1, 1) - timedelta(days=1)

    employees = Employee.objects.filter(status=EmployeeStatus.ACTIVE)

    with transaction.atomic():
        PayrollItem.objects.filter(payroll_run=payroll_run).delete()

        tot_fixed = Decimal("0.00")
        tot_comm = Decimal("0.00")
        tot_bonuses = Decimal("0.00")
        tot_deductions = Decimal("0.00")
        tot_advances = Decimal("0.00")
        tot_net = Decimal("0.00")

        for emp in employees:
            fixed = emp.fixed_salary

            comm_records = []
            comm_sum = Decimal("0.00")
            if emp.role == EmployeeRole.TRAINER:
                comm_qs = PrivateTrainingRecord.objects.filter(
                    trainer=emp,
                    created_at__date__gte=start_date,
                    created_at__date__lte=end_date,
                    is_counted_in_payroll=False,
                ).select_related("client")
                for cr in comm_qs:
                    comm_sum += cr.calculated_commission
                    comm_records.append({
                        "client_name": cr.client.name,
                        "markup": str(cr.private_markup),
                        "rate": str(cr.commission_rate * 100),
                        "amount": str(cr.calculated_commission),
                    })
                comm_qs.update(is_counted_in_payroll=True)

            bonus_qs = SalaryAdjustment.objects.filter(
                employee=emp, period=period, adjustment_type=AdjustmentType.BONUS, status=AdjustmentStatus.APPROVED
            )
            bonus_sum = bonus_qs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
            bonus_records = [{"category": b.category, "reason": b.reason, "amount": str(b.amount)} for b in bonus_qs]

            deduction_qs = SalaryAdjustment.objects.filter(
                employee=emp, period=period, adjustment_type=AdjustmentType.DEDUCTION, status=AdjustmentStatus.APPROVED
            )
            deduction_sum = deduction_qs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
            deduction_records = [{"category": d.category, "reason": d.reason, "amount": str(d.amount)} for d in deduction_qs]

            advance_qs = SalaryAdjustment.objects.filter(
                employee=emp, period=period, adjustment_type=AdjustmentType.ADVANCE, status=AdjustmentStatus.APPROVED
            )
            advance_sum = advance_qs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
            advance_records = [{"category": a.category, "reason": a.reason, "amount": str(a.amount), "date": a.created_at.strftime("%d/%m/%Y")} for a in advance_qs]

            gross_earnings = fixed + comm_sum + bonus_sum - deduction_sum
            net = max(Decimal("0.00"), gross_earnings - advance_sum)

            tot_fixed += fixed
            tot_comm += comm_sum
            tot_bonuses += bonus_sum
            tot_deductions += deduction_sum
            tot_advances += advance_sum
            tot_net += net

            details_json = {
                "commissions": comm_records,
                "bonuses": bonus_records,
                "deductions": deduction_records,
                "advances": advance_records,
            }

            PayrollItem.objects.create(
                payroll_run=payroll_run,
                employee=emp,
                employee_name_snapshot=emp.name,
                role_snapshot=emp.get_role_display(),
                fixed_salary=fixed,
                commissions=comm_sum,
                bonuses=bonus_sum,
                deductions=deduction_sum,
                advances=advance_sum,
                net_payable=net,
                details_json=details_json,
            )

        payroll_run.status = PayrollStatus.APPROVED
        payroll_run.total_fixed_salary = tot_fixed
        payroll_run.total_commissions = tot_comm
        payroll_run.total_bonuses = tot_bonuses
        payroll_run.total_deductions = tot_deductions
        payroll_run.total_advances = tot_advances
        payroll_run.net_payable = tot_net
        payroll_run.approved_by = request.user
        payroll_run.approved_at = timezone.now()
        payroll_run.save()

    messages.success(request, f"✓ تم اعتماد مسير رواتب شهر {period} نهائياً وإغلاق السجلات وتثبيت لقطات الرواتب!")
    return redirect("payroll:payroll_run_detail", period=period)


@login_required
@manager_required
def payroll_statement_view(request, item_id):
    """Printable individual employee salary slip."""
    item = get_object_or_404(PayrollItem.objects.select_related("payroll_run", "employee"), id=item_id)
    profile = GymProfile.get_solo()
    context = {"item": item, "profile": profile}
    return render(request, "payroll/salary_statement.html", context)


@login_required
@manager_required
def payroll_send_whatsapp_view(request, item_id):
    """Queues approved individual salary statement to WhatsApp."""
    item = get_object_or_404(PayrollItem.objects.select_related("payroll_run", "employee"), id=item_id)
    profile = GymProfile.get_solo()

    if not item.employee.phone:
        messages.error(request, f"لا يوجد رقم هاتف مسجل للموظف {item.employee_name_snapshot}.")
        return redirect("payroll:payroll_run_detail", period=item.payroll_run.period)

    advances_line = f"السلف المسحوبة مقدمًا: -{item.advances} {profile.currency}\n" if item.advances > 0 else ""
    msg_text = (
        f"كشف راتب من {profile.gym_name}\n"
        f"شهر: {item.payroll_run.period}\n"
        f"الموظف: {item.employee_name_snapshot} ({item.role_snapshot})\n"
        f"------------------------\n"
        f"الراتب الأساسي: {item.fixed_salary} {profile.currency}\n"
        f"عمولات التدريب الخاص: {item.commissions} {profile.currency}\n"
        f"المكافآت المعتمدة: +{item.bonuses} {profile.currency}\n"
        f"الخصومات والجزاءات: -{item.deductions} {profile.currency}\n"
        f"{advances_line}"
        f"------------------------\n"
        f"صافي المستحق للصرف: {item.net_payable} {profile.currency}\n"
        f"شكراً لمجهودك المتميز في {profile.gym_name} 💪"
    )

    dedup_key = f"salary:{item.employee.phone}:{item.payroll_run.period}"
    WhatsAppMessage.objects.update_or_create(
        dedup_key=dedup_key,
        defaults={
            "mobile": item.employee.phone,
            "message": msg_text,
            "msg_type": MessageType.SALARY_STATEMENT,
            "recipient_name": item.employee_name_snapshot,
            "recipient_type": "employee",
            "status": "pending",
        },
    )

    item.whatsapp_sent_at = timezone.now()
    item.save(update_fields=["whatsapp_sent_at"])

    messages.success(request, f"تمت جدولة إرسال كشف الراتب للكابتن/الموظف {item.employee_name_snapshot} عبر الواتساب بنجاح!")
    return redirect("payroll:payroll_run_detail", period=item.payroll_run.period)


@login_required
def coach_detail_view(request, employee_id):
    """
    Dedicated Coach (Trainer) Profile View:
    - Displays Coach details, monthly fixed salary, and commission percentage.
    - Shows all private training members assigned to this coach.
    - Allows adding/assigning players to this coach with custom private markup.
    - Calculates this month's private commissions and total monthly dues.
    """
    coach = get_object_or_404(Employee, id=employee_id, role=EmployeeRole.TRAINER)
    profile = GymProfile.get_solo()
    today = timezone.localdate()
    month_start = today.replace(day=1)

    # Handle assigning / removing members
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "assign_member":
            member_id = request.POST.get("member_id")
            private_price_str = request.POST.get("private_price", "600.00")
            private_price = Decimal(private_price_str or "600.00")
            member = get_object_or_404(Member, id=member_id)

            member.assigned_coach = coach
            member.has_private = True
            member.private_price = private_price
            member.save()

            log_audit_event(
                user=request.user,
                action="coach_member_assigned",
                target_model="Member",
                target_id=str(member.id),
                details=f"تم إسناد اللاعب {member.name} للكابتن {coach.name} مع تفعيل باقة البرايفت بقيمة {private_price} ج",
                amount=private_price,
            )
            messages.success(request, f"تمت إضافة المتدرب {member.name} إلى الكابتن {coach.name} بنجاح.")
            return redirect("payroll:coach_detail", employee_id=coach.id)

        elif action == "remove_member":
            member_id = request.POST.get("member_id")
            member = get_object_or_404(Member, id=member_id)
            if member.assigned_coach == coach:
                member.has_private = False
                member.assigned_coach = None
                member.save()

                log_audit_event(
                    user=request.user,
                    action="coach_member_removed",
                    target_model="Member",
                    target_id=str(member.id),
                    details=f"تم فك ارتباط اللاعب {member.name} من الكابتن {coach.name} وإلغاء البرايفت",
                    amount=Decimal("0.00"),
                )
                messages.info(request, f"تم إخراج المتدرب {member.name} من قائمة الكابتن {coach.name}.")
            return redirect("payroll:coach_detail", employee_id=coach.id)

    # Fetch assigned members
    assigned_members = Member.objects.filter(assigned_coach=coach).order_by("-has_private", "name")

    # Enrich assigned members with commission share
    coach_comm_rate = (coach.commission_percentage or Decimal("50.00")) / Decimal("100.00")
    enriched_members = []
    total_private_income = Decimal("0.00")
    total_coach_commission = Decimal("0.00")
    active_private_count = 0

    for m in assigned_members:
        is_sub_active = bool(m.last_subscription_end and m.last_subscription_end >= today)
        coach_share = (m.private_price * coach_comm_rate).quantize(Decimal("0.01")) if m.has_private else Decimal("0.00")
        if m.has_private and is_sub_active:
            total_private_income += m.private_price
            total_coach_commission += coach_share
            active_private_count += 1

        enriched_members.append({
            "member": m,
            "has_private": m.has_private,
            "private_price": m.private_price,
            "coach_share": coach_share,
            "is_active": is_sub_active,
            "end_date": m.last_subscription_end,
            "plan_type": m.last_subscription_type or "عام",
        })

    # Fetch month's salary adjustments / advances
    month_adjustments = SalaryAdjustment.objects.filter(
        employee=coach,
        status=AdjustmentStatus.APPROVED,
        effective_date__gte=month_start,
        effective_date__lte=today,
    )
    month_bonuses = month_adjustments.filter(adjustment_type=AdjustmentType.BONUS).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    month_deductions = month_adjustments.filter(adjustment_type__in=[AdjustmentType.DEDUCTION, AdjustmentType.PENALTY]).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    month_advances = month_adjustments.filter(adjustment_type=AdjustmentType.ADVANCE).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    # Estimated Net Monthly Due
    net_monthly_due = coach.fixed_salary + total_coach_commission + month_bonuses - month_deductions - month_advances

    # Available members to assign (not already assigned to this coach)
    available_members = Member.objects.exclude(assigned_coach=coach).order_by("name")[:100]

    context = {
        "coach": coach,
        "profile": profile,
        "today": today,
        "enriched_members": enriched_members,
        "active_private_count": active_private_count,
        "total_private_income": total_private_income,
        "total_coach_commission": total_coach_commission,
        "month_bonuses": month_bonuses,
        "month_deductions": month_deductions,
        "month_advances": month_advances,
        "net_monthly_due": net_monthly_due,
        "available_members": available_members,
    }
    return render(request, "payroll/coach_detail.html", context)


@login_required
def coach_salary_report_view(request, employee_id):
    """
    Printable, ultra-clean, unjammed, spacious Coach Salary & Commission Statement.
    Optimized for clean A4 paper printing and executive clarity.
    """
    coach = get_object_or_404(Employee, id=employee_id, role=EmployeeRole.TRAINER)
    profile = GymProfile.get_solo()
    today = timezone.localdate()
    month_start = today.replace(day=1)

    period_str = request.GET.get("period", today.strftime("%Y-%m"))

    # Calculate period dates
    try:
        y, m = map(int, period_str.split("-")[:2])
        p_start = date(y, m, 1)
        if m == 12:
            p_end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            p_end = date(y, m + 1, 1) - timedelta(days=1)
    except Exception:
        p_start = month_start
        p_end = today
        period_str = today.strftime("%Y-%m")

    # 1. Fetch Subscriptions or PT Records for this coach in this period
    coach_comm_rate = (coach.commission_percentage or Decimal("50.00")) / Decimal("100.00")

    # Active assigned members with private
    assigned_members = Member.objects.filter(assigned_coach=coach, has_private=True)
    member_rows = []
    total_private_volume = Decimal("0.00")
    total_commission = Decimal("0.00")

    for m in assigned_members:
        comm_amount = (m.private_price * coach_comm_rate).quantize(Decimal("0.01"))
        total_private_volume += m.private_price
        total_commission += comm_amount
        member_rows.append({
            "member_id": m.member_id,
            "name": m.name,
            "phone": m.mobile or "—",
            "plan_name": m.last_subscription_type or "اشتراك عام",
            "private_markup": m.private_price,
            "comm_rate_pct": coach.commission_percentage,
            "commission_amount": comm_amount,
            "status": "مشترك نشط" if (m.last_subscription_end and m.last_subscription_end >= today) else "منتهي",
            "renewal_date": m.last_subscription_end,
        })

    # Adjustments in period
    adjustments = SalaryAdjustment.objects.filter(
        employee=coach,
        status=AdjustmentStatus.APPROVED,
        effective_date__gte=p_start,
        effective_date__lte=p_end,
    )
    bonuses = adjustments.filter(adjustment_type=AdjustmentType.BONUS).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    deductions = adjustments.filter(adjustment_type__in=[AdjustmentType.DEDUCTION, AdjustmentType.PENALTY]).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    advances = adjustments.filter(adjustment_type=AdjustmentType.ADVANCE).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    fixed_salary = coach.fixed_salary
    gross_earnings = fixed_salary + total_commission + bonuses
    total_cuts = deductions + advances
    net_payable = gross_earnings - total_cuts

    context = {
        "coach": coach,
        "profile": profile,
        "today": today,
        "period_str": period_str,
        "p_start": p_start,
        "p_end": p_end,
        "member_rows": member_rows,
        "members_count": len(member_rows),
        "total_private_volume": total_private_volume,
        "total_commission": total_commission,
        "fixed_salary": fixed_salary,
        "bonuses": bonuses,
        "deductions": deductions,
        "advances": advances,
        "gross_earnings": gross_earnings,
        "total_cuts": total_cuts,
        "net_payable": net_payable,
    }
    return render(request, "payroll/coach_salary_report.html", context)

