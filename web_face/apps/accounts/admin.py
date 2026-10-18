from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from apps.accounts.models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "first_name", "role", "branch", "is_staff", "is_active"]
    list_filter = ["role", "branch", "is_staff", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("الصلاحيات الإدارية والفروع", {"fields": ("role", "branch", "phone")}),
    )
