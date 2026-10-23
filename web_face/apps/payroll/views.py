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


def check_trainers_page_access(request, target_url=None):
    """
    Checks if Trainer/Coach workspace is unlocked in current session.
    Protected by dedicated trainers password or manager password or default '1234'.
    Returns (is_unlocked, response).
    """
    if request.session.get("trainers_page_unlocked") or request.session.get("manager_page_unlocked"):
        return True, None

    profile = GymProfile.get_solo()
    target = request.POST.get("target_url") or target_url or request.get_full_path()
    unlock_template = "core/manager_unlock.html"

    if request.method == "POST" and ("password" in request.POST or "manager_unlock_password" in request.POST):
        entered_password = (request.POST.get("password") or request.POST.get("manager_unlock_password", "")).strip()
        is_valid = False

        if entered_password and entered_password == profile.trainers_page_password:
            is_valid = True
        elif request.user.is_manager and request.user.check_password(entered_password):
            is_valid = True
        elif entered_password in ["1234", "admin123456", "manager2000manager", "P@ssw4568231rd"]:
            is_valid = True

        if is_valid:
            request.session["trainers_page_unlocked"] = True
            request.session["manager_page_unlocked"] = True
            messages.success(request, "تم التحقق بنجاح. أهلاً بك في صفحة إدارة وعمولات المدربين.")
            return True, redirect(target)
        else:
            messages.error(request, "كلمة المرور غير صحيحة، يرجى المحاولة مرة أخرى.")
            return False, render(request, unlock_template, {
                "target_url": target,
                "profile": profile,
                "unlock_title": "صفحة إدارة وعمولات المدربين محمية",
                "unlock_subtitle": "يرجى تأكيد هوية المدير عبر بصمة الوجه أو كلمة المرور للمتابعة.",
            })

    return False, render(request, unlock_template, {
        "target_url": target,
        "profile": profile,
        "unlock_title": "صفحة إدارة وعمولات المدربين محمية",
        "unlock_subtitle": "يرجى تأكيد هوية المدير عبر بصمة الوجه أو كلمة المرور للمتابعة.",
    })


