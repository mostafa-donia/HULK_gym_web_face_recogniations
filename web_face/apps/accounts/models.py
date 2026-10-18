from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    OWNER = "OWNER", "مالك النظام (كافة الفروع)"
    MANAGER = "MANAGER", "مدير فرع"
    RECEPTION = "RECEPTION", "موظف استقبال فرع"
    ASSISTANT = "ASSISTANT", "موظف استقبال فرع"


class User(AbstractUser):
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.RECEPTION,
        verbose_name="الدور والصلاحية",
    )
    branch = models.ForeignKey(
        "core.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="الفرع التابع له",
        help_text="في حال كان المالك (OWNER)، يمكنه ترك هذا الحقل فارغاً للوصول لكافة الفروع",
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="رقم الهاتف")

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"

    @property
    def is_owner(self) -> bool:
        return self.role == UserRole.OWNER or self.is_superuser

    @property
    def is_manager(self) -> bool:
        return self.role in [UserRole.OWNER, UserRole.MANAGER] or self.is_superuser

    @property
    def is_reception(self) -> bool:
        return self.role in [UserRole.RECEPTION, UserRole.ASSISTANT]

    @property
    def is_assistant(self) -> bool:
        return self.is_reception

    @property
    def role_display_arabic(self) -> str:
        if self.is_owner:
            return "المالك (كافة الفروع)"
        elif self.role == UserRole.MANAGER:
            return "مدير فرع"
        return "استقبال"

    @property
    def branch_name(self) -> str:
        if self.branch:
            return self.branch.name
        return "الفرع الرئيسي"


# Patch AnonymousUser so template lookups never fail for non-logged-in visitors
from django.contrib.auth.models import AnonymousUser

AnonymousUser.branch_name = property(lambda self: "الفرع الرئيسي")
AnonymousUser.role_display_arabic = property(lambda self: "زائر")
