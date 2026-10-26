from decimal import Decimal
from django.db import models
from django.conf import settings
from apps.members.models import Member, Subscription


class PaymentMethod(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="طريقة الدفع")
    is_active = models.BooleanField(default=True, verbose_name="مفعلة")

    class Meta:
        verbose_name = "طريقة دفع"
        verbose_name_plural = "طرق الدفع"

    def __str__(self) -> str:
        return self.name


class AccountType(models.TextChoices):
    CASH = "cash", "خزينة نقدية (كاش)"
    VODAFONE_CASH = "vodafone_cash", "محفظة فودافون كاش / إلكترونية"
    BANK = "bank", "حساب بنكي / فيزا / إنستاباي"
    OTHER = "other", "حساب مالي آخر"


class FinancialAccount(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم الحساب / الخزينة")
    account_type = models.CharField(
        max_length=30,
        choices=AccountType.choices,
        default=AccountType.CASH,
        verbose_name="نوع الحساب",
    )
    account_number = models.CharField(max_length=100, blank=True, verbose_name="رقم الحساب / المحفظة / IBAN")
    initial_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="الرصيد الافتتاحي",
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_default = models.BooleanField(default=False, verbose_name="حساب افتراضي")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    branch = models.ForeignKey(
        "core.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_accounts",
        verbose_name="الفرع",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "حساب مالي / خزينة"
        verbose_name_plural = "الحسابات المالية والخزائن"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_account_type_display()})"

    @classmethod
    def get_default_accounts(cls, branch=None):
        """
        Ensures the 3 core accounts exist:
        1. Cash: خزينة النقدية (الكاش)
        2. Vodafone Cash: محفظة فودافون كاش
        3. Bank: الحساب البنكي / إنستاباي
        """
        defaults = [
            ("خزينة النقدية (الكاش)", AccountType.CASH, "الخزينة الرئيسية في الاستقبال للنقدية السائلة", True),
            ("محفظة فودافون كاش", AccountType.VODAFONE_CASH, "حساب استقبال وايداع تحويلات فودافون كاش والمحافظ الإلكترونية", False),
            ("الحساب البنكي / إنستاباي", AccountType.BANK, "الحساب البنكي ومدفوعات الفيزا وإنستاباي (InstaPay)", False),
        ]
        accounts = []
        for name, acc_type, desc, is_def in defaults:
            acc, _ = cls.objects.get_or_create(
                name=name,
                defaults={
                    "account_type": acc_type,
                    "notes": desc,
                    "is_default": is_def,
                    "branch": branch,
                },
            )
            accounts.append(acc)
        return accounts


