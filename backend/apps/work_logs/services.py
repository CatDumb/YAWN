from calendar import monthrange
from datetime import date, datetime, time, timedelta
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
    EmployeeBaseLocationAssignment,
    EmployeeProjectAssignment,
    FinalizedLedgerRevision,
    FiscalPeriod,
    ProjectBaseLocationAssignment,
    ProjectStatusRule,
    RemoteWorkException,
    WioTransitionBaseline,
    WorkInOfficeRecord,
)


def company_today(company=None):
    timezone_name = company.timezone if company else settings.TIME_ZONE
    return timezone.now().astimezone(ZoneInfo(timezone_name)).date()


def _assignment_status(employee, on_date):
    assignment = EmployeeProjectAssignment.objects.filter(
        employee=employee, effective_from__lte=on_date
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
    assignment = assignment.select_related(
        "project__base_location", "employee__base_location"
    ).first()
    if not assignment:
        return "benched", None
    employee_location = (
        EmployeeBaseLocationAssignment.objects.filter(
            employee=employee,
            effective_from__lte=on_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
        .first()
    )
    project_location = (
        ProjectBaseLocationAssignment.objects.filter(
            project=assignment.project,
            effective_from__lte=on_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
        .first()
    )
    employee_location_id = (
        employee_location.base_location_id if employee_location else employee.base_location_id
    )
    project_location_id = (
        project_location.base_location_id
        if project_location
        else assignment.project.base_location_id
    )
    status = "same_base" if project_location_id == employee_location_id else "different_base"
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
    baseline = WioTransitionBaseline.objects.filter(employee=employee).first()
    if baseline and work_date <= baseline.cutoff_date:
        raise ValidationError(
            "This date belongs to your legacy transition balance. New WIO starts after its cutoff."
        )
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
    employee = CompanyMembership.objects.select_for_update().get(pk=employee.pk)
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
    baseline = WioTransitionBaseline.objects.filter(employee=employee).first()
    if baseline and work_date <= baseline.cutoff_date:
        raise ValidationError(
            "This date belongs to your legacy transition balance. New WIO starts after its cutoff."
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
        record.submitted_at = timezone.now()
        if employee.role in {
            CompanyMembership.Role.MANAGER,
            CompanyMembership.Role.HR_ADMIN,
        }:
            record.review_state = WorkInOfficeRecord.ReviewState.APPROVED
            record.approval_method = WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED
            record.approved_at = record.submitted_at
            record.approved_by_snapshot = {
                "membership_id": employee.pk,
                "role": employee.role,
            }
            record.approval_owner_snapshot = {}
        else:
            manager = effective_manager(employee, work_date)
            record.approval_owner_snapshot = (
                {"membership_id": manager.manager_id, "assignment_id": manager.pk}
                if manager
                else {}
            )
            record.review_state = (
                WorkInOfficeRecord.ReviewState.PENDING
                if manager
                else WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
            )
            record.approval_method = None
            record.approved_at = None
            record.approved_by_snapshot = {}
    elif location_choice == WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE:
        record.review_state = WorkInOfficeRecord.ReviewState.NOT_REQUIRED
        record.submitted_at = timezone.now()
        record.approval_method = None
        record.approved_at = None
        record.approved_by_snapshot = {}
    else:
        record.review_state = WorkInOfficeRecord.ReviewState.DRAFT
        record.approval_method = None
        record.approved_at = None
        record.approved_by_snapshot = {}
    record.version = (record.version or 0) + (1 if record.pk else 0)
    record.full_clean()
    record.save()
    event = (
        "work_logs.record_self_approved"
        if record.approval_method == WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED
        else "work_logs.record_submitted"
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


@transaction.atomic
def undo_self_approval(*, employee, record_id, version, actor):
    record = (
        WorkInOfficeRecord.objects.select_for_update()
        .filter(pk=record_id, employee=employee)
        .first()
    )
    if (
        record is None
        or record.review_state != WorkInOfficeRecord.ReviewState.APPROVED
        or record.approval_method != WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED
    ):
        raise ValidationError("Self-approval undo is unavailable.")
    if version is None or record.version != version:
        raise RuntimeError("stale")
    if record.approved_at is None or timezone.now() > record.approved_at + timedelta(seconds=10):
        raise ValidationError("The 10-second self-approval undo window has expired.")
    record.review_state = WorkInOfficeRecord.ReviewState.DRAFT
    record.approved_at = None
    record.approved_by_snapshot = {}
    record.approval_method = None
    record.approval_owner_snapshot = {}
    record.version += 1
    record.save(
        update_fields=[
            "review_state",
            "approved_at",
            "approved_by_snapshot",
            "approval_method",
            "approval_owner_snapshot",
            "version",
            "updated_at",
        ]
    )
    audit_record(actor=actor, event_type="work_logs.self_approval_undone", record=record)
    return record


def _cutoff_date_for_month(cutoff_month):
    return date(
        cutoff_month.year,
        cutoff_month.month,
        monthrange(cutoff_month.year, cutoff_month.month)[1],
    )


def transition_baseline_locked(employee, baseline):
    return WorkInOfficeRecord.objects.filter(
        employee=employee, work_date__gt=baseline.cutoff_date
    ).exists()


def _latest_transition_cutoff(employee):
    """Return the latest safe month-end for a baseline, or ``None``.

    Existing WIO belongs to the employee, rather than their approval queue.  A
    carry-forward may therefore end on the month before the employee's first
    local record, provided both dates remain in the same mutable fiscal period.
    """
    first_record = (
        WorkInOfficeRecord.objects.filter(employee=employee).order_by("work_date", "pk").first()
    )
    if first_record:
        cutoff_date = first_record.work_date.replace(day=1) - timedelta(days=1)
    else:
        cutoff_date = company_today().replace(day=1) - timedelta(days=1)

    if cutoff_date >= company_today():
        return None
    period = _period_for(employee, cutoff_date)
    if period is None or period.state == FiscalPeriod.State.FINAL:
        return None
    if FinalizedLedgerRevision.objects.filter(period=period, employee=employee).exists():
        return None
    if first_record:
        first_period = _period_for(employee, first_record.work_date)
        if first_period is None or first_period.pk != period.pk:
            return None
    return cutoff_date


def transition_baseline_state(employee):
    baseline = (
        WioTransitionBaseline.objects.filter(employee=employee).select_related("period").first()
    )
    if baseline is None:
        latest_cutoff = _latest_transition_cutoff(employee)
        return {
            "baseline": None,
            "eligible": latest_cutoff is not None,
            "lock_reason": (
                None
                if latest_cutoff
                else "No completed transition month is available in an unfinalized fiscal period."
            ),
            "latest_cutoff_month": latest_cutoff.strftime("%Y-%m") if latest_cutoff else None,
        }
    locked = transition_baseline_locked(employee, baseline)
    return {
        "baseline": baseline,
        "eligible": False,
        "locked": locked,
        "lock_reason": "A post-cutoff WIO record exists." if locked else None,
        "latest_cutoff_month": None,
    }


def _transition_period(employee, cutoff_date):
    period = FiscalPeriod.objects.filter(
        company=employee.company,
        start_date__lte=cutoff_date,
        end_date__gte=cutoff_date,
    ).first()
    if period is None:
        raise ValidationError("Transition cutoff must fall inside one fiscal period.")
    if (
        period.state == FiscalPeriod.State.FINAL
        or FinalizedLedgerRevision.objects.filter(period=period, employee=employee).exists()
    ):
        raise ValidationError("A finalized fiscal period cannot receive a transition baseline.")
    return period


def _validate_transition_values(*, cutoff_month, target_days, achieved_days):
    cutoff_date = _cutoff_date_for_month(cutoff_month)
    if cutoff_date >= company_today():
        raise ValidationError("Transition cutoff month must be completed.")
    if target_days < 0 or achieved_days < 0:
        raise ValidationError("Transition days must be non-negative.")
    if target_days == 0 and achieved_days != 0:
        raise ValidationError("Achieved days must be zero when target days are zero.")
    return cutoff_date


def audit_transition_baseline(*, actor, event_type, baseline, reason=None):
    metadata = {
        "cutoff_date": baseline.cutoff_date.isoformat(),
        "target_days": str(baseline.target_days),
        "achieved_days": str(baseline.achieved_days),
        "version": baseline.version,
    }
    if reason:
        metadata["reason"] = reason
    AuditEvent.objects.create(
        actor=actor,
        event_type=event_type,
        target_type="work_logs.WioTransitionBaseline",
        target_id=str(baseline.pk),
        metadata=metadata,
    )


@transaction.atomic
def save_transition_baseline(
    *,
    employee,
    cutoff_month,
    target_days,
    achieved_days,
    actor,
    version=None,
    correction_reason=None,
    allow_locked_correction=False,
):
    """Create/update a one-time legacy aggregate without racing WIO creation."""
    employee = CompanyMembership.objects.select_for_update().get(pk=employee.pk)
    cutoff_date = _validate_transition_values(
        cutoff_month=cutoff_month,
        target_days=target_days,
        achieved_days=achieved_days,
    )
    period = _transition_period(employee, cutoff_date)
    baseline = WioTransitionBaseline.objects.select_for_update().filter(employee=employee).first()
    if baseline is None:
        first_record = (
            WorkInOfficeRecord.objects.filter(employee=employee).order_by("work_date", "pk").first()
        )
        if first_record and first_record.work_date <= cutoff_date:
            raise ValidationError("Transition cutoff must precede your earliest local WIO record.")
        if first_record:
            first_period = _period_for(employee, first_record.work_date)
            if first_period is None or first_period.pk != period.pk:
                raise ValidationError(
                    "Transition cutoff and existing WIO must belong to the same fiscal period."
                )
        baseline = WioTransitionBaseline.objects.create(
            employee=employee,
            period=period,
            cutoff_date=cutoff_date,
            target_days=target_days,
            achieved_days=achieved_days,
        )
        audit_transition_baseline(
            actor=actor,
            event_type="work_logs.transition_baseline_created",
            baseline=baseline,
        )
        return baseline

    if version is None or baseline.version != version:
        raise RuntimeError("stale")
    locked = transition_baseline_locked(employee, baseline)
    if locked and not allow_locked_correction:
        raise ValidationError("Transition baseline is locked after post-cutoff WIO begins.")
    if locked and cutoff_date != baseline.cutoff_date:
        raise ValidationError("Locked transition cutoff cannot change.")
    if locked and not correction_reason:
        raise ValidationError("HR/admin correction reason is required.")

    baseline.period = period
    baseline.cutoff_date = cutoff_date
    baseline.target_days = target_days
    baseline.achieved_days = achieved_days
    baseline.version += 1
    baseline.full_clean()
    baseline.save()
    audit_transition_baseline(
        actor=actor,
        event_type=(
            "work_logs.transition_baseline_corrected"
            if locked
            else "work_logs.transition_baseline_updated"
        ),
        baseline=baseline,
        reason=correction_reason,
    )
    return baseline
