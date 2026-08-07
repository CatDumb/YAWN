from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import strip_tags

from apps.accounts.models import CompanyMembership
from apps.audit.models import AuditEvent
from apps.work_logs.models import (
    ApprovedLeave,
    BaseLocation,
    CompanyHoliday,
    EmployeeBaseLocationAssignment,
    EmployeeProjectAssignment,
    FiscalPeriod,
    Project,
    ProjectBaseLocationAssignment,
    ProjectStatusRule,
    RemoteWorkException,
    WioTransitionBaseline,
    WorkInOfficeRecord,
)
from apps.work_logs.services import (
    audit_record,
    company_today,
    current_time,
    eligibility_reason,
    lock_wio_period,
    locked_hr_mutation_scope,
    reopen_fiscal_periods,
    reverse_approved_record,
    save_record,
    save_transition_baseline,
)


def reason_confirmation(model_admin, request, queryset, *, title, submit_label):
    reason = request.POST.get("audit_reason", "").strip()
    error = None
    if request.POST.get("apply"):
        if not reason:
            error = "An audit reason is required."
        elif len(reason) > 500:
            error = "Audit reason cannot exceed 500 characters."
        elif strip_tags(reason) != reason:
            error = "Audit reason must be plain text."
        else:
            return reason, None
    context = {
        **model_admin.admin_site.each_context(request),
        "title": title,
        "objects": queryset,
        "opts": model_admin.model._meta,
        "action_name": request.POST.get("action", ""),
        "submit_label": submit_label,
        "error": error,
        "cancel_url": reverse(
            f"admin:{model_admin.model._meta.app_label}_{model_admin.model._meta.model_name}_changelist"
        ),
    }
    return None, TemplateResponse(
        request,
        "admin/work_logs/wio_action_confirmation.html",
        context,
    )


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

    @transaction.atomic
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

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)

    @transaction.atomic
    def delete_model(self, request, obj):
        target_type = obj._meta.label
        target_id = str(obj.pk)
        super().delete_model(request, obj)
        AuditEvent.objects.create(
            actor=request.user,
            event_type="work_logs.admin_deleted",
            target_type=target_type,
            target_id=target_id,
        )


