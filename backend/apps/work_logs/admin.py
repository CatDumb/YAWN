from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership
from apps.audit.models import AuditEvent
from apps.work_logs.models import (
    ApprovedLeave,
    BaseLocation,
    CompanyHoliday,
    EmployeeProjectAssignment,
    FiscalPeriod,
    Project,
    ProjectStatusRule,
    RemoteWorkException,
    WioTransitionBaseline,
    WorkInOfficeRecord,
)
from apps.work_logs.services import save_transition_baseline


class AuditedAdmin(admin.ModelAdmin):
    company_lookup = "company"

    def _allowed_company_ids(self, user):
        if not user.is_authenticated:
            return CompanyMembership.objects.none().values("company_id")
        if user.is_superuser:
            return None
        return CompanyMembership.objects.filter(
            user=user,
            is_active=True,
            company__is_active=True,
            role=CompanyMembership.Role.HR_ADMIN,
        ).values("company_id")

    def _allowed(self, request, obj=None):
        company_ids = self._allowed_company_ids(request.user)
        if company_ids is None:
            return True
        if not request.user.is_staff or not company_ids.exists():
            return False
        if obj is None:
            return True
        company = obj
        for part in self.company_lookup.split("__"):
            company = getattr(company, part)
        return company_ids.filter(company=company).exists()

    def has_module_permission(self, request):
        return self._allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request, obj)

    def has_add_permission(self, request):
        return self._allowed(request)

    def has_change_permission(self, request, obj=None):
        return self._allowed(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._allowed(request, obj)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        company_ids = self._allowed_company_ids(request.user)
        if company_ids is None:
            return queryset
        return queryset.filter(**{f"{self.company_lookup}__in": company_ids})

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        metadata = {}
        if source_id := request.GET.get("clone_from"):
            metadata["source_period_id"] = source_id
        AuditEvent.objects.create(
            actor=request.user,
            event_type="work_logs.admin_saved",
            target_type=obj._meta.label,
            target_id=str(obj.pk),
            metadata=metadata,
        )

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)


@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(AuditedAdmin):
    list_display = ("name", "company", "start_date", "end_date", "reconciliation_cutoff", "state")
    list_filter = ("company", "state")
    actions = ("clone_selected_period", "reopen_for_correction")

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if source_id := request.GET.get("clone_from"):
            source = self.get_queryset(request).filter(pk=source_id).first()
            if source:
                initial.update(
                    {
                        "company": source.company_id,
                        "name": f"{source.name} copy",
                        "start_date": source.end_date + timedelta(days=1),
                        "end_date": source.end_date
                        + timedelta(days=1)
                        + (source.end_date - source.start_date),
                        "reconciliation_cutoff": "",
                        "state": FiscalPeriod.State.UPCOMING,
                    }
                )
        return initial

    @admin.action(description="Clone selected period for review")
    def clone_selected_period(self, request, queryset):
        period = queryset.first()
        if not period:
            return None
        if queryset.count() != 1:
            self.message_user(request, "Select one period to clone.", messages.ERROR)
            return None
        return redirect(f"{reverse('admin:work_logs_fiscalperiod_add')}?clone_from={period.pk}")

    @admin.action(description="Reopen selected final periods for audited correction")
    def reopen_for_correction(self, request, queryset):
        for period in queryset.filter(state=FiscalPeriod.State.FINAL):
            period.state = FiscalPeriod.State.RECONCILIATION
            period.reopened_at = timezone.now()
            period.reopened_by = request.user
            period.save()
            AuditEvent.objects.create(
                actor=request.user,
                event_type="work_logs.period_reopened",
                target_type="work_logs.FiscalPeriod",
                target_id=str(period.pk),
            )


@admin.register(ProjectStatusRule)
class EffectiveDatedAdmin(AuditedAdmin):
    list_display = ("__str__", "effective_from", "effective_to")

    def delete_model(self, request, obj):
        try:
            super().delete_model(request, obj)
        except ValidationError as error:
            self.message_user(request, error.messages[0], messages.ERROR)


@admin.register(EmployeeProjectAssignment)
class AssignmentAdmin(EffectiveDatedAdmin):
    company_lookup = "employee__company"


class EmployeeScopedAdmin(AuditedAdmin):
    company_lookup = "employee__company"


class WorkInOfficeRecordAdmin(EmployeeScopedAdmin):
    actions = ("extend_rejected_correction",)
    readonly_fields = (
        "employee",
        "work_date",
        "location_choice",
        "review_state",
        "note",
        "approver_note",
        "version",
        "assignment_snapshot",
        "policy_snapshot",
        "created_at",
        "updated_at",
        "submitted_at",
        "rejected_at",
        "correction_deadline",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Extend rejected correction deadline by one day")
    def extend_rejected_correction(self, request, queryset):
        reason = request.POST.get("audit_reason", "").strip()
        if not reason:
            self.message_user(request, "An audit reason is required.", messages.ERROR)
            return
        for record in queryset.filter(review_state=WorkInOfficeRecord.ReviewState.REJECTED):
            period = FiscalPeriod.objects.filter(
                company=record.employee.company,
                start_date__lte=record.work_date,
                end_date__gte=record.work_date,
            ).first()
            if not period or period.state == FiscalPeriod.State.FINAL:
                self.message_user(
                    request,
                    f"{record} is final and cannot be extended.",
                    messages.ERROR,
                )
                continue
            cutoff = period.reconciliation_cutoff
            current_deadline = record.correction_deadline or timezone.now()
            extended_deadline = min(current_deadline + timedelta(days=1), cutoff)
            if extended_deadline <= current_deadline:
                self.message_user(
                    request, f"{record} is already at the final cutoff.", messages.ERROR
                )
                continue
            record.correction_deadline = extended_deadline
            record.version += 1
            record.save(update_fields=["correction_deadline", "version", "updated_at"])
            AuditEvent.objects.create(
                actor=request.user,
                event_type="work_logs.rejection_correction_extended",
                target_type="work_logs.WorkInOfficeRecord",
                target_id=str(record.pk),
                metadata={"deadline": extended_deadline.isoformat(), "reason": reason},
            )


class TransitionBaselineAdminForm(forms.ModelForm):
    correction_reason = forms.CharField(required=True, max_length=240)

    class Meta:
        model = WioTransitionBaseline
        fields = [
            "employee",
            "period",
            "cutoff_date",
            "target_days",
            "achieved_days",
            "version",
            "correction_reason",
        ]


@admin.register(WioTransitionBaseline)
class TransitionBaselineAdmin(EmployeeScopedAdmin):
    form = TransitionBaselineAdminForm
    list_display = ("employee", "cutoff_date", "target_days", "achieved_days", "version")
    readonly_fields = ("employee", "period", "cutoff_date", "version", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            return
        save_transition_baseline(
            employee=obj.employee,
            cutoff_month=obj.cutoff_date.replace(day=1),
            target_days=obj.target_days,
            achieved_days=obj.achieved_days,
            version=obj.version,
            actor=request.user,
            correction_reason=form.cleaned_data["correction_reason"],
            allow_locked_correction=True,
        )


admin.site.register(BaseLocation, AuditedAdmin)
admin.site.register(Project, AuditedAdmin)
admin.site.register(CompanyHoliday, AuditedAdmin)
admin.site.register(ApprovedLeave, EmployeeScopedAdmin)
admin.site.register(RemoteWorkException, EmployeeScopedAdmin)
admin.site.register(WorkInOfficeRecord, WorkInOfficeRecordAdmin)
