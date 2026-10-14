from decimal import Decimal
from django.db import models
from django.conf import settings
from apps.members.models import Member
from apps.payments.models import Payment


class EmployeeRole(models.TextChoices):
    TRAINER = "TRAINER", "مدرب (كابتن)"
    ASSISTANT = "ASSISTANT", "موظف استقبال"
    MANAGER = "MANAGER", "مدير صالة"


class EmployeeStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "نشط بالعمل"
    INACTIVE = "INACTIVE", "متوقف / إجازة"


class Employee(models.Model):
    name = models.CharField(max_length=150, verbose_name="اسم الموظف / المدرب")
    phone = models.CharField(max_length=20, verbose_name="رقم الهاتف")
    role = models.CharField(
        max_length=20,
        choices=EmployeeRole.choices,
        default=EmployeeRole.TRAINER,
        verbose_name="المسمى الوظيفي",
    )
    status = models.CharField(
        max_length=15,
        choices=EmployeeStatus.choices,
        default=EmployeeStatus.ACTIVE,
        verbose_name="حالة العمل",
    )
    fixed_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="الراتب الأساسي الشهري",
    )
    hire_date = models.DateField(null=True, blank=True, verbose_name="تاريخ التعيين")
    notes = models.TextField(blank=True, verbose_name="ملاحظات سرية")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإضافة")

    class Meta:
        verbose_name = "موظف / مدرب"
        verbose_name_plural = "الموظفون والمدربون"
        ordering = ["role", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_role_display()})"


class TrainerClientAssignment(models.Model):
    trainer = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="client_assignments",
        limit_choices_to={"role": EmployeeRole.TRAINER},
        verbose_name="المدرب",
    )
    client = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="trainer_assignments",
        verbose_name="اللاعب (العميل الخاص)",
    )
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.5000"),
        verbose_name="نسبة العمولة من التدريب الخاص (مثال: 0.50 لـ 50%)",
    )
    effective_from = models.DateField(auto_now_add=True, verbose_name="تاريخ بداية الاتفاق")
    effective_to = models.DateField(null=True, blank=True, verbose_name="تاريخ نهاية الاتفاق")
    is_active = models.BooleanField(default=True, verbose_name="ساري المفعول")
    notes = models.CharField(max_length=255, blank=True, verbose_name="ملاحظات العقد")

    class Meta:
        verbose_name = "عقد عمولة عميل خاص"
        verbose_name_plural = "عقود عمولات العملاء الخاصين"
        unique_together = ("trainer", "client")

    def __str__(self) -> str:
        pct = (self.commission_rate * 100).quantize(Decimal("1"))
        return f"{self.trainer.name} ⟷ {self.client.name} (عمولة {pct}%)"


class PrivateTrainingRecord(models.Model):
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="private_training_details",
        verbose_name="دفعة السداد",
    )
    trainer = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="private_trainings",
        verbose_name="المدرب المستحق للعمولة",
    )
    client = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        related_name="private_training_records",
        verbose_name="اللاعب",
    )
    package_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر الباقة الإجمالي")
    standard_plan_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر الاشتراك العام المماثل")
    private_markup = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), blank=True, verbose_name="قيمة التدريب الخاص (الفارق)")
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4, verbose_name="نسبة العمولة المطبقة")
    calculated_commission = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), blank=True, verbose_name="قيمة العمولة المستحقة")
    is_counted_in_payroll = models.BooleanField(default=False, verbose_name="تم تضمينها في مسير رواتب معتمد")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ العملية")

    class Meta:
        verbose_name = "سجل تدريب خاص"
        verbose_name_plural = "سجلات التدريب الخاص وعمولات المدربين"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.private_markup or self.private_markup == Decimal("0.00"):
            self.private_markup = max(Decimal("0.00"), self.package_price - self.standard_plan_price)
        if not self.calculated_commission or self.calculated_commission == Decimal("0.00"):
            self.calculated_commission = (self.private_markup * self.commission_rate).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.trainer.name} مع {self.client.name}: عمولة {self.calculated_commission} ج.م"


class AdjustmentType(models.TextChoices):
    BONUS = "BONUS", "مكافأة / حافز (+)"
    DEDUCTION = "DEDUCTION", "خصم / جزاء (-)"
    ADVANCE = "ADVANCE", "سلفة على الراتب (سحب مقدم -)"


class AdjustmentStatus(models.TextChoices):
    DRAFT = "DRAFT", "مسودة"
    PENDING = "PENDING", "في انتظار موافقة المدير"
    APPROVED = "APPROVED", "معتمد ومصروف"
    REJECTED = "REJECTED", "مرفوض"


