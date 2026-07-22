from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AccessRequest, Company, CompanyMembership, ManagerAssignment, User
from apps.accounts.services import schedule_approval_email_delivery
from apps.audit.models import AuditEvent


def _is_identity_admin(user):
    if not user or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return (
        user.is_staff
        and user.memberships.filter(
            company__is_active=True,
            is_active=True,
            role=CompanyMembership.Role.HR_ADMIN,
        ).exists()
    )


def _managed_company_ids(user):
    return CompanyMembership.objects.filter(
        user=user,
        company__is_active=True,
        is_active=True,
        role=CompanyMembership.Role.HR_ADMIN,
    ).values("company_id")


@admin.register(User)
class YawnUserAdmin(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "is_staff", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    actions = ["disable_selected_users", "enable_selected_users"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal information", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
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
                "fields": ("email", "password1", "password2", "is_staff"),
            },
        ),
    )

    def has_module_permission(self, request):
        return _is_identity_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return _is_identity_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return _is_identity_admin(request.user)

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return (
            queryset.filter(memberships__company_id__in=_managed_company_ids(request.user))
            .exclude(is_superuser=True)
            .distinct()
        )

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return super().get_readonly_fields(request, obj)
        return [
            *[field.name for field in self.model._meta.fields],
            *[field.name for field in self.model._meta.many_to_many],
        ]

    @admin.action(description="Disable selected users")
    @transaction.atomic
    def disable_selected_users(self, request, queryset):
        user_ids = list(queryset.filter(is_active=True).values_list("pk", flat=True))
        users = User.objects.select_for_update().filter(pk__in=user_ids, is_active=True)
        for user in users:
            user.is_active = False
            user.save(update_fields=["is_active"])
            AuditEvent.objects.create(
                actor=request.user,
                event_type="accounts.user_disabled",
                target_type="accounts.User",
                target_id=str(user.pk),
            )

    @admin.action(description="Enable selected users")
    @transaction.atomic
    def enable_selected_users(self, request, queryset):
        user_ids = list(queryset.filter(is_active=False).values_list("pk", flat=True))
        users = User.objects.select_for_update().filter(pk__in=user_ids, is_active=False)
        for user in users:
            user.is_active = True
            user.save(update_fields=["is_active"])
            AuditEvent.objects.create(
                actor=request.user,
                event_type="accounts.user_enabled",
                target_type="accounts.User",
                target_id=str(user.pk),
            )


@admin.register(AccessRequest)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ["email", "company", "status", "created_at", "reviewed_at", "reviewer"]
    list_filter = ["status", "company"]
    search_fields = ["email", "first_name", "last_name"]
    readonly_fields = [
        "company",
        "email",
        "first_name",
        "last_name",
        "request_fingerprint",
        "status",
        "created_at",
        "updated_at",
        "reviewed_at",
        "reviewer",
    ]
    actions = ["approve_access_requests", "reject_access_requests"]

    def has_module_permission(self, request):
        return _is_identity_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return _is_identity_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return _is_identity_admin(request.user)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(company_id__in=_managed_company_ids(request.user))

    @admin.action(description="Approve selected access requests")
    @transaction.atomic
    def approve_access_requests(self, request, queryset):
        pending_requests = queryset.select_for_update().filter(status=AccessRequest.Status.PENDING)
        skipped_count = 0
        for access_request in pending_requests:
            user = (
                User.objects.select_for_update().filter(email__iexact=access_request.email).first()
            )
            membership = None
            if user is not None:
                membership = (
                    CompanyMembership.objects.select_for_update()
                    .filter(user=user, company=access_request.company)
                    .first()
                )
                if membership is not None and not membership.is_active:
                    skipped_count += 1
                    continue
            if user is None:
                user = User.objects.create_user(
                    email=access_request.email,
                    first_name=access_request.first_name,
                    last_name=access_request.last_name,
                )
            if membership is None:
                membership = CompanyMembership.objects.create(
                    user=user,
                    company=access_request.company,
                    role=CompanyMembership.Role.EMPLOYEE,
                    is_active=True,
                )

            now = timezone.now()
            access_request.status = AccessRequest.Status.APPROVED
            access_request.reviewer = request.user
            access_request.reviewed_at = now
            access_request.save(update_fields=["status", "reviewer", "reviewed_at", "updated_at"])
            AuditEvent.objects.create(
                actor=request.user,
                event_type="accounts.access_request_approved",
                target_type="accounts.AccessRequest",
                target_id=str(access_request.pk),
                metadata={"company_id": access_request.company_id, "user_id": user.pk},
            )
            schedule_approval_email_delivery(recipient=user.email)
        if skipped_count:
            self.message_user(
                request,
                f"{skipped_count} request(s) skipped; membership reactivation required.",
                level=messages.WARNING,
            )

    @admin.action(description="Reject selected access requests")
    @transaction.atomic
    def reject_access_requests(self, request, queryset):
        pending_requests = queryset.select_for_update().filter(status=AccessRequest.Status.PENDING)
        for access_request in pending_requests:
            access_request.status = AccessRequest.Status.REJECTED
            access_request.reviewer = request.user
            access_request.reviewed_at = timezone.now()
            access_request.save(update_fields=["status", "reviewer", "reviewed_at", "updated_at"])
            AuditEvent.objects.create(
                actor=request.user,
                event_type="accounts.access_request_rejected",
                target_type="accounts.AccessRequest",
                target_id=str(access_request.pk),
                metadata={"company_id": access_request.company_id},
            )


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "company", "role", "is_active", "joined_at"]
    list_filter = ["company", "role", "is_active"]
    search_fields = ["user__email", "company__name", "company__slug"]
    readonly_fields = ["joined_at"]
    actions = ["reactivate_selected_memberships"]

    def has_module_permission(self, request):
        return _is_identity_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return _is_identity_admin(request.user)

    def has_change_permission(self, request, obj=None):
        if not _is_identity_admin(request.user):
            return False
        if request.user.is_superuser or obj is None:
            return True
        return _managed_company_ids(request.user).filter(company_id=obj.company_id).exists()

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(company_id__in=_managed_company_ids(request.user))

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return self.readonly_fields
        return [*self.readonly_fields, "user", "company", "role", "is_active"]

    @admin.action(description="Reactivate selected memberships")
    @transaction.atomic
    def reactivate_selected_memberships(self, request, queryset):
        memberships = queryset.select_for_update().filter(is_active=False)
        for membership in memberships:
            membership.is_active = True
            membership.save(update_fields=["is_active"])
            AuditEvent.objects.create(
                actor=request.user,
                event_type="accounts.membership_reactivated",
                target_type="accounts.CompanyMembership",
                target_id=str(membership.pk),
                metadata={"company_id": membership.company_id, "user_id": membership.user_id},
            )


admin.site.register(Company)
admin.site.register(ManagerAssignment)
