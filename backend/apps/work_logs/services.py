from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import CompanyMembership, ManagerAssignment
from apps.audit.models import AuditEvent
from apps.work_logs.models import (
    ApprovedLeave,
    CompanyHoliday,
    EmployeeProjectAssignment,
    FiscalPeriod,
    ProjectStatusRule,
    RemoteWorkException,
    WorkInOfficeRecord,
)


def company_today():
    return timezone.now().astimezone(ZoneInfo(settings.TIME_ZONE)).date()


def _assignment_status(employee, on_date):
    assignment = EmployeeProjectAssignment.objects.filter(
        employee=employee, effective_from__lte=on_date
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
    assignment = assignment.select_related(
        "project__base_location", "employee__base_location"
    ).first()
    if not assignment:
        return "benched", None
    status = (
        "same_base"
        if assignment.project.base_location_id == employee.base_location_id
        else "different_base"
    )
    return status, assignment


def eligibility_reasons(employee, work_date):
    if work_date.weekday() >= 5:
        return ["Weekend"]
    if CompanyHoliday.objects.filter(company=employee.company, date=work_date).exists():
        return ["Public holiday"]
    common = {"employee": employee, "effective_from__lte": work_date}
    leave = (
        ApprovedLeave.objects.filter(**common).filter(effective_to__isnull=True).exists()
        or ApprovedLeave.objects.filter(**common, effective_to__gte=work_date).exists()
    )
    reasons = ["Approved leave"] if leave else []
    remote = (
        RemoteWorkException.objects.filter(**common).filter(effective_to__isnull=True).exists()
        or RemoteWorkException.objects.filter(**common, effective_to__gte=work_date).exists()
    )
    if remote:
        reasons.append("Approved remote-work exception")
    return reasons


def eligibility_reason(employee, work_date):
    return "; ".join(eligibility_reasons(employee, work_date)) or None


def snapshot_for(employee, work_date):
    reason = eligibility_reason(employee, work_date)
    status, assignment = _assignment_status(employee, work_date)
    rule = (
        ProjectStatusRule.objects.filter(
            company=employee.company, assignment_status=status, effective_from__lte=work_date
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=work_date))
        .first()
    )
    return {
        "eligibility_reason": reason,
        "assignment": {"id": assignment.pk, "status": status} if assignment else {"status": status},
        "rule": {"id": rule.pk, "fraction": str(rule.expected_fraction)} if rule else {},
    }


def validate_record_date(employee, work_date):
    today = company_today()
    if work_date > today:
        raise ValidationError("Future dates belong in Planner.")
    if work_date < today - timedelta(days=1):
        raise ValidationError("This work date is closed. Ask HR/admin for an audited override.")
    reason = eligibility_reason(employee, work_date)
    if reason:
        raise ValidationError(f"This date is ineligible: {reason}.")


def _period_for(employee, work_date):
    return FiscalPeriod.objects.filter(
        company=employee.company,
        start_date__lte=work_date,
        end_date__gte=work_date,
    ).first()


def _company_day_end(day):
    return timezone.make_aware(datetime.combine(day, time.max), ZoneInfo(settings.TIME_ZONE))


def audit_record(*, actor, event_type, record, reason=None, **metadata):
    membership = CompanyMembership.objects.filter(
        user=actor, company=record.employee.company, is_active=True
    ).first()
    context = {
        "work_date": str(record.work_date),
        "actor_role": membership.role if membership else "system",
        "actor_company_id": record.employee.company_id,
        "revision": record.version,
        **metadata,
    }
    if reason:
        context["reason"] = reason
    AuditEvent.objects.create(
        actor=actor,
        event_type=event_type,
        target_type="work_logs.WorkInOfficeRecord",
        target_id=str(record.pk),
        metadata=context,
    )


def effective_manager(employee, work_date):
    assignments = list(
        ManagerAssignment.objects.select_related("manager")
        .filter(
            employee=employee,
            manager__is_active=True,
            manager__company=employee.company,
            is_active=True,
            effective_from__lte=work_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=work_date))
        .order_by("effective_from", "pk")[:2]
    )
    return assignments[0] if len(assignments) == 1 else None