class MoneyTransfer(models.Model):
    transfer_id = models.CharField(max_length=32, unique=True, db_index=True, verbose_name="رقم التحويل")
    from_account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.PROTECT,
        related_name="transfers_sent",
        verbose_name="من حساب (المحول منه)",
    )
    to_account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.PROTECT,
        related_name="transfers_received",
        verbose_name="إلى حساب (المحول إليه)",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المبلغ المحول")
    fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="رسوم ومصاريف التحويل",
    )
    transfer_date = models.DateField(db_index=True, verbose_name="تاريخ التحويل")
    reference_no = models.CharField(max_length=100, blank=True, verbose_name="رقم الإشعار / المرجع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات وسبب التحويل")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="المسجل",
    )
    branch = models.ForeignKey(
        "core.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="money_transfers",
        verbose_name="الفرع",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التسجيل")

    class Meta:
        verbose_name = "تحويل بين الحسابات"
        verbose_name_plural = "تحويلات الخزائن والحسابات"
        ordering = ["-transfer_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.transfer_id}: {self.amount} ج.م من {self.from_account.name} إلى {self.to_account.name}"


class PaymentOperationType(models.TextChoices):
    NEW_SUBSCRIPTION = "new_subscription", "اشتراك جديد"
    RENEWAL = "renewal", "تجديد اشتراك"
    REMAINING = "remaining", "سداد متبقي"
    BAR_SALE = "bar_sale", "مبيعات البار"
    REFUND = "refund", "استرداد اشتراك ملغي"


class Payment(models.Model):
    payment_id = models.CharField(max_length=30, unique=True, db_index=True, verbose_name="رقم المعاملة")
    invoice_no = models.CharField(max_length=30, unique=True, db_index=True, verbose_name="رقم الفاتورة")
    operation_type = models.CharField(
        max_length=30,
        choices=PaymentOperationType.choices,
        verbose_name="نوع العملية",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name="العضو",
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name="الاشتراك المرتبط",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ المحصل")
    payment_method = models.CharField(max_length=50, default="نقدي", verbose_name="طريقة الدفع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات الإيصال")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاريخ وتوقيت الدفع")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="المحصل",
    )
    branch = models.ForeignKey(
        "core.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name="الفرع",
    )
    account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name="الخزينة المودع بها",
    )

    class Meta:
        verbose_name = "عملية دفع"
        verbose_name_plural = "المدفوعات والفواتير"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        name = self.member.name if self.member else "عميل بار / غير مسجل"
        return f"{self.invoice_no} - {name} ({self.amount} ج.م)"

    def save(self, *args, **kwargs):
        if not self.branch_id:
            if self.member and getattr(self.member, "branch_id", None):
                self.branch = self.member.branch
            elif self.created_by and getattr(self.created_by, "branch_id", None):
                self.branch = self.created_by.branch
        if not self.account_id:
            from apps.payments.services import resolve_account_for_payment_method
            self.account = resolve_account_for_payment_method(self.payment_method, self.branch)
        super().save(*args, **kwargs)


class BarProductCategory(models.TextChoices):
    DRINKS = "drinks", "مشروبات ومياه"
    SUPPLEMENTS = "supplements", "مكملات وكرياتين وبروتين"
    SNACKS = "snacks", "سناكس وأغذية رياضية"
    OTHER = "other", "أخرى"


class BarProduct(models.Model):
    name = models.CharField(max_length=120, verbose_name="اسم المنتج")
    category = models.CharField(
        max_length=40,
        choices=BarProductCategory.choices,
        default=BarProductCategory.DRINKS,
        verbose_name="التصنيف",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر البيع للقطعة")
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        blank=True,
        verbose_name="سعر الشراء / التكلفة",
    )
    stock_quantity = models.IntegerField(default=0, verbose_name="الكمية المتاحة بالمخزون")
    min_stock_alert = models.IntegerField(default=5, verbose_name="حد التنبيه لنقص المخزون")
    is_active = models.BooleanField(default=True, verbose_name="متاح للبيع")
    branch = models.ForeignKey(
        "core.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bar_products",
        verbose_name="الفرع",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإضافة")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")

    class Meta:
        verbose_name = "منتج بار"
        verbose_name_plural = "مخزون البار والمنتجات"
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.price} ج.م) - متبقي {self.stock_quantity}"

    @property
    def is_low_stock(self) -> bool:
        return self.stock_quantity <= self.min_stock_alert

    @property
    def unit_profit(self) -> Decimal:
        """Actual net profit per item = selling price - cost price"""
        cost = self.cost_price or Decimal("0.00")
        return max(Decimal("0.00"), self.price - cost)


