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


class Payment(models.Model):
    payment_id = models.CharField(max_length=30, unique=True, db_index=True, verbose_name="رقم المعاملة")
    invoice_no = models.CharField(max_length=30, unique=True, db_index=True, verbose_name="رقم الفاتورة")
    operation_type = models.CharField(
        max_length=30,
        choices=PaymentOperationType.choices,
        verbose_name="نوع العملية",
    )
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name="payments", verbose_name="العضو")
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
        return f"{self.invoice_no} - {self.member.name} ({self.amount} ج.م)"
