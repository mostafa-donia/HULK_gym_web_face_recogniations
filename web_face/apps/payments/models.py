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


class PaymentOperationType(models.TextChoices):
    NEW_SUBSCRIPTION = "new_subscription", "اشتراك جديد"
    RENEWAL = "renewal", "تجديد اشتراك"
    REMAINING = "remaining", "سداد متبقي"
    BAR_SALE = "bar_sale", "مبيعات البار"


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

    class Meta:
        verbose_name = "عملية دفع"
        verbose_name_plural = "المدفوعات والفواتير"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        name = self.member.name if self.member else "عميل بار / غير مسجل"
        return f"{self.invoice_no} - {name} ({self.amount} ج.م)"


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

    class Meta:
        verbose_name = "عملية بيع بار"
        verbose_name_plural = "مبيعات البار"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        status_txt = "مدفوع" if self.is_paid else "آجل (لم يدفع)"
        return f"{self.sale_id} - {self.product.name} x {self.quantity} - {self.buyer_name} ({status_txt})"
