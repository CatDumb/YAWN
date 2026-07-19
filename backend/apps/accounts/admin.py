from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import Company, CompanyMembership, ManagerAssignment, User


@admin.register(User)
class WIOUserAdmin(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "is_staff", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal information", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )


admin.site.register(Company)
admin.site.register(CompanyMembership)
admin.site.register(ManagerAssignment)