@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(AuditedAdmin):
    list_display = ("name", "company", "start_date", "end_date", "reconciliation_cutoff", "state")
    list_filter = ("company", "state")
    actions = ("clone_selected_period", "reopen_for_correction")
    readonly_fields = ("reopened_at", "reopened_by")
    final_readonly_fields = (
        "company",
        "start_date",
        "end_date",
        "reconciliation_cutoff",
        "state",
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj and obj.state == FiscalPeriod.State.FINAL:
            return (*readonly_fields, *self.final_readonly_fields)
        return readonly_fields

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
    @transaction.atomic
    def reopen_for_correction(self, request, queryset):
        reason, response = reason_confirmation(
            self,
            request,
            queryset,
            title="Reopen final periods",
            submit_label="Reopen periods",
        )
        if response:
            return response
        period_ids = list(queryset.values_list("pk", flat=True))
        reopen_fiscal_periods(
            period_ids=period_ids,
            actor=request.user,
            reason=reason,
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


@admin.register(EmployeeBaseLocationAssignment)
class EmployeeBaseLocationAssignmentAdmin(EffectiveDatedAdmin):
    company_lookup = "employee__company"


@admin.register(ProjectBaseLocationAssignment)
class ProjectBaseLocationAssignmentAdmin(EffectiveDatedAdmin):
    company_lookup = "project__company"


class EmployeeScopedAdmin(AuditedAdmin):
    company_lookup = "employee__company"


class WorkInOfficeRecordAdminForm(forms.ModelForm):
    location_choice = forms.ChoiceField(
        required=True,
        choices=WorkInOfficeRecord.LocationChoice.choices,
    )
    override_reason = forms.CharField(
        required=True,
        max_length=500,
        help_text="Required audit reason for an older-date creation or correction.",
    )

    class Meta:
        model = WorkInOfficeRecord
        fields = ["employee", "work_date", "location_choice", "note", "override_reason"]

    def clean_note(self):
        note = self.cleaned_data.get("note", "")
        if strip_tags(note) != note:
            raise ValidationError("Note must be plain text.")
        return note

    def clean(self):
        cleaned = super().clean()
        employee = cleaned.get("employee")
        if employee is None and self.instance.employee_id:
            employee = self.instance.employee
        work_date = cleaned.get("work_date") or self.instance.work_date
        if not employee or not work_date:
            return cleaned
        if work_date >= company_today(employee.company) - timedelta(days=1):
            raise ValidationError("This workflow is only available for older dates.")
        reason = eligibility_reason(employee, work_date)
        if reason:
            raise ValidationError(f"This date is ineligible: {reason}.")
        baseline = WioTransitionBaseline.objects.filter(employee=employee).first()
        if baseline and work_date <= baseline.cutoff_date:
            raise ValidationError("This date belongs to the employee's legacy transition balance.")
        period = FiscalPeriod.objects.filter(
            company=employee.company,
            start_date__lte=work_date,
            end_date__gte=work_date,
        ).first()
        if period is None:
            raise ValidationError("Older-date overrides must belong to a fiscal period.")
        if period.state == FiscalPeriod.State.FINAL:
            raise ValidationError("The fiscal period is final.")
        if current_time() > period.reconciliation_cutoff and period.reopened_at is None:
            raise ValidationError("The fiscal reconciliation cutoff has passed.")
        if (
            not self.instance.pk
            and WorkInOfficeRecord.objects.filter(
                employee=employee,
                work_date=work_date,
            ).exists()
        ):
            raise ValidationError("A record already exists for this employee and date.")
        if (
            self.instance.pk
            and self.instance.review_state == WorkInOfficeRecord.ReviewState.REJECTED
            and (
                self.instance.correction_deadline is None
                or current_time() > self.instance.correction_deadline
            )
        ):
            raise ValidationError("The rejection correction deadline has passed.")
        return cleaned


class WorkInOfficeRecordAdmin(EmployeeScopedAdmin):
    form = WorkInOfficeRecordAdminForm
    actions = ("extend_rejected_correction", "reverse_approved_records")
    system_readonly_fields = (
        "employee",
        "work_date",
        "location_choice",
        "review_state",
        "note",
        "approver_note",
        "version",
        "assignment_snapshot",
        "policy_snapshot",
        "approval_owner_snapshot",
        "approved_at",
        "approved_by_snapshot",
        "approval_method",
        "created_at",
        "updated_at",
        "submitted_at",
        "rejected_at",
        "correction_deadline",
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.is_locked:
            return False
        return super().has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            editable = {"employee", "work_date", "location_choice", "note"}
        elif obj.is_locked:
            editable = set()
        else:
            editable = {"location_choice", "note"}
        return tuple(field for field in self.system_readonly_fields if field not in editable)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "employee":
            employees = CompanyMembership.objects.filter(
                is_active=True,
                user__is_active=True,
                company__is_active=True,
            )
            company_ids = self._allowed_company_ids(request.user)
            if company_ids is not None:
                employees = employees.filter(company_id__in=company_ids)
            kwargs["queryset"] = employees.select_related("company", "user")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        record = save_record(
            employee=obj.employee,
            work_date=obj.work_date,
            location_choice=obj.location_choice,
            note=obj.note,
            version=obj.version if change else None,
            expected_record_id=obj.pk if change else None,
            actor=request.user,
            override_reason=form.cleaned_data["override_reason"],
        )
        obj.__dict__.update(record.__dict__)

    def _reason_confirmation(self, request, queryset, *, title, submit_label):
        return reason_confirmation(
            self,
            request,
            queryset,
            title=title,
            submit_label=submit_label,
        )

    @admin.action(description="Extend rejected correction deadline by one day")
    @transaction.atomic
    def extend_rejected_correction(self, request, queryset):
        reason, response = self._reason_confirmation(
            request,
            queryset,
            title="Extend rejected correction deadline",
            submit_label="Extend deadline",
        )
        if response:
            return response
        record_ids = list(
            queryset.filter(review_state=WorkInOfficeRecord.ReviewState.REJECTED).values_list(
                "pk", flat=True
            )
        )
        for record_id in record_ids:
            identity = WorkInOfficeRecord.objects.select_related("employee").get(pk=record_id)
            expected_employee_id = identity.employee_id
            expected_company_id = identity.employee.company_id
            expected_user_id = identity.employee.user_id
            expected_work_date = identity.work_date
            try:
                period = lock_wio_period(
                    company_id=expected_company_id,
                    work_date=expected_work_date,
                )
                _, _, locked_employee = locked_hr_mutation_scope(
                    actor=request.user,
                    company_id=expected_company_id,
                    employee_id=expected_employee_id,
                    employee_user_id=expected_user_id,
                )
            except ValidationError as error:
                self.message_user(request, f"{identity}: {error.messages[0]}", messages.ERROR)
                continue
            except RuntimeError:
                self.message_user(request, f"{identity}: record changed.", messages.ERROR)
                continue
            record = WorkInOfficeRecord.objects.select_for_update().get(pk=record_id)
            if (
                record.employee_id != locked_employee.pk
                or record.work_date != expected_work_date
                or locked_employee.company_id != expected_company_id
                or locked_employee.user_id != expected_user_id
            ):
                self.message_user(request, f"{record} changed.", messages.ERROR)
                continue
            record.employee = locked_employee
            if record.review_state != WorkInOfficeRecord.ReviewState.REJECTED:
                self.message_user(request, f"{record} is no longer rejected.", messages.ERROR)
                continue
            if not period:
                self.message_user(
                    request,
                    f"{record} has no fiscal period and cannot be extended.",
                    messages.ERROR,
                )
                continue
            now = current_time()
            current_deadline = max(record.correction_deadline or now, now)
            extended_deadline = current_deadline + timedelta(days=1)
            if period.reopened_at is None:
                extended_deadline = min(extended_deadline, period.reconciliation_cutoff)
            if extended_deadline <= current_deadline:
                self.message_user(
                    request, f"{record} is already at the final cutoff.", messages.ERROR
                )
                continue
            record.correction_deadline = extended_deadline
            record.version += 1
            record.save(update_fields=["correction_deadline", "version", "updated_at"])
            audit_record(
                actor=request.user,
                event_type="work_logs.rejection_correction_extended",
                record=record,
                reason=reason,
                deadline=extended_deadline.isoformat(),
                from_state=record.review_state,
                to_state=record.review_state,
            )

    @admin.action(description="Reverse approved records for audited correction")
    @transaction.atomic
    def reverse_approved_records(self, request, queryset):
        reason, response = self._reason_confirmation(
            request,
            queryset,
            title="Reverse approved records",
            submit_label="Reverse approvals",
        )
        if response:
            return response
        for record in queryset.filter(review_state=WorkInOfficeRecord.ReviewState.APPROVED):
            try:
                reverse_approved_record(record=record, actor=request.user, reason=reason)
            except ValidationError as error:
                self.message_user(request, f"{record}: {error.messages[0]}", messages.ERROR)


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