@transaction.atomic
def reject_record(*, record, actor, reason):
    """Manager-facing transition hook; assignment authorization belongs to subphase 3.3."""
    record = WorkInOfficeRecord.objects.select_for_update().get(pk=record.pk)
    if record.review_state != WorkInOfficeRecord.ReviewState.PENDING:
        raise ValidationError("Only pending office claims can be rejected.")
    now = timezone.now()
    period = _period_for(record.employee, record.work_date)
    deadline = _company_day_end(company_today() + timedelta(days=1))
    if period and period.reconciliation_cutoff:
        deadline = min(deadline, period.reconciliation_cutoff)
    record.review_state = WorkInOfficeRecord.ReviewState.REJECTED
    record.approver_note = reason
    record.rejected_at = now
    record.correction_deadline = deadline
    record.version += 1
    record.save(
        update_fields=[
            "review_state",
            "approver_note",
            "rejected_at",
            "correction_deadline",
            "version",
            "updated_at",
        ]
    )
    audit_record(actor=actor, event_type="work_logs.record_rejected", record=record, reason=reason)
    return record


@transaction.atomic
def save_record(
    *,
    employee,
    work_date,
    location_choice=None,
    note="",
    version=None,
    delete_draft=False,
    actor=None,
    override_reason=None,
):
    record = (
        WorkInOfficeRecord.objects.select_for_update()
        .filter(employee=employee, work_date=work_date)
        .first()
    )
    actor = actor or employee.user
    if record and version is None:
        raise RuntimeError("version_required")
    if record and record.version != version:
        raise RuntimeError("stale")
    if record and record.review_state == WorkInOfficeRecord.ReviewState.APPROVED:
        raise ValidationError("Approved records are immutable.")
    if record and record.review_state == WorkInOfficeRecord.ReviewState.PENDING:
        raise ValidationError("Pending records are locked.")
    if (
        record
        and record.review_state == WorkInOfficeRecord.ReviewState.REJECTED
        and record.correction_deadline
        and timezone.now() > record.correction_deadline
    ):
        raise ValidationError("The rejection correction deadline has passed.")
    period = _period_for(employee, work_date)
    if record and record.review_state == WorkInOfficeRecord.ReviewState.REJECTED and period:
        if period.state == FiscalPeriod.State.FINAL:
            raise ValidationError(
                "The fiscal period is final; HR/admin must reopen it for correction."
            )
    if delete_draft:
        if not record or record.review_state != WorkInOfficeRecord.ReviewState.DRAFT:
            raise ValidationError("Only drafts can be deleted.")
        audit_record(actor=actor, event_type="work_logs.record_draft_deleted", record=record)
        record.delete()
        return None
    correction = record and record.review_state == WorkInOfficeRecord.ReviewState.REJECTED
    if not correction:
        try:
            validate_record_date(employee, work_date)
        except ValidationError as error:
            if not override_reason:
                raise
            if not CompanyMembership.objects.filter(
                user=actor,
                company=employee.company,
                is_active=True,
                role=CompanyMembership.Role.HR_ADMIN,
            ).exists():
                raise ValidationError("Only HR/admin can use an older-date override.") from error
    snapshot = snapshot_for(employee, work_date)
    old_state = record.review_state if record else None
    if record is None:
        record = WorkInOfficeRecord(employee=employee, work_date=work_date)
    record.location_choice = location_choice or None
    record.note = note if location_choice == WorkInOfficeRecord.LocationChoice.IN_OFFICE else ""
    record.assignment_snapshot = snapshot["assignment"]
    record.policy_snapshot = {
        "eligibility_reason": snapshot["eligibility_reason"],
        "rule": snapshot["rule"],
    }
    if location_choice == WorkInOfficeRecord.LocationChoice.IN_OFFICE:
        manager = effective_manager(employee, work_date)
        record.approval_owner_snapshot = (
            {"membership_id": manager.manager_id, "assignment_id": manager.pk} if manager else {}
        )
        record.review_state = (
            WorkInOfficeRecord.ReviewState.PENDING
            if manager
            else WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
        )
        record.submitted_at = timezone.now()
    elif location_choice == WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE:
        record.review_state = WorkInOfficeRecord.ReviewState.NOT_REQUIRED
        record.submitted_at = timezone.now()
    else:
        record.review_state = WorkInOfficeRecord.ReviewState.DRAFT
    record.version = (record.version or 0) + (1 if record.pk else 0)
    record.full_clean()
    record.save()
    event = (
        "work_logs.record_submitted"
        if record.review_state
        in {
            WorkInOfficeRecord.ReviewState.PENDING,
            WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
        }
        else "work_logs.record_not_in_office"
        if record.review_state == WorkInOfficeRecord.ReviewState.NOT_REQUIRED
        else "work_logs.record_draft_saved"
    )
    if old_state == WorkInOfficeRecord.ReviewState.REJECTED:
        event = (
            "work_logs.record_resubmitted"
            if location_choice
            else "work_logs.record_rejection_corrected"
        )
    audit_record(
        actor=actor,
        event_type=event,
        record=record,
        reason=override_reason,
        from_state=old_state,
        to_state=record.review_state,
    )
    return record