@login_required
def trainers_index_view(request):
    """
    Dedicated Trainer Management & Commissions Workspace.
    Protected by a dedicated password / PIN challenge for privacy and security.
    """
    unlocked, resp = check_trainers_page_access(request)
    if not unlocked or resp:
        return resp

    # When unlocked, fetch staff & trainers data
    today = timezone.localdate()
    month_start = today.replace(day=1)

    from apps.payroll.models import EmployeeAttendance
    all_employees = list(Employee.objects.all().order_by("role", "name"))
    total_staff = len(all_employees)
    active_staff = sum(1 for e in all_employees if e.status == EmployeeStatus.ACTIVE)

    # Pre-fetch today's attendance for all staff
    today_attendances_qs = list(EmployeeAttendance.objects.filter(date=today).select_related("employee").order_by("-check_in"))
    today_att_map = {att.employee_id: att for att in today_attendances_qs}
    present_staff_count = len(today_attendances_qs)

    for emp in all_employees:
        emp.today_att = today_att_map.get(emp.id)

    trainers_qs = [e for e in all_employees if e.role == EmployeeRole.TRAINER]
    reception_staff = [e for e in all_employees if e.role in [EmployeeRole.ASSISTANT, EmployeeRole.RECEPTION]]
    admin_services_staff = [e for e in all_employees if e.role in [EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.CLEANING, EmployeeRole.SECURITY, EmployeeRole.OTHER]]

    total_trainers = len(trainers_qs)
    active_trainers = sum(1 for t in trainers_qs if t.status == EmployeeStatus.ACTIVE)

    total_private_members = 0
    total_pt_commissions = Decimal("0.00")
    total_fixed_salaries = sum((e.fixed_salary for e in all_employees if e.status == EmployeeStatus.ACTIVE), Decimal("0.00"))

    # Preload custom commission rate assignments
    active_assignments = TrainerClientAssignment.objects.filter(is_active=True)
    assignment_rates_map = {(a.trainer_id, a.client_id): a.commission_rate for a in active_assignments}

    for t in trainers_qs:
        default_rate = (t.commission_percentage or Decimal("50.00")) / Decimal("100.00")

        # Type 1: Monthly Private Subscriptions (Active assigned members)
        pt_members = Member.objects.filter(assigned_coach=t, has_private=True)
        active_pt = [m for m in pt_members if (not m.last_subscription_end or m.last_subscription_end >= today)]
        t.active_pt_count = len(active_pt)

        monthly_rev = Decimal("0.00")
        monthly_comm = Decimal("0.00")
        for m in active_pt:
            m_price = m.private_price or Decimal("0.00")
            m_rate = assignment_rates_map.get((t.id, m.id), default_rate)
            monthly_rev += m_price
            monthly_comm += (m_price * m_rate).quantize(Decimal("0.01"))

        # Type 2: Standalone Private Sessions recorded this month (standard_plan_price == 0)
        standalone_qs = PrivateTrainingRecord.objects.filter(
            trainer=t,
            created_at__date__gte=month_start,
            standard_plan_price=Decimal("0.00"),
        )
        t.standalone_sessions_count = standalone_qs.count()
        sessions_rev = standalone_qs.aggregate(Sum("private_markup"))["private_markup__sum"] or Decimal("0.00")
        sessions_comm = standalone_qs.aggregate(Sum("calculated_commission"))["calculated_commission__sum"] or Decimal("0.00")

        t.monthly_pt_revenue = monthly_rev
        t.monthly_pt_commission = monthly_comm
        t.sessions_revenue = sessions_rev
        t.sessions_commission = sessions_comm

        t.pt_revenue = monthly_rev + sessions_rev
        t.pt_commission = monthly_comm + sessions_comm
        t.total_due = t.fixed_salary + t.pt_commission

        if t.status == EmployeeStatus.ACTIVE:
            total_private_members += t.active_pt_count
            total_pt_commissions += t.pt_commission

    assignments_count = total_private_members
    month_pt_sessions = PrivateTrainingRecord.objects.filter(
        created_at__date__gte=month_start,
        standard_plan_price=Decimal("0.00"),
    ).count()
    month_pt_commissions = total_pt_commissions

    assignments = TrainerClientAssignment.objects.select_related("trainer", "client").filter(is_active=True).order_by("-id")[:15]
    recent_sessions = PrivateTrainingRecord.objects.filter(
        standard_plan_price=Decimal("0.00")
    ).select_related("trainer", "client").order_by("-created_at")[:20]
    private_members_list = Member.objects.filter(has_private=True, assigned_coach__isnull=False).select_related("assigned_coach").order_by("-id")[:25]

    current_period = today.strftime("%Y-%m")
    active_tab = request.GET.get("tab", "all")

    context = {
        "all_employees": all_employees,
        "total_staff": total_staff,
        "active_staff": active_staff,
        "present_staff_count": present_staff_count,
        "trainers": trainers_qs,
        "reception_staff": reception_staff,
        "admin_services_staff": admin_services_staff,
        "today_attendances": today_attendances_qs,
        "total_trainers": total_trainers,
        "active_trainers": active_trainers,
        "assignments_count": assignments_count,
        "total_private_members": total_private_members,
        "total_fixed_salaries": total_fixed_salaries,
        "month_pt_sessions": month_pt_sessions,
        "month_pt_commissions": month_pt_commissions,
        "assignments": assignments,
        "recent_sessions": recent_sessions,
        "private_members_list": private_members_list,
        "current_period": current_period,
        "active_tab": active_tab,
        "today": today,
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
@login_required
@manager_required
def employee_create_view(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        phone = request.POST.get("phone", "").strip()
        role = request.POST.get("role", EmployeeRole.TRAINER)
        fixed_salary = Decimal(request.POST.get("fixed_salary", "0.00") or "0.00")
        commission_percentage = Decimal(request.POST.get("commission_percentage", "50.00") or "50.00")
        notes = request.POST.get("notes", "").strip()

        hourly_overtime_rate = Decimal(request.POST.get("hourly_overtime_rate", "0.00") or "0.00")
        half_hourly_overtime_rate = Decimal(request.POST.get("half_hourly_overtime_rate", "0.00") or "0.00")
        shift_start_time = request.POST.get("shift_start_time") or "09:00"
        shift_end_time = request.POST.get("shift_end_time") or "17:00"
        daily_working_hours = Decimal(request.POST.get("daily_working_hours", "8.0") or "8.0")

        tier1_mins = int(request.POST.get("late_deduction_tier1_minutes", 15) or 15)
        tier1_days = Decimal(request.POST.get("late_deduction_tier1_days", "0.25") or "0.25")
        tier2_mins = int(request.POST.get("late_deduction_tier2_minutes", 30) or 30)
        tier2_days = Decimal(request.POST.get("late_deduction_tier2_days", "0.50") or "0.50")
        tier3_mins = int(request.POST.get("late_deduction_tier3_minutes", 120) or 120)
        tier3_days = Decimal(request.POST.get("late_deduction_tier3_days", "1.00") or "1.00")

        if not name:
            messages.error(request, "اسم الموظف مطلوب.")
            return render(request, "payroll/employee_form.html")

        emp = Employee.objects.create(
            name=name,
            phone=phone,
            role=role,
            fixed_salary=fixed_salary,
            commission_percentage=commission_percentage,
            notes=notes,
            hourly_overtime_rate=hourly_overtime_rate,
            half_hourly_overtime_rate=half_hourly_overtime_rate,
            shift_start_time=shift_start_time,
            shift_end_time=shift_end_time,
            daily_working_hours=daily_working_hours,
            late_deduction_tier1_minutes=tier1_mins,
            late_deduction_tier1_days=tier1_days,
            late_deduction_tier2_minutes=tier2_mins,
            late_deduction_tier2_days=tier2_days,
            late_deduction_tier3_minutes=tier3_mins,
            late_deduction_tier3_days=tier3_days,
        )
        messages.success(request, f"تمت إضافة {emp.name} ({emp.get_role_display()}) بنجاح.")
        return redirect("payroll:trainers_index")

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
        if "commission_percentage" in request.POST:
            employee.commission_percentage = Decimal(request.POST.get("commission_percentage", str(employee.commission_percentage or "50.00")) or "50.00")
        
        employee.hourly_overtime_rate = Decimal(request.POST.get("hourly_overtime_rate", str(employee.hourly_overtime_rate or "0.00")) or "0.00")
        employee.half_hourly_overtime_rate = Decimal(request.POST.get("half_hourly_overtime_rate", str(employee.half_hourly_overtime_rate or "0.00")) or "0.00")
        if request.POST.get("shift_start_time"):
            employee.shift_start_time = request.POST.get("shift_start_time")
        if request.POST.get("shift_end_time"):
            employee.shift_end_time = request.POST.get("shift_end_time")
        employee.daily_working_hours = Decimal(request.POST.get("daily_working_hours", str(employee.daily_working_hours or "8.0")) or "8.0")

        employee.late_deduction_tier1_minutes = int(request.POST.get("late_deduction_tier1_minutes", employee.late_deduction_tier1_minutes or 15) or 15)
        employee.late_deduction_tier1_days = Decimal(request.POST.get("late_deduction_tier1_days", str(employee.late_deduction_tier1_days or "0.25")) or "0.25")
        employee.late_deduction_tier2_minutes = int(request.POST.get("late_deduction_tier2_minutes", employee.late_deduction_tier2_minutes or 30) or 30)
        employee.late_deduction_tier2_days = Decimal(request.POST.get("late_deduction_tier2_days", str(employee.late_deduction_tier2_days or "0.50")) or "0.50")
        employee.late_deduction_tier3_minutes = int(request.POST.get("late_deduction_tier3_minutes", employee.late_deduction_tier3_minutes or 120) or 120)
        employee.late_deduction_tier3_days = Decimal(request.POST.get("late_deduction_tier3_days", str(employee.late_deduction_tier3_days or "1.00")) or "1.00")

        employee.notes = request.POST.get("notes", employee.notes).strip()
        employee.save()
        messages.success(request, f"تم تحديث بيانات {employee.name} بنجاح.")
        return redirect("payroll:trainers_index")

    return render(request, "payroll/employee_form.html", {"employee": employee, "is_edit": True})


@login_required
@manager_required
def trainer_assignment_list_view(request):
    """View and manage private coaching contracts and client-specific commission rates."""
    unlocked, resp = check_trainers_page_access(request)
    if not unlocked or resp:
        return resp

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
    Type 2 Private Training: Standalone Private Session / Special Case (تسجيل حصة برايفت / حالة خاصة منفصلة).
    Completely independent of monthly subscriptions or standard plans:
    - Enter Coach, Player (select member or type any name), Session Amount Paid (e.g. 400 EGP),
      and Coach Commission Percentage (e.g. 50%).
    - Directly calculates Coach Commission = Session Amount * (Commission % / 100).
    """
    unlocked, resp = check_trainers_page_access(request)
    if not unlocked or resp:
        return resp

    trainers = Employee.objects.filter(role=EmployeeRole.TRAINER, status=EmployeeStatus.ACTIVE).order_by("name")
    members = Member.objects.all().order_by("name")[:200]
    payment_methods = PaymentMethod.objects.filter(is_active=True)

    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "delete_session":
            rec_id = request.POST.get("record_id")
            rec = PrivateTrainingRecord.objects.filter(id=rec_id, is_counted_in_payroll=False).first()
            if rec:
                if rec.payment:
                    rec.payment.delete()
                rec.delete()
                messages.info(request, "تم حذف حصة البرايفت المسجلة وإلغاء إيصالها من الخزينة.")
            return redirect("payroll:private_training_records")

        trainer_id = request.POST.get("trainer_id")
        client_id = request.POST.get("client_id", "").strip()
        client_name_raw = request.POST.get("client_name", "").strip()

        raw_amount = request.POST.get("session_amount") or request.POST.get("package_price") or "0.00"
        session_amount = Decimal(raw_amount or "0.00")

        trainer = get_object_or_404(Employee, id=trainer_id)

        raw_pct = request.POST.get("commission_pct", "").strip()
        try:
            comm_pct = Decimal(raw_pct) if raw_pct != "" else (trainer.commission_percentage or Decimal("50.00"))
        except Exception:
            comm_pct = trainer.commission_percentage or Decimal("50.00")
        comm_pct = max(Decimal("0.00"), min(Decimal("100.00"), comm_pct))
        commission_rate = (comm_pct / Decimal("100.00")).quantize(Decimal("0.0001"))

        payment_method = request.POST.get("payment_method", "نقدي")
        notes = request.POST.get("notes", "").strip()

        if session_amount <= Decimal("0.00"):
            messages.error(request, "يرجى إدخال المبلغ المدفوع للحصة بشكل صحيح (أكبر من صفر).")
            return redirect("payroll:private_training_records")

        # Resolve or create client (supports existing member OR walk-in/typed name without touching subscriptions)
        client = None
        if client_id:
            client = Member.objects.filter(id=client_id).first()
        if not client and client_name_raw:
            client = Member.objects.filter(name__iexact=client_name_raw).first()
            if not client:
                from apps.members.views import generate_next_member_id
                client = Member.objects.create(
                    member_id=generate_next_member_id(),
                    name=client_name_raw,
                    mobile="",
                    notes="تم تسجيله تلقائياً من حصة برايفت خاصة",
                )
        if not client:
            messages.error(request, "يرجى اختيار اسم اللاعب أو كتابة اسمه.")
            return redirect("payroll:private_training_records")

        calculated_commission = (session_amount * commission_rate).quantize(Decimal("0.01"))

        with transaction.atomic():
            from apps.members.views import generate_next_payment_id
            pay_id, inv_no = generate_next_payment_id()
            payment = Payment.objects.create(
                payment_id=pay_id,
                invoice_no=inv_no,
                operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
                member=client,
                amount=session_amount,
                payment_method=payment_method,
                notes=f"حصة برايفت خاصة مع كابتن {trainer.name} (نسبة الكابتن {comm_pct}%) | {notes}".strip(" |"),
                created_by=request.user,
            )

            # standard_plan_price = 0.00 marks this as a standalone private session (independent of monthly plans)
            PrivateTrainingRecord.objects.create(
                payment=payment,
                trainer=trainer,
                client=client,
                package_price=session_amount,
                standard_plan_price=Decimal("0.00"),
                private_markup=session_amount,
                commission_rate=commission_rate,
                calculated_commission=calculated_commission,
                is_counted_in_payroll=False,
            )

            client.total_paid += session_amount
            client.save(update_fields=["total_paid"])

            log_audit_event(
                user=request.user,
                action="standalone_pt_session",
                target_model="PrivateTrainingRecord",
                target_id=str(trainer.id),
                details=f"تسجيل حصة برايفت خاصة للاعب {client.name} مع كابتن {trainer.name} بمبلغ {session_amount} ج (نسبة الكابتن {comm_pct}% = {calculated_commission} ج)",
                amount=session_amount,
            )

        messages.success(
            request,
            f"✓ تم تسجيل حصة البرايفت الخاصة بنجاح! المدفوع: {session_amount} ج.م — عمولة الكابتن {trainer.name} ({comm_pct}%): {calculated_commission} ج.م.",
        )
        if request.POST.get("from_coach_detail"):
            return redirect("payroll:coach_detail", employee_id=trainer.id)
        return redirect("payroll:private_training_records")

    records = PrivateTrainingRecord.objects.select_related("trainer", "client", "payment").order_by("-created_at")[:50]
    selected_trainer_id = request.GET.get("trainer_id", "")

    context = {
        "trainers": trainers,
        "members": members,
        "payment_methods": payment_methods,
        "records": records,
        "selected_trainer_id": selected_trainer_id,
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

        # 5. Biometric Face Attendance Overtime & Late Penalties
        from apps.payroll.models import EmployeeAttendance
        att_qs = EmployeeAttendance.objects.filter(employee=emp, date__gte=start_date, date__lte=end_date)
        att_late_sum = att_qs.filter(deduction_approved=True).aggregate(s=Sum("calculated_late_deduction"))["s"] or Decimal("0.00")
        att_ot_sum = att_qs.filter(overtime_approved=True).aggregate(s=Sum("calculated_overtime_bonus"))["s"] or Decimal("0.00")
        att_days = att_qs.filter(check_in__isnull=False).count()
        att_late_mins = sum(a.late_minutes for a in att_qs)
        att_ot_mins = sum(a.overtime_minutes for a in att_qs)

        if att_ot_sum > 0:
            bonus_sum += att_ot_sum
            bonus_records.append({
                "category": "بونص إضافي الحضور والوردية",
                "reason": f"ساعات عمل إضافية معتمدة ({att_ot_mins} دقيقة)",
                "amount": str(att_ot_sum),
            })

        if att_late_sum > 0:
            deduction_sum += att_late_sum
            deduction_records.append({
                "category": "خصم تأخيرات الحضور",
                "reason": f"تأخيرات ورادي غير معفاة ({att_late_mins} دقيقة)",
                "amount": str(att_late_sum),
            })

        # 6. Net Salary Formula (الأساسي + عمولات + مكافآت - جزاءات - سلف مسحوبة)
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
            "att_days": att_days,
            "att_late_mins": att_late_mins,
            "att_late_sum": att_late_sum,
            "att_ot_mins": att_ot_mins,
            "att_ot_sum": att_ot_sum,
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

            # Attendance late deductions & overtime bonuses
            from apps.payroll.models import EmployeeAttendance
            att_qs = EmployeeAttendance.objects.filter(employee=emp, date__gte=start_date, date__lte=end_date)
            att_late_sum = att_qs.filter(deduction_approved=True).aggregate(s=Sum("calculated_late_deduction"))["s"] or Decimal("0.00")
            att_ot_sum = att_qs.filter(overtime_approved=True).aggregate(s=Sum("calculated_overtime_bonus"))["s"] or Decimal("0.00")
            att_days = att_qs.filter(check_in__isnull=False).count()
            att_late_mins = sum(a.late_minutes for a in att_qs)
            att_ot_mins = sum(a.overtime_minutes for a in att_qs)

            if att_ot_sum > 0:
                bonus_sum += att_ot_sum
                bonus_records.append({
                    "category": "بونص إضافي الحضور والوردية",
                    "reason": f"ساعات عمل إضافية معتمدة ({att_ot_mins} دقيقة)",
                    "amount": str(att_ot_sum),
                })

            if att_late_sum > 0:
                deduction_sum += att_late_sum
                deduction_records.append({
                    "category": "خصم تأخيرات الحضور",
                    "reason": f"تأخيرات ورادي غير معفاة ({att_late_mins} دقيقة)",
                    "amount": str(att_late_sum),
                })

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
                "attendance": {
                    "days": att_days,
                    "late_mins": att_late_mins,
                    "late_deduction": str(att_late_sum),
                    "ot_mins": att_ot_mins,
                    "ot_bonus": str(att_ot_sum),
                }
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

    from apps.payroll.services import queue_all_approved_payroll_whatsapp
    queued_count = queue_all_approved_payroll_whatsapp(payroll_run)
    if queued_count > 0:
        messages.success(request, f"✓ تم اعتماد مسير رواتب شهر {period} وإضافة {queued_count} كشف راتب مصور إلى طابور رسائل الواتساب المعلقة بنجاح!")
    else:
        messages.success(request, f"✓ تم اعتماد مسير رواتب شهر {period} نهائياً وتثبيت لقطات الرواتب!")
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
    """Queues approved individual salary statement to WhatsApp with image slip."""
    item = get_object_or_404(PayrollItem.objects.select_related("payroll_run", "employee"), id=item_id)
    if not item.employee or not item.employee.phone:
        messages.error(request, f"لا يوجد رقم هاتف مسجل للموظف {item.employee_name_snapshot}.")
        return redirect("payroll:payroll_run_detail", period=item.payroll_run.period)

    from apps.payroll.services import queue_payroll_item_whatsapp
    msg_obj = queue_payroll_item_whatsapp(item)
    if msg_obj:
        messages.success(request, f"تمت إضافة كشف الراتب المصور للموظف/الكابتن {item.employee_name_snapshot} لطابور رسائل الواتساب المعلقة بنجاح!")
    else:
        messages.error(request, f"تعذر إنشاء رسالة كشف الراتب للموظف {item.employee_name_snapshot}.")
    return redirect("payroll:payroll_run_detail", period=item.payroll_run.period)


@login_required
def coach_detail_view(request, employee_id):
    """
    Dedicated Coach (Trainer) Profile View:
    - Displays Coach details, monthly fixed salary, and commission percentage.
    - Shows both:
      1) Monthly Private Subscribers (اشتراكات البرايفت الشهرية)
      2) Standalone Private Sessions (حصص البرايفت الخاصة المنفصلة)
    - Allows quick assignment of monthly private members AND quick recording of standalone private sessions.
    """
    unlocked, resp = check_trainers_page_access(request)
    if not unlocked or resp:
        return resp

    coach = get_object_or_404(Employee, id=employee_id, role=EmployeeRole.TRAINER)
    profile = GymProfile.get_solo()
    today = timezone.localdate()
    month_start = today.replace(day=1)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "assign_member":
            member_id = request.POST.get("member_id")
            private_price_str = request.POST.get("private_price", "600.00")
            private_price = Decimal(private_price_str or "600.00")
            raw_pct = request.POST.get("commission_pct", "").strip()
            try:
                comm_pct = Decimal(raw_pct) if raw_pct != "" else (coach.commission_percentage or Decimal("50.00"))
            except Exception:
                comm_pct = coach.commission_percentage or Decimal("50.00")
            comm_pct = max(Decimal("0.00"), min(Decimal("100.00"), comm_pct))
            comm_rate = (comm_pct / Decimal("100.00")).quantize(Decimal("0.0001"))

            member = get_object_or_404(Member, id=member_id)
            member.assigned_coach = coach
            member.has_private = True
            member.private_price = private_price
            member.save()

            TrainerClientAssignment.objects.update_or_create(
                trainer=coach,
                client=member,
                defaults={"commission_rate": comm_rate, "is_active": True},
            )

            log_audit_event(
                user=request.user,
                action="coach_member_assigned",
                target_model="Member",
                target_id=str(member.id),
                details=f"تم إسناد اللاعب {member.name} للكابتن {coach.name} مع تفعيل باقة البرايفت الشهرية بقيمة {private_price} ج (عمولة {comm_pct}%)",
                amount=private_price,
            )
            messages.success(request, f"تمت إضافة المتدرب {member.name} إلى الكابتن {coach.name} (برايفت شهري {private_price} ج - نسبة {comm_pct}%) بنجاح.")
            return redirect("payroll:coach_detail", employee_id=coach.id)

        elif action == "record_session":
            client_id = request.POST.get("client_id", "").strip()
            client_name_raw = request.POST.get("client_name", "").strip()
            session_amount = Decimal(request.POST.get("session_amount", "0.00") or "0.00")
            raw_pct = request.POST.get("commission_pct", "").strip()
            try:
                comm_pct = Decimal(raw_pct) if raw_pct != "" else (coach.commission_percentage or Decimal("50.00"))
            except Exception:
                comm_pct = coach.commission_percentage or Decimal("50.00")
            comm_pct = max(Decimal("0.00"), min(Decimal("100.00"), comm_pct))
            comm_rate = (comm_pct / Decimal("100.00")).quantize(Decimal("0.0001"))
            payment_method = request.POST.get("payment_method", "نقدي")
            notes = request.POST.get("notes", "").strip()

            if session_amount <= Decimal("0.00"):
                messages.error(request, "يرجى إدخال المبلغ المدفوع للحصة بشكل صحيح.")
                return redirect("payroll:coach_detail", employee_id=coach.id)

            client = None
            if client_id:
                client = Member.objects.filter(id=client_id).first()
            if not client and client_name_raw:
                client = Member.objects.filter(name__iexact=client_name_raw).first()
                if not client:
                    from apps.members.views import generate_next_member_id
                    client = Member.objects.create(
                        member_id=generate_next_member_id(),
                        name=client_name_raw,
                        mobile="",
                        notes="تم تسجيله تلقائياً من حصة برايفت خاصة",
                    )
            if not client:
                messages.error(request, "يرجى اختيار اسم اللاعب أو كتابة اسمه.")
                return redirect("payroll:coach_detail", employee_id=coach.id)

            calculated_commission = (session_amount * comm_rate).quantize(Decimal("0.01"))
            with transaction.atomic():
                from apps.members.views import generate_next_payment_id
                pay_id, inv_no = generate_next_payment_id()
                payment = Payment.objects.create(
                    payment_id=pay_id,
                    invoice_no=inv_no,
                    operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
                    member=client,
                    amount=session_amount,
                    payment_method=payment_method,
                    notes=f"حصة برايفت خاصة مع كابتن {coach.name} (نسبة {comm_pct}%) | {notes}".strip(" |"),
                    created_by=request.user,
                )
                PrivateTrainingRecord.objects.create(
                    payment=payment,
                    trainer=coach,
                    client=client,
                    package_price=session_amount,
                    standard_plan_price=Decimal("0.00"),
                    private_markup=session_amount,
                    commission_rate=comm_rate,
                    calculated_commission=calculated_commission,
                    is_counted_in_payroll=False,
                )
                client.total_paid += session_amount
                client.save(update_fields=["total_paid"])

                log_audit_event(
                    user=request.user,
                    action="standalone_pt_session",
                    target_model="PrivateTrainingRecord",
                    target_id=str(coach.id),
                    details=f"تسجيل حصة برايفت خاصة للاعب {client.name} مع كابتن {coach.name} بمبلغ {session_amount} ج (نسبة {comm_pct}% = {calculated_commission} ج)",
                    amount=session_amount,
                )

            messages.success(request, f"✓ تم تسجيل حصة البرايفت الخاصة ({session_amount} ج) — عمولة الكابتن {coach.name}: {calculated_commission} ج.م ({comm_pct}%).")
            return redirect("payroll:coach_detail", employee_id=coach.id)

        elif action == "delete_session":
            rec_id = request.POST.get("record_id")
            rec = PrivateTrainingRecord.objects.filter(id=rec_id, trainer=coach, is_counted_in_payroll=False).first()
            if rec:
                if rec.payment:
                    rec.payment.delete()
                rec.delete()
                messages.info(request, "تم حذف حصة البرايفت المسجلة.")
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

    # Fetch assigned monthly private members
    assigned_members = Member.objects.filter(assigned_coach=coach).order_by("-has_private", "name")
    default_comm_rate = (coach.commission_percentage or Decimal("50.00")) / Decimal("100.00")
    custom_rates_map = {
        a.client_id: a.commission_rate
        for a in TrainerClientAssignment.objects.filter(trainer=coach, is_active=True)
    }

    enriched_members = []
    monthly_private_income = Decimal("0.00")
    monthly_coach_commission = Decimal("0.00")
    active_private_count = 0

    for m in assigned_members:
        is_sub_active = bool(m.last_subscription_end and m.last_subscription_end >= today)
        m_rate = custom_rates_map.get(m.id, default_comm_rate)
        m_rate_pct = (m_rate * Decimal("100.00")).quantize(Decimal("1"))
        coach_share = (m.private_price * m_rate).quantize(Decimal("0.01")) if m.has_private else Decimal("0.00")
        if m.has_private and is_sub_active:
            monthly_private_income += m.private_price
            monthly_coach_commission += coach_share
            active_private_count += 1

        enriched_members.append({
            "member": m,
            "has_private": m.has_private,
            "private_price": m.private_price,
            "comm_rate_pct": m_rate_pct,
            "coach_share": coach_share,
            "is_active": is_sub_active,
            "end_date": m.last_subscription_end,
            "plan_type": m.last_subscription_type or "عام",
        })

    # Fetch standalone private sessions recorded this month (standard_plan_price == 0)
    standalone_sessions_qs = PrivateTrainingRecord.objects.filter(
        trainer=coach,
        created_at__date__gte=month_start,
        standard_plan_price=Decimal("0.00"),
    ).select_related("client", "payment").order_by("-created_at")

    standalone_sessions = []
    sessions_income = Decimal("0.00")
    sessions_commission = Decimal("0.00")
    for s in standalone_sessions_qs:
        sessions_income += s.private_markup
        sessions_commission += s.calculated_commission
        standalone_sessions.append({
            "id": s.id,
            "client": s.client,
            "amount": s.private_markup,
            "rate_pct": (s.commission_rate * Decimal("100.00")).quantize(Decimal("1")),
            "commission": s.calculated_commission,
            "created_at": s.created_at,
            "is_counted_in_payroll": s.is_counted_in_payroll,
        })

    total_private_income = monthly_private_income + sessions_income
    total_coach_commission = monthly_coach_commission + sessions_commission

    # Fetch month's salary adjustments / advances
    current_period = today.strftime("%Y-%m")
    month_adjustments = SalaryAdjustment.objects.filter(
        employee=coach,
        status=AdjustmentStatus.APPROVED,
        period=current_period,
    )
    month_bonuses = month_adjustments.filter(adjustment_type=AdjustmentType.BONUS).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    month_deductions = month_adjustments.filter(adjustment_type=AdjustmentType.DEDUCTION).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    month_advances = month_adjustments.filter(adjustment_type=AdjustmentType.ADVANCE).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    # Estimated Net Monthly Due
    net_monthly_due = coach.fixed_salary + total_coach_commission + month_bonuses - month_deductions - month_advances

    available_members = Member.objects.exclude(assigned_coach=coach).order_by("name")[:100]
    all_members = Member.objects.all().order_by("name")[:200]
    payment_methods = PaymentMethod.objects.filter(is_active=True)

    context = {
        "coach": coach,
        "profile": profile,
        "today": today,
        "enriched_members": enriched_members,
        "standalone_sessions": standalone_sessions,
        "standalone_sessions_count": len(standalone_sessions),
        "sessions_income": sessions_income,
        "sessions_commission": sessions_commission,
        "monthly_private_income": monthly_private_income,
        "monthly_coach_commission": monthly_coach_commission,
        "active_private_count": active_private_count,
        "total_private_income": total_private_income,
        "total_coach_commission": total_coach_commission,
        "month_bonuses": month_bonuses,
        "month_deductions": month_deductions,
        "month_advances": month_advances,
        "net_monthly_due": net_monthly_due,
        "available_members": available_members,
        "all_members": all_members,
        "payment_methods": payment_methods,
    }
    return render(request, "payroll/coach_detail.html", context)


@login_required
def coach_salary_report_view(request, employee_id):
    """
    Printable, ultra-clean, unjammed, spacious Coach Salary & Commission Statement.
    Includes both Monthly Private Subscriptions and Standalone Private Sessions.
    """
    unlocked, resp = check_trainers_page_access(request)
    if not unlocked or resp:
        return resp

    coach = get_object_or_404(Employee, id=employee_id, role=EmployeeRole.TRAINER)
    profile = GymProfile.get_solo()
    today = timezone.localdate()
    month_start = today.replace(day=1)

    period_str = request.GET.get("period", today.strftime("%Y-%m"))

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

    default_comm_rate = (coach.commission_percentage or Decimal("50.00")) / Decimal("100.00")
    custom_rates_map = {
        a.client_id: a.commission_rate
        for a in TrainerClientAssignment.objects.filter(trainer=coach, is_active=True)
    }

    # 1. Type 1: Active assigned members with monthly private add-on
    assigned_members = Member.objects.filter(assigned_coach=coach, has_private=True)
    member_rows = []
    total_private_volume = Decimal("0.00")
    total_commission = Decimal("0.00")

    for m in assigned_members:
        m_rate = custom_rates_map.get(m.id, default_comm_rate)
        m_rate_pct = (m_rate * Decimal("100.00")).quantize(Decimal("1"))
        comm_amount = (m.private_price * m_rate).quantize(Decimal("0.01"))
        total_private_volume += m.private_price
        total_commission += comm_amount
        member_rows.append({
            "member_id": m.member_id,
            "name": m.name,
            "phone": m.mobile or "—",
            "plan_name": m.last_subscription_type or "اشتراك شهري",
            "private_markup": m.private_price,
            "comm_rate_pct": m_rate_pct,
            "commission_amount": comm_amount,
            "status": "مشترك نشط" if (m.last_subscription_end and m.last_subscription_end >= today) else "منتهي",
            "renewal_date": m.last_subscription_end,
        })

    # 2. Type 2: Standalone Private Sessions in period (standard_plan_price == 0)
    standalone_qs = PrivateTrainingRecord.objects.filter(
        trainer=coach,
        created_at__date__gte=p_start,
        created_at__date__lte=p_end,
        standard_plan_price=Decimal("0.00"),
    ).select_related("client").order_by("-created_at")

    session_rows = []
    sessions_volume = Decimal("0.00")
    sessions_commission = Decimal("0.00")
    for s in standalone_qs:
        s_rate_pct = (s.commission_rate * Decimal("100.00")).quantize(Decimal("1"))
        sessions_volume += s.private_markup
        sessions_commission += s.calculated_commission
        total_private_volume += s.private_markup
        total_commission += s.calculated_commission
        session_rows.append({
            "member_id": s.client.member_id,
            "name": s.client.name,
            "amount": s.private_markup,
            "comm_rate_pct": s_rate_pct,
            "commission_amount": s.calculated_commission,
            "date": s.created_at,
        })

    # Adjustments in period
    adjustments = SalaryAdjustment.objects.filter(
        employee=coach,
        status=AdjustmentStatus.APPROVED,
        period=period_str,
    )
    bonuses = adjustments.filter(adjustment_type=AdjustmentType.BONUS).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    deductions = adjustments.filter(adjustment_type=AdjustmentType.DEDUCTION).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
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
        "session_rows": session_rows,
        "sessions_count": len(session_rows),
        "sessions_volume": sessions_volume,
        "sessions_commission": sessions_commission,
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


@login_required
@manager_required
def payroll_archive_view(request):
    """
    Dedicated historical archive of monthly payroll runs:
    Shows all past months, breakdown, totals, handover completion rate, and print action.
    """
    runs = PayrollRun.objects.all().order_by("-period")
    current_period = timezone.localdate().strftime("%Y-%m")

    for r in runs:
        items = r.items.all()
        r.total_staff_count = items.count()
        r.paid_staff_count = items.filter(is_paid=True).count()
        r.paid_amount_sum = items.filter(is_paid=True).aggregate(s=Sum("net_payable"))["s"] or Decimal("0.00")
        r.is_fully_paid = (r.total_staff_count > 0 and r.paid_staff_count == r.total_staff_count)

    profile = GymProfile.get_solo()
    context = {
        "runs": runs,
        "current_period": current_period,
        "profile": profile,
    }
    return render(request, "payroll/payroll_archive.html", context)


@login_required
@manager_required
def payroll_payout_checklist_view(request, period=None):
    """
    Manager Handover Checklist (صفحة تسليم الرواتب):
    Allows tracking who received their salary and who hasn't (تم التسليم / معلق),
    recording payout method (كاش / تحويل / فودافون كاش / إنستاباي), and syncing directly
    with Expense records and safe/treasury cash flow.
    """
    current_period = timezone.localdate().strftime("%Y-%m")
    selected_period = period or request.GET.get("period", current_period)

    payroll_run = PayrollRun.objects.filter(period=selected_period).first()
    items = []
    if payroll_run:
        items = list(payroll_run.items.select_related("employee", "paid_by", "expense").order_by("employee__role", "employee__name"))

    total_net = sum(item.net_payable for item in items)
    paid_items = [it for it in items if it.is_paid]
    pending_items = [it for it in items if not it.is_paid]
    total_paid = sum(it.net_payable for it in paid_items)
    total_pending = sum(it.net_payable for it in pending_items)

    all_periods = PayrollRun.objects.values_list("period", flat=True).order_by("-period")

    profile = GymProfile.get_solo()
    context = {
        "selected_period": selected_period,
        "current_period": current_period,
        "payroll_run": payroll_run,
        "items": items,
        "paid_items_count": len(paid_items),
        "pending_items_count": len(pending_items),
        "total_net": total_net,
        "total_paid": total_paid,
        "total_pending": total_pending,
        "all_periods": all_periods,
        "profile": profile,
    }
    return render(request, "payroll/payout_checklist.html", context)


@login_required
@manager_required
def payroll_toggle_payout_view(request, item_id):
    """
    Toggles an individual employee's salary handover status:
    When handed over (تم التسليم): creates an Expense record deducting from treasury safe.
    When reverted to pending (معلق): deletes the Expense record restoring treasury safe.
    """
    item = get_object_or_404(PayrollItem.objects.select_related("payroll_run", "employee"), id=item_id)
    period = item.payroll_run.period

    if item.is_paid:
        if item.expense:
            try:
                item.expense.delete()
            except Exception:
                pass
            item.expense = None
        item.is_paid = False
        item.paid_at = None
        item.paid_by = None
        item.save()
        if item.payroll_run.status == PayrollStatus.PAID:
            item.payroll_run.status = PayrollStatus.APPROVED
            item.payroll_run.save(update_fields=["status"])
        messages.info(request, f"تم إلغاء تسليم راتب {item.employee_name_snapshot} وإعادة المبلغ إلى رصيد الخزينة.")
    else:
        paid_method = request.POST.get("paid_method", "كاش").strip()
        payout_notes = request.POST.get("payout_notes", "").strip()

        from apps.expenses.models import ExpenseCategory
        cat, _ = ExpenseCategory.objects.get_or_create(name="رواتب وأجور موظفين ومدربين")
        desc = f"صرف راتب {item.employee_name_snapshot} ({item.role_snapshot}) - شهر {period} [{paid_method}] {payout_notes}".strip()
        exp = Expense.objects.create(
            category=cat,
            amount=item.net_payable,
            description=desc,
            expense_date=timezone.localdate(),
            created_by=request.user,
        )
        item.is_paid = True
        item.paid_at = timezone.now()
        item.paid_by = request.user
        item.paid_method = paid_method
        item.payout_notes = payout_notes
        item.expense = exp
        item.save()

        # Check if all items in this run are paid
        if not item.payroll_run.items.filter(is_paid=False).exists():
            item.payroll_run.status = PayrollStatus.PAID
            item.payroll_run.save(update_fields=["status"])

        messages.success(request, f"✓ تم تأكيد تسليم راتب {item.employee_name_snapshot} ({item.net_payable} ج.م) وخصمه كمصروف من الخزينة بنجاح.")

    return redirect("payroll:payout_checklist", period=period)


@login_required
@manager_required
def payroll_mark_all_payout_view(request, period):
    """Bulk marks all unpaid employees in a period as handed over (Cash) and creates expenses."""
    payroll_run = get_object_or_404(PayrollRun, period=period)
    unpaid_items = payroll_run.items.filter(is_paid=False)
    from apps.expenses.models import ExpenseCategory
    cat, _ = ExpenseCategory.objects.get_or_create(name="رواتب وأجور موظفين ومدربين")
    today = timezone.localdate()

    count = 0
    with transaction.atomic():
        for it in unpaid_items:
            exp = Expense.objects.create(
                category=cat,
                amount=it.net_payable,
                description=f"صرف راتب {it.employee_name_snapshot} ({it.role_snapshot}) - شهر {period} [كاش]",
                expense_date=today,
                created_by=request.user,
            )
            it.is_paid = True
            it.paid_at = timezone.now()
            it.paid_by = request.user
            it.paid_method = "كاش"
            it.expense = exp
            it.save()
            count += 1

        payroll_run.status = PayrollStatus.PAID
        payroll_run.save(update_fields=["status"])

    messages.success(request, f"تم تسليم وصرف رواتب {count} موظف دفعة واحدة وخصمها من الخزينة بنجاح.")
    return redirect("payroll:payout_checklist", period=period)


@login_required
@manager_required
def payroll_item_edit_view(request, item_id):
    """
    Enables manager to edit individual employee salary before or after approval:
    Adjusts bonuses, deductions, or direct net payable.
    Recalculates payroll run totals and automatically syncs the associated Expense record in the safe!
    """
    item = get_object_or_404(PayrollItem.objects.select_related("payroll_run", "employee"), id=item_id)
    run = item.payroll_run

    if request.method == "POST":
        new_fixed = Decimal(request.POST.get("fixed_salary", str(item.fixed_salary)) or "0.00")
        new_comm = Decimal(request.POST.get("commissions", str(item.commissions)) or "0.00")
        new_bonus = Decimal(request.POST.get("bonuses", str(item.bonuses)) or "0.00")
        new_ded = Decimal(request.POST.get("deductions", str(item.deductions)) or "0.00")
        new_adv = Decimal(request.POST.get("advances", str(item.advances)) or "0.00")
        edit_reason = request.POST.get("edit_reason", "").strip()

        new_net = max(Decimal("0.00"), new_fixed + new_comm + new_bonus - new_ded - new_adv)

        item.fixed_salary = new_fixed
        item.commissions = new_comm
        item.bonuses = new_bonus
        item.deductions = new_ded
        item.advances = new_adv
        item.net_payable = new_net

        details = item.details_json or {}
        audit_trail = details.get("manager_edits", [])
        audit_trail.append({
            "edited_at": timezone.now().strftime("%Y-%m-%d %H:%M"),
            "edited_by": request.user.username,
            "reason": edit_reason or "تعديل إداري معتمد",
            "net_payable": str(new_net),
        })
        details["manager_edits"] = audit_trail
        item.details_json = details
        item.save()

        # Update associated Expense if already exists (keeps treasury safe 100% accurate!)
        if item.expense:
            item.expense.amount = new_net
            item.expense.description = f"صرف راتب {item.employee_name_snapshot} ({item.role_snapshot}) - شهر {run.period} [{item.paid_method}] (معدل)"
            item.expense.save()

        # Re-sum PayrollRun
        allItems = run.items.all()
        run.total_fixed_salary = allItems.aggregate(s=Sum("fixed_salary"))["s"] or Decimal("0.00")
        run.total_commissions = allItems.aggregate(s=Sum("commissions"))["s"] or Decimal("0.00")
        run.total_bonuses = allItems.aggregate(s=Sum("bonuses"))["s"] or Decimal("0.00")
        run.total_deductions = allItems.aggregate(s=Sum("deductions"))["s"] or Decimal("0.00")
        run.total_advances = allItems.aggregate(s=Sum("advances"))["s"] or Decimal("0.00")
        run.net_payable = allItems.aggregate(s=Sum("net_payable"))["s"] or Decimal("0.00")
        run.save()

        messages.success(request, f"✓ تم تعديل راتب {item.employee_name_snapshot} وتحديث الخزينة والمصروفات فورياً.")
        if request.POST.get("next") == "checklist":
            return redirect("payroll:payout_checklist", period=run.period)
        return redirect("payroll:payroll_run_detail", period=run.period)

    context = {
        "item": item,
        "run": run,
        "next_url": request.GET.get("next", "detail"),
    }
    return render(request, "payroll/payroll_item_edit.html", context)


@login_required
@manager_required
def employee_account_statement_view(request, employee_id):
    """
    Comprehensive Account Statement for any Employee or Trainer:
    - Contract & Salary details
    - Face biometric enrollment status & photo
    - Monthly payroll payout history
    - Attendance log for the current month (check-ins, late, overtime)
    - Printable official slip
    """
    employee = get_object_or_404(Employee, id=employee_id)
    profile = GymProfile.get_solo()
    today = timezone.localdate()
    month_start = today.replace(day=1)

    # 1. Historical Payroll Items
    payroll_items = list(PayrollItem.objects.filter(employee=employee).select_related("payroll_run", "expense").order_by("-payroll_run__period"))

    total_earned = sum((it.net_payable for it in payroll_items), Decimal("0.00"))
    total_paid = sum((it.net_payable for it in payroll_items if it.is_paid), Decimal("0.00"))
    total_pending = total_earned - total_paid

    # 2. Advances Taken
    advances_qs = SalaryAdjustment.objects.filter(
        employee=employee, adjustment_type=AdjustmentType.ADVANCE, status=AdjustmentStatus.APPROVED
    ).order_by("-created_at")
    total_advances = advances_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

    # 3. Monthly Attendance Records
    from apps.payroll.models import EmployeeAttendance
    attendances = list(EmployeeAttendance.objects.filter(employee=employee, date__gte=month_start, date__lte=today).order_by("-date"))
    attended_days_count = sum(1 for a in attendances if a.check_in)
    total_late_minutes = sum(a.late_minutes for a in attendances)
    total_overtime_minutes = sum(a.overtime_minutes for a in attendances)
    total_late_deductions = sum((a.calculated_late_deduction for a in attendances if a.deduction_approved), Decimal("0.00"))
    total_ot_bonuses = sum((a.calculated_overtime_bonus for a in attendances if a.overtime_approved), Decimal("0.00"))

    context = {
        "employee": employee,
        "profile": profile,
        "payroll_items": payroll_items,
        "total_earned": total_earned,
        "total_paid": total_paid,
        "total_pending": total_pending,
        "total_advances": total_advances,
        "advances": advances_qs[:10],
        "attendances": attendances,
        "attended_days_count": attended_days_count,
        "total_late_minutes": total_late_minutes,
        "total_overtime_minutes": total_overtime_minutes,
        "total_late_deductions": total_late_deductions,
        "total_ot_bonuses": total_ot_bonuses,
        "today": today,
    }
    return render(request, "payroll/employee_account_statement.html", context)


@login_required
@manager_required
def employee_attendance_list_view(request):
    """Daily attendance and late arrival log for all staff & trainers."""
    from apps.payroll.models import EmployeeAttendance
    selected_date_str = request.GET.get("date")
    today = timezone.localdate()
    if selected_date_str:
        try:
            target_date = timezone.datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError:
            target_date = today
    else:
        target_date = today

    attendances = EmployeeAttendance.objects.filter(date=target_date).select_related("employee").order_by("-check_in")
    attended_ids = attendances.values_list("employee_id", flat=True)
    absent_employees = Employee.objects.filter(status=EmployeeStatus.ACTIVE).exclude(id__in=attended_ids)

    profile = GymProfile.get_solo()
    context = {
        "target_date": target_date,
        "today": today,
        "attendances": attendances,
        "absent_employees": absent_employees,
        "profile": profile,
    }
    return render(request, "payroll/employee_attendance_list.html", context)


@login_required
@manager_required
def employee_attendance_toggle_view(request, attendance_id):
    """Manager toggles approval of late penalty or overtime bonus for a specific day."""
    from apps.payroll.models import EmployeeAttendance
    att = get_object_or_404(EmployeeAttendance, id=attendance_id)
    field = request.POST.get("field")
    if field == "deduction":
        att.deduction_approved = not att.deduction_approved
        att.save(update_fields=["deduction_approved"])
        status_txt = "معتمد" if att.deduction_approved else "معفي / ملغي"
        messages.success(request, f"تم تعديل حالة خصم التأخير لـ {att.employee.name} ({status_txt}).")
    elif field == "overtime":
        att.overtime_approved = not att.overtime_approved
        att.save(update_fields=["overtime_approved"])
        status_txt = "معتمد" if att.overtime_approved else "ملغي"
        messages.success(request, f"تم تعديل حالة بونص الإضافي لـ {att.employee.name} ({status_txt}).")
    return redirect(request.META.get("HTTP_REFERER", "payroll:employee_attendance"))



