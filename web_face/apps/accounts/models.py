from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    MANAGER = "MANAGER", "مدير الصالة"
    ASSISTANT = "ASSISTANT", "موظف استقبال"


class User(AbstractUser):
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.ASSISTANT,
        verbose_name="الدور والصلاحية",
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="رقم الهاتف")

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"

    @property
    def is_manager(self) -> bool:
        return self.role == UserRole.MANAGER or self.is_superuser

    @property
    def is_assistant(self) -> bool:
        return self.role == UserRole.ASSISTANT
