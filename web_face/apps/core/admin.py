from django.contrib import admin
from apps.core.models import Branch, GymProfile, SystemLicense, AuditLog

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "phone", "manager_name", "is_main", "is_active"]
    search_fields = ["name", "code", "phone", "manager_name"]
    list_filter = ["is_main", "is_active"]

@admin.register(SystemLicense)
class SystemLicenseAdmin(admin.ModelAdmin):
    list_display = ["client_name", "machine_id", "status", "license_type", "valid_until", "feature_multi_branch"]
    list_filter = ["status", "license_type", "feature_multi_branch"]

admin.site.register(GymProfile)
admin.site.register(AuditLog)
