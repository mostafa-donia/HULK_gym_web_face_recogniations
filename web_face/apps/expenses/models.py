from django.db import models
from django.conf import settings


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="تصنيف المصروف")
    is_active = models.BooleanField(default=True, verbose_name="مفعل")

    class Meta:
        verbose_name = "تصنيف مصروف"
        verbose_name_plural = "تصنيفات المصروفات"

    def __str__(self) -> str:
        return self.name


class Expense(models.Model):
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses",
        verbose_name="التصنيف",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    description = models.TextField(blank=True, verbose_name="الوصف والتفاصيل")
    expense_date = models.DateField(db_index=True, verbose_name="تاريخ المصروف")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التسجيل")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="المسجل",
    )

    class Meta:
        verbose_name = "مصروف"
        verbose_name_plural = "المصروفات"
        ordering = ["-expense_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.category.name}: {self.amount} ج.م ({self.expense_date})"