class BarSale(models.Model):
    sale_id = models.CharField(max_length=30, unique=True, db_index=True, verbose_name="رقم العملية")
    product = models.ForeignKey(
        BarProduct,
        on_delete=models.PROTECT,
        related_name="sales",
        verbose_name="المنتج",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bar_sales",
        verbose_name="العضو المسجل (اختياري)",
    )
    buyer_name = models.CharField(
        max_length=150,
        default="عميل نقدي / لاعب",
        verbose_name="اسم المشتري / اللاعب",
    )
    buyer_phone = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="رقم هاتف المشتري",
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="الكمية")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر القطعة")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ الإجمالي")
    is_paid = models.BooleanField(default=True, db_index=True, verbose_name="تم الدفع")
    payment_method = models.CharField(max_length=50, default="نقدي", verbose_name="طريقة الدفع")
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bar_sales",
        verbose_name="إيصال الخزينة",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات (مثلاً: هيدفع بعد التمرين)")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاريخ ووقت البيع")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ ووقت السداد")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="المسؤول",
    )
    branch = models.ForeignKey(
        "core.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bar_sales",
        verbose_name="الفرع",
        db_index=True,
    )

    class Meta:
        verbose_name = "عملية بيع بار"
        verbose_name_plural = "مبيعات البار"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        status_txt = "مدفوع" if self.is_paid else "آجل (لم يدفع)"
        return f"{self.sale_id} - {self.product.name} x {self.quantity} - {self.buyer_name} ({status_txt})"

    def save(self, *args, **kwargs):
        if not self.branch_id:
            if self.member and getattr(self.member, "branch_id", None):
                self.branch = self.member.branch
            elif self.payment and getattr(self.payment, "branch_id", None):
                self.branch = self.payment.branch
            elif self.created_by and getattr(self.created_by, "branch_id", None):
                self.branch = getattr(self.created_by, "branch", None)
        super().save(*args, **kwargs)


class HandoverStatus(models.TextChoices):
    PENDING = "pending", "معلق (بانتظار استلام واعتماد المدير)"
    APPROVED = "approved", "معتمد (تم الاستلام والإيداع بالخزينة الرئيسية)"
    REJECTED = "rejected", "مرفوض"


class ReceptionCashHandover(models.Model):
    handover_id = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        verbose_name="رقم إيصال التسليم",
    )
    receptionist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="handovers_given",
        verbose_name="موظف الاستقبال (المُسَلِّم)",
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handovers_received",
        verbose_name="المدير المستلم والمعتمد",
    )
    branch = models.ForeignKey(
        "core.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_handovers",
        verbose_name="الفرع",
    )
    target_account = models.ForeignKey(
        FinancialAccount,
        on_delete=models.PROTECT,
        related_name="handovers_deposited",
        verbose_name="الخزينة المودع بها",
    )
    expected_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="الرصيد الدفتري المتوقع بالدرج",
    )
    actual_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="المبلغ الفعلي المسلّم للمدير",
    )
    difference = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="فارق المطابقة (عجز / زيادة)",
        help_text="المبلغ الفعلي - المبلغ المتوقع. قيمة سالبة تعني عجز، موجبة تعني زيادة، صفر يعني مطابق",
    )
    status = models.CharField(
        max_length=20,
        choices=HandoverStatus.choices,
        default=HandoverStatus.PENDING,
        db_index=True,
        verbose_name="حالة التسليم",
    )
    handover_date = models.DateField(db_index=True, verbose_name="تاريخ التسليم")
    handover_time = models.DateTimeField(auto_now_add=True, verbose_name="توقيت التسليم")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ وتوقيت الاعتماد")
    notes = models.TextField(blank=True, verbose_name="ملاحظات موظف الاستقبال")
    manager_notes = models.TextField(blank=True, verbose_name="ملاحظات المدير عند المطابقة")

    class Meta:
        verbose_name = "تسليم نقدية من الريسبشن"
        verbose_name_plural = "تسليمات نقدية الريسبشن والخزينة"
        ordering = ["-handover_time"]

    def __str__(self) -> str:
        return f"{self.handover_id}: {self.actual_amount} ج.م من {self.receptionist} ({self.get_status_display()})"

    @property
    def has_shortage(self) -> bool:
        return self.difference < Decimal("0.00")

    @property
    def has_surplus(self) -> bool:
        return self.difference > Decimal("0.00")

    @property
    def is_matched(self) -> bool:
        return self.difference == Decimal("0.00")

    @property
    def shortage_amount(self) -> Decimal:
        return abs(self.difference) if self.has_shortage else Decimal("0.00")

    @property
    def surplus_amount(self) -> Decimal:
        return self.difference if self.has_surplus else Decimal("0.00")