class SalaryAdjustment(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="adjustments", verbose_name="الموظف")
    period = models.CharField(max_length=7, db_index=True, verbose_name="الشهر المستهدف (YYYY-MM)")
    adjustment_type = models.CharField(
        max_length=15,
        choices=AdjustmentType.choices,
        verbose_name="نوع البند",
    )
    category = models.CharField(max_length=50, verbose_name="التصنيف (أداء، تأخير، غياب، سلفة، مكافأة تشجيعية)")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    reason = models.TextField(verbose_name="سبب وتفاصيل القرار")
    status = models.CharField(
        max_length=20,
        choices=AdjustmentStatus.choices,
        default=AdjustmentStatus.PENDING,
        db_index=True,
        verbose_name="حالة الاعتماد",
    )
    expense = models.ForeignKey(
        "expenses.Expense",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_adjustments",
        verbose_name="سجل المصروف المرتبط بالخزينة",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_adjustments",
        verbose_name="الموظف الذي اقترح البند",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_adjustments",
        verbose_name="المدير الذي اعتمد البند",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="توقيت الاعتماد")
    rejection_reason = models.TextField(blank=True, verbose_name="سبب الرفض إن وجد")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "بند مكافأة أو خصم"
        verbose_name_plural = "المكافآت والخصومات"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        sign = "+" if self.adjustment_type == AdjustmentType.BONUS else "-"
        return f"{self.employee.name} | {sign}{self.amount} ج.م ({self.get_status_display()})"


class PayrollStatus(models.TextChoices):
    DRAFT = "DRAFT", "مسودة"
    CALCULATED = "CALCULATED", "تم الاحتساب"
    UNDER_REVIEW = "UNDER_REVIEW", "قيد مراجعة المدير"
    APPROVED = "APPROVED", "معتمد نهائياً (مغلق)"
    PAID = "PAID", "تم صرف الرواتب بالكامل"


class PayrollRun(models.Model):
    period = models.CharField(max_length=7, unique=True, db_index=True, verbose_name="شهر المسير (YYYY-MM)")
    status = models.CharField(
        max_length=20,
        choices=PayrollStatus.choices,
        default=PayrollStatus.DRAFT,
        verbose_name="حالة المسير",
    )
    total_fixed_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي الرواتب الأساسية")
    total_commissions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي عمولات التدريب الخاص")
    total_bonuses = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي المكافآت المعتمدة")
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي الخصومات والجزاءات")
    total_advances = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي السلف المسحوبة خلال الشهر")
    net_payable = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="صافي إجمالي المتبقي للصرف")
    
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="المدير المعتمد",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ ووقت الاعتماد النهائي")
    notes = models.TextField(blank=True, verbose_name="ملاحظات عامة على المسير")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ آخر تحديث")

    class Meta:
        verbose_name = "مسير رواتب شهري"
        verbose_name_plural = "مسيرات الرواتب الشهرية"
        ordering = ["-period"]

    def __str__(self) -> str:
        return f"مسير رواتب شهر {self.period} - {self.get_status_display()}"


class PayrollItem(models.Model):
    payroll_run = models.ForeignKey(
        PayrollRun,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="المسير الشهري",
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="payroll_items",
        verbose_name="الموظف / المدرب",
    )
    employee_name_snapshot = models.CharField(max_length=150, verbose_name="اسم الموظف وقت الاعتماد")
    role_snapshot = models.CharField(max_length=50, verbose_name="الوظيفة وقت الاعتماد")
    fixed_salary = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="الراتب الأساسي")
    commissions = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="عمولات التدريب الخاص")
    bonuses = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="المكافآت المعتمدة")
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="الخصومات والجزاءات")
    advances = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="السلف المعتمدة المسحوبة")
    net_payable = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="صافي الراتب المستحق (المتبقي للصرف)")
    
    details_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="تفاصيل البنود والعمولات والمكافآت بالتفصيل",
    )
    is_paid = models.BooleanField(default=False, verbose_name="تم الصرف")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الصرف الفعلي")
    whatsapp_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ إرسال كشف الراتب عبر الواتساب")

    class Meta:
        verbose_name = "كشف راتب موظف"
        verbose_name_plural = "كشوف رواتب الموظفين الفردية"
        unique_together = ("payroll_run", "employee")
        ordering = ["employee__role", "employee__name"]

    def __str__(self) -> str:
        return f"{self.employee_name_snapshot} ({self.payroll_run.period}): صافي {self.net_payable} ج.م"
