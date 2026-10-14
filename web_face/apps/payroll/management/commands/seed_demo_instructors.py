from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.members.models import Member, MemberStatus, Plan
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


class Command(BaseCommand):
    help = "Seeds 3 rich demo instructors with salary structures, clients, PT records, and monthly payroll"

    def handle(self, *args, **options):
        today = timezone.localdate()
        current_period = today.strftime("%Y-%m")

        # 1. Ensure Manager User exists
        manager_user = User.objects.filter(role=UserRole.MANAGER).first()
        if not manager_user:
            manager_user = User.objects.create_user(
                username="manager",
                password="password123",
                role=UserRole.MANAGER,
                first_name="مدير الصالة",
            )

        # 2. Ensure base demo members exist to assign as clients
        clients_data = [
            ("MEM-D0001", "محمد صلاح الدين", "01099881122", "male"),
            ("MEM-D0002", "كريم عبد العزيز", "01099882233", "male"),
            ("MEM-D0003", "ياسمين صبري", "01099883344", "female"),
            ("MEM-D0004", "عمر الشريف", "01099884455", "male"),
            ("MEM-D0005", "نور الهدى إبراهيم", "01099885566", "female"),
        ]
        clients = []
        for mid, name, mobile, gender in clients_data:
            c, _ = Member.objects.get_or_create(
                member_id=mid,
                defaults={
                    "name": name,
                    "mobile": mobile,
                    "gender": gender,
                    "current_status": MemberStatus.ACTIVE,
                    "last_subscription_start": today - timezone.timedelta(days=10),
                    "last_subscription_end": today + timezone.timedelta(days=20),
                    "last_subscription_type": "شهري VIP خاص",
                    "current_paid": Decimal("800.00"),
                    "current_remaining": Decimal("0.00"),
                    "total_paid": Decimal("800.00"),
                },
            )
            clients.append(c)

        # 3. Create Demo Instructors
        instructors_specs = [
            {
                "name": "كابتن أحمد كمال (Demo 1)",
                "phone": "01011112233",
                "fixed_salary": Decimal("4000.00"),
                "notes": "كابتن أول كمال أجسام ولياقة بدنية - مدرب تدريب خاص VIP معتمد",
                "rate": Decimal("0.5000"),
                "client_indices": [0, 1],
                "pt_sessions": [
                    {"client": clients[0], "package": Decimal("1200.00"), "standard": Decimal("800.00")},
                    {"client": clients[1], "package": Decimal("1000.00"), "standard": Decimal("700.00")},
                ],
                "bonus": Decimal("500.00"),
                "bonus_reason": "حافز التزام بأعلى تقييم عملاء لشهر أكتوبر",
                "deduction": Decimal("0.00"),
                "deduction_reason": "",
            },
            {
                "name": "كابتن محمود إبراهيم (Demo 2)",
                "phone": "01022223344",
                "fixed_salary": Decimal("3500.00"),
                "notes": "مدرب فتنس وتأهيل بدني عام ومتابعة الأجهزة الرياضية",
                "rate": Decimal("0.4000"),
                "client_indices": [1, 3],
                "pt_sessions": [
                    {"client": clients[3], "package": Decimal("1000.00"), "standard": Decimal("500.00")},
                ],
                "bonus": Decimal("150.00"),
                "bonus_reason": "حافز تنظيم الصالة وتجهيز بطولة اللياقة البدنية",
                "deduction": Decimal("200.00"),
                "deduction_reason": "خصم غياب يوم دون إخطار مسبق",
            },
            {
                "name": "كابتن سارة علي (Demo 3)",
                "phone": "01033334455",
                "fixed_salary": Decimal("3200.00"),
                "notes": "مدربة فتنس وكروس فيت وإيروبكس للسيدات",
                "rate": Decimal("0.5000"),
                "client_indices": [2, 4],
                "pt_sessions": [
                    {"client": clients[2], "package": Decimal("900.00"), "standard": Decimal("500.00")},
                    {"client": clients[4], "package": Decimal("800.00"), "standard": Decimal("500.00")},
                ],
                "bonus": Decimal("400.00"),
                "bonus_reason": "مكافأة تميز في جذب متدربات جدد لفصول الكروس فيت",
                "deduction": Decimal("0.00"),
                "deduction_reason": "",
            },
        ]

        created_employees = []
        for spec in instructors_specs:
            emp, created = Employee.objects.get_or_create(
                phone=spec["phone"],
                defaults={
                    "name": spec["name"],
                    "role": EmployeeRole.TRAINER,
                    "status": EmployeeStatus.ACTIVE,
                    "fixed_salary": spec["fixed_salary"],
                    "notes": spec["notes"],
                    "hire_date": today - timezone.timedelta(days=120),
                },
            )
            if not created:
                emp.name = spec["name"]
                emp.fixed_salary = spec["fixed_salary"]
                emp.notes = spec["notes"]
                emp.save()

            created_employees.append(emp)

            # Assign Clients
            for idx in spec["client_indices"]:
                client = clients[idx]
                TrainerClientAssignment.objects.get_or_create(
                    trainer=emp,
                    client=client,
                    defaults={
                        "commission_rate": spec["rate"],
                        "notes": "عقد تدريب خاص حصري",
                    },
                )

            # Private Training Records
            for pt in spec["pt_sessions"]:
                markup = pt["package"] - pt["standard"]
                comm = (markup * spec["rate"]).quantize(Decimal("0.01"))
                PrivateTrainingRecord.objects.get_or_create(
                    trainer=emp,
                    client=pt["client"],
                    package_price=pt["package"],
                    defaults={
                        "standard_plan_price": pt["standard"],
                        "private_markup": markup,
                        "commission_rate": spec["rate"],
                        "calculated_commission": comm,
                    },
                )

            # Adjustments
            if spec["bonus"] > Decimal("0.00"):
                SalaryAdjustment.objects.get_or_create(
                    employee=emp,
                    period=current_period,
                    adjustment_type=AdjustmentType.BONUS,
                    defaults={
                        "category": "مكافأة أداء",
                        "amount": spec["bonus"],
                        "reason": spec["bonus_reason"],
                        "status": AdjustmentStatus.APPROVED,
                        "created_by": manager_user,
                        "approved_by": manager_user,
                        "approved_at": timezone.now(),
                    },
                )

            if spec["deduction"] > Decimal("0.00"):
                SalaryAdjustment.objects.get_or_create(
                    employee=emp,
                    period=current_period,
                    adjustment_type=AdjustmentType.DEDUCTION,
                    defaults={
                        "category": "خصم غياب",
                        "amount": spec["deduction"],
                        "reason": spec["deduction_reason"],
                        "status": AdjustmentStatus.APPROVED,
                        "created_by": manager_user,
                        "approved_by": manager_user,
                        "approved_at": timezone.now(),
                    },
                )

        # 4. Generate / Calculate Payroll Run for current period
        payroll_run, _ = PayrollRun.objects.get_or_create(
            period=current_period,
            defaults={
                "status": PayrollStatus.CALCULATED,
                "notes": f"مسير رواتب تجريبي معتمد لشهر {current_period}",
            },
        )

        total_fixed = Decimal("0.00")
        total_comm = Decimal("0.00")
        total_bonuses = Decimal("0.00")
        total_deductions = Decimal("0.00")
        total_net = Decimal("0.00")

        for emp in created_employees:
            # Sum PT commissions
            comm_sum = Decimal("0.00")
            for pt in emp.private_trainings.all():
                comm_sum += pt.calculated_commission

            # Sum approved bonuses & deductions
            bonuses_sum = Decimal("0.00")
            for adj in emp.adjustments.filter(period=current_period, adjustment_type=AdjustmentType.BONUS, status=AdjustmentStatus.APPROVED):
                bonuses_sum += adj.amount

            deductions_sum = Decimal("0.00")
            for adj in emp.adjustments.filter(period=current_period, adjustment_type=AdjustmentType.DEDUCTION, status=AdjustmentStatus.APPROVED):
                deductions_sum += adj.amount

            net_sal = emp.fixed_salary + comm_sum + bonuses_sum - deductions_sum

            PayrollItem.objects.update_or_create(
                payroll_run=payroll_run,
                employee=emp,
                defaults={
                    "employee_name_snapshot": emp.name,
                    "role_snapshot": emp.get_role_display(),
                    "fixed_salary": emp.fixed_salary,
                    "commissions": comm_sum,
                    "bonuses": bonuses_sum,
                    "deductions": deductions_sum,
                    "net_payable": net_sal,
                    "details_json": {
                        "fixed": float(emp.fixed_salary),
                        "commissions": float(comm_sum),
                        "bonuses": float(bonuses_sum),
                        "deductions": float(deductions_sum),
                    },
                },
            )

            total_fixed += emp.fixed_salary
            total_comm += comm_sum
            total_bonuses += bonuses_sum
            total_deductions += deductions_sum
            total_net += net_sal

        payroll_run.total_fixed_salary = total_fixed
        payroll_run.total_commissions = total_comm
        payroll_run.total_bonuses = total_bonuses
        payroll_run.total_deductions = total_deductions
        payroll_run.net_payable = total_net
        payroll_run.status = PayrollStatus.CALCULATED
        payroll_run.save()

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded 3 demo instructors and created Payroll Run for {current_period}. Total net: {total_net} EGP"
        ))
