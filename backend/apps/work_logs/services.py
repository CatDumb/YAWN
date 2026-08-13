from calendar import monthrange
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.html import strip_tags

from apps.accounts.models import Company, CompanyMembership, ManagerAssignment, User
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
    _allow_final_period_mutation,
)


def company_date(at, company):
    return at.astimezone(ZoneInfo(company.timezone)).date()


def current_time():
    return getattr(settings, "WIO_FIXED_NOW", None) or timezone.now()


def company_today(company=None):
    now = current_time()
    if company:
        return company_date(now, company)
    return now.astimezone(ZoneInfo(settings.TIME_ZONE)).date()


def _validated_audit_reason(reason):
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason:
        raise ValidationError("An audit reason is required.")
    if len(reason) > 500:
        raise ValidationError("Audit reason cannot exceed 500 characters.")
    if strip_tags(reason) != reason:
        raise ValidationError("Audit reason must be plain text.")
    return reason


@transaction.atomic
def reopen_fiscal_periods(*, period_ids, actor, reason):
    """Reopen final periods through one authorized, reasoned, audited boundary."""
    reason = _validated_audit_reason(reason)
    if not getattr(actor, "pk", None) or not getattr(actor, "is_active", False):
        raise ValidationError("An active actor is required to reopen a fiscal period.")

    period_ids = list(dict.fromkeys(period_ids))
    if not period_ids:
        return []
    company_ids = list(
        FiscalPeriod.objects.filter(pk__in=period_ids)
        .order_by("company_id")
        .values_list("company_id", flat=True)
        .distinct()
    )
    companies = {
        company.pk: company
        for company in Company.objects.select_for_update().filter(pk__in=company_ids).order_by("pk")
    }
    periods = list(
        FiscalPeriod.objects.select_for_update()
        .filter(pk__in=period_ids)
        .order_by("company_id", "pk")
    )
    if len(periods) != len(period_ids):
        raise ValidationError("A selected fiscal period no longer exists.")
    if any(period.company_id not in companies for period in periods):
        raise RuntimeError("Fiscal period changed while acquiring its company lock.")

    memberships = {
        membership.company_id: membership
        for membership in CompanyMembership.objects.select_for_update().filter(
            user=actor,
            company_id__in=company_ids,
            is_active=True,
        )
    }
    if not actor.is_superuser:
        unauthorized = any(
            not companies[period.company_id].is_active
            or period.company_id not in memberships
            or memberships[period.company_id].role != CompanyMembership.Role.HR_ADMIN
            for period in periods
        )
        if unauthorized:
            raise ValidationError("Only an active HR admin or superuser can reopen this period.")

    reopened = []
    for period in periods:
        if period.state != FiscalPeriod.State.FINAL:
            continue
        previous_state = period.state
        period.state = FiscalPeriod.State.RECONCILIATION
        period.reopened_at = current_time()
        period.reopened_by = actor
        with _allow_final_period_mutation():
            period.save(update_fields=["state", "reopened_at", "reopened_by", "updated_at"])
        period.finalization_steps.update(completed_at=None, effect_token=None, metadata={})
        membership = memberships.get(period.company_id)
        AuditEvent.objects.create(
            actor=actor,
            event_type="work_logs.period_reopened",
            target_type="work_logs.FiscalPeriod",
            target_id=str(period.pk),
            metadata={
                "reason": reason,
                "actor_role": membership.role if membership else "superuser",
                "actor_company_id": period.company_id,
                "from_state": previous_state,
                "to_state": period.state,
            },
        )
        reopened.append(period)
    return reopened


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
    today = company_today(employee.company)
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


def _past_unreopened_cutoff(period):
    return current_time() > period.reconciliation_cutoff and period.reopened_at is None


def lock_wio_period(*, company_id, work_date):
    """Lock the fiscal boundary before any WIO row lock or mutation."""
    Company.objects.select_for_update().get(pk=company_id)
    period = (
        FiscalPeriod.objects.select_for_update()
        .filter(
            company_id=company_id,
            start_date__lte=work_date,
            end_date__gte=work_date,
        )
        .first()
    )
    if period and period.state == FiscalPeriod.State.FINAL:
        raise ValidationError("The fiscal period is final; HR/admin must reopen it for correction.")
    if period and _past_unreopened_cutoff(period):
        raise ValidationError("The fiscal reconciliation cutoff has passed.")
    return period


def audit_record(*, actor, event_type, record, reason=None, **metadata):
    membership = CompanyMembership.objects.filter(
        user=actor, company=record.employee.company, is_active=True
    ).first()
    context = {
        "work_date": str(record.work_date),
        "actor_role": (
            membership.role
            if membership
            else "superuser"
            if getattr(actor, "is_superuser", False)
            else "system"
        ),
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


def locked_hr_mutation_scope(
    *,
    actor,
    company_id,
    employee_id,
    employee_user_id,
):
    actor_id = getattr(actor, "pk", None)
    user_ids = {actor_id, employee_user_id} - {None}
    locked_users = {
        user.pk: user
        for user in User.objects.select_for_update().filter(pk__in=user_ids).order_by("pk")
    }
    locked_actor = locked_users.get(actor_id)
    locked_employee_user = locked_users.get(employee_user_id)
    if locked_actor is None or locked_employee_user is None or not locked_actor.is_active:
        raise ValidationError("Only HR/admin with one active company membership can perform this.")
    membership_ids = {employee_id}
    if not locked_actor.is_superuser:
        membership_ids.update(
            CompanyMembership.objects.filter(
                user_id=locked_actor.pk,
                is_active=True,
                company__is_active=True,
            )
            .order_by("pk")
            .values_list("pk", flat=True)[:2]
        )
    memberships = list(
        CompanyMembership.objects.select_for_update()
        .filter(pk__in=membership_ids)
        .select_related("company")
        .order_by("user_id", "pk")
    )
    locked_employee = next(
        (membership for membership in memberships if membership.pk == employee_id),
        None,
    )
    if locked_employee is None:
        raise RuntimeError("stale")
    if locked_actor.is_superuser:
        return locked_actor, locked_employee_user, locked_employee
    actor_memberships = [
        membership
        for membership in memberships
        if membership.user_id == locked_actor.pk
        and membership.is_active
        and membership.company.is_active
    ]
    if (
        len(actor_memberships) != 1
        or actor_memberships[0].company_id != company_id
        or actor_memberships[0].role != CompanyMembership.Role.HR_ADMIN
    ):
        raise ValidationError("Only HR/admin with one active company membership can perform this.")
    return locked_actor, locked_employee_user, locked_employee


def effective_manager(employee, work_date):
    assignments = list(
        ManagerAssignment.objects.select_related("manager")
        .filter(
            employee=employee,
            manager__is_active=True,
            manager__user__is_active=True,
            manager__company=employee.company,
            manager__role=CompanyMembership.Role.MANAGER,
            is_active=True,
            effective_from__lte=work_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=work_date))
        .order_by("effective_from", "pk")[:2]
    )
    return assignments[0] if len(assignments) == 1 else None


@transaction.atomic
def reject_record(*, record, actor, reason, period=None):
    """Manager-facing transition hook; assignment authorization belongs to subphase 3.3."""
    if period is None:
        identity = WorkInOfficeRecord.objects.select_related("employee").get(pk=record.pk)
        period = lock_wio_period(
            company_id=identity.employee.company_id,
            work_date=identity.work_date,
        )
    record = WorkInOfficeRecord.objects.select_for_update().get(pk=record.pk)
    if record.review_state != WorkInOfficeRecord.ReviewState.PENDING:
        raise ValidationError("Only pending office claims can be rejected.")
    now = current_time()
    deadline = timezone.make_aware(
        datetime.combine(company_today(record.employee.company) + timedelta(days=1), time.max),
        ZoneInfo(record.employee.company.timezone),
    )
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
    save_as_draft=False,
    version=None,
    expected_record_id=None,
    delete_draft=False,
    actor=None,
    override_reason=None,
):
    employee_id = employee.pk
    company_id = employee.company_id
    user_id = employee.user_id
    period = lock_wio_period(company_id=company_id, work_date=work_date)
    if override_reason:
        actor, locked_user, employee = locked_hr_mutation_scope(
            actor=actor,
            company_id=company_id,
            employee_id=employee_id,
            employee_user_id=user_id,
        )
    else:
        locked_user = User.objects.select_for_update().get(pk=user_id)
        employee = CompanyMembership.objects.select_for_update().get(pk=employee_id)
    locked_company = Company.objects.get(pk=company_id)
    if (
        employee.company_id != company_id
        or employee.user_id != user_id
        or (
            not override_reason
            and (
                not locked_company.is_active or not employee.is_active or not locked_user.is_active
            )
        )
    ):
        raise RuntimeError("stale")
    employee.company = locked_company
    if version is not None and expected_record_id is None:
        raise RuntimeError("record_id_required")
    records = WorkInOfficeRecord.objects.select_for_update().filter(
        employee=employee,
        work_date=work_date,
    )
    if expected_record_id is None:
        record = records.first()
    else:
        record = records.filter(pk=expected_record_id).first()
        if record is None:
            raise RuntimeError("stale")
    actor = actor or employee.user
    if record and version is None:
        raise RuntimeError("version_required")
    if record and record.version != version:
        raise RuntimeError("stale")
    if record and record.is_locked:
        raise ValidationError("This record is locked.")
    if record and record.review_state == WorkInOfficeRecord.ReviewState.REJECTED:
        if record.correction_deadline is None:
            raise ValidationError("The rejection correction deadline is unavailable.")
        if current_time() > record.correction_deadline:
            raise ValidationError("The rejection correction deadline has passed.")
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
    if correction and save_as_draft:
        raise ValidationError("Rejected records must be corrected or closed, not saved as drafts.")
    if correction and not location_choice:
        raise ValidationError("Rejected records require a corrected work location.")
    if not save_as_draft and not location_choice:
        raise ValidationError("Choose a work location or explicitly save a draft.")
    if override_reason:
        if work_date >= company_today(employee.company) - timedelta(days=1):
            raise ValidationError("Overrides are only available for older dates.")
        reason = eligibility_reason(employee, work_date)
        if reason:
            raise ValidationError(f"This date is ineligible: {reason}.")
        if period is None:
            raise ValidationError("Older-date overrides must belong to a fiscal period.")
    elif not correction:
        validate_record_date(employee, work_date)
    snapshot = snapshot_for(employee, work_date)
    old_state = record.review_state if record else None
    old_location_choice = record.location_choice if record else None
    old_note = record.note if record else ""
    old_rejection_reason = record.approver_note if record else ""
    old_rejected_at = record.rejected_at if record else None
    old_correction_deadline = record.correction_deadline if record else None
    if record is None:
        record = WorkInOfficeRecord(employee=employee, work_date=work_date)
    record.location_choice = location_choice or None
    record.note = note if location_choice == WorkInOfficeRecord.LocationChoice.IN_OFFICE else ""
    record.assignment_snapshot = snapshot["assignment"]
    record.policy_snapshot = {
        "eligibility_reason": snapshot["eligibility_reason"],
        "rule": snapshot["rule"],
    }
    if save_as_draft:
        if record.pk and old_state != WorkInOfficeRecord.ReviewState.DRAFT:
            raise ValidationError("Only new or existing draft records can be saved as drafts.")
        record.review_state = WorkInOfficeRecord.ReviewState.DRAFT
        record.submitted_at = None
        record.approval_method = None
        record.approved_at = None
        record.approved_by_snapshot = {}
        record.approval_owner_snapshot = {}
    elif location_choice == WorkInOfficeRecord.LocationChoice.IN_OFFICE:
        record.submitted_at = current_time()
        manager = effective_manager(employee, work_date)
        record.approval_owner_snapshot = (
            {"membership_id": manager.manager_id, "assignment_id": manager.pk} if manager else {}
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
        record.submitted_at = current_time()
        record.approval_method = None
        record.approved_at = None
        record.approved_by_snapshot = {}
        record.approval_owner_snapshot = {}
    else:
        record.review_state = WorkInOfficeRecord.ReviewState.DRAFT
        record.approval_method = None
        record.approved_at = None
        record.approved_by_snapshot = {}
        record.approval_owner_snapshot = {}
    if correction:
        record.approver_note = ""
        record.rejected_at = None
        record.correction_deadline = None
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
            if location_choice == WorkInOfficeRecord.LocationChoice.IN_OFFICE
            else "work_logs.record_rejection_corrected_not_in_office"
        )
    elif (
        old_state == WorkInOfficeRecord.ReviewState.NOT_REQUIRED
        and record.review_state == WorkInOfficeRecord.ReviewState.NOT_REQUIRED
    ):
        event = "work_logs.record_not_in_office_updated"
    correction_metadata = (
        {
            "previous_location_choice": old_location_choice,
            "previous_note": old_note,
            "rejection_reason": old_rejection_reason,
            "previous_rejected_at": (old_rejected_at.isoformat() if old_rejected_at else None),
            "previous_correction_deadline": (
                old_correction_deadline.isoformat() if old_correction_deadline else None
            ),
            "location_choice": record.location_choice,
            "note": record.note,
        }
        if correction
        else {}
    )
    audit_record(
        actor=actor,
        event_type=event,
        record=record,
        from_state=old_state,
        to_state=record.review_state,
        **correction_metadata,
    )
    if override_reason:
        audit_record(
            actor=actor,
            event_type="work_logs.record_older_date_overridden",
            record=record,
            reason=override_reason,
            from_state=old_state,
            to_state=record.review_state,
        )
    return record


@transaction.atomic
def undo_self_approval(*, employee, record_id, version, actor):
    expected_company_id = employee.company_id
    expected_user_id = employee.user_id
    identity = (
        WorkInOfficeRecord.objects.select_related("employee")
        .filter(pk=record_id, employee=employee)
        .first()
    )
    if identity is None:
        raise ValidationError("Self-approval undo is unavailable.")
    if (
        identity.employee.company_id != expected_company_id
        or identity.employee.user_id != expected_user_id
    ):
        raise RuntimeError("stale")
    expected_work_date = identity.work_date
    lock_wio_period(
        company_id=expected_company_id,
        work_date=expected_work_date,
    )
    if not Company.objects.get(pk=expected_company_id).is_active:
        raise RuntimeError("stale")
    locked_user = User.objects.select_for_update().filter(pk=expected_user_id).first()
    locked_employee = CompanyMembership.objects.select_for_update().filter(pk=employee.pk).first()
    if (
        locked_user is None
        or not locked_user.is_active
        or locked_employee is None
        or not locked_employee.is_active
        or locked_employee.company_id != expected_company_id
        or locked_employee.user_id != expected_user_id
    ):
        raise RuntimeError("stale")
    record = (
        WorkInOfficeRecord.objects.select_for_update()
        .filter(pk=record_id, employee=locked_employee)
        .first()
    )
    if record is not None and record.work_date != expected_work_date:
        raise RuntimeError("stale")
    if (
        record is None
        or record.review_state != WorkInOfficeRecord.ReviewState.APPROVED
        or record.approval_method != WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED
    ):
        raise ValidationError("Self-approval undo is unavailable.")
    if version is None or record.version != version:
        raise RuntimeError("stale")
    if record.approved_at is None or current_time() > record.approved_at + timedelta(seconds=10):
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


@transaction.atomic
def reverse_approved_record(*, record, actor, reason):
    if not reason or not reason.strip():
        raise ValidationError("An audit reason is required.")
    identity = WorkInOfficeRecord.objects.select_related("employee").get(pk=record.pk)
    expected_employee_id = identity.employee_id
    expected_company_id = identity.employee.company_id
    expected_user_id = identity.employee.user_id
    expected_work_date = identity.work_date
    period = lock_wio_period(
        company_id=expected_company_id,
        work_date=expected_work_date,
    )
    actor, _, locked_employee = locked_hr_mutation_scope(
        actor=actor,
        company_id=expected_company_id,
        employee_id=expected_employee_id,
        employee_user_id=expected_user_id,
    )
    if (
        locked_employee is None
        or locked_employee.company_id != expected_company_id
        or locked_employee.user_id != expected_user_id
    ):
        raise RuntimeError("stale")
    record = (
        WorkInOfficeRecord.objects.select_for_update()
        .select_related("employee__company")
        .get(pk=record.pk)
    )
    if record.employee_id != expected_employee_id or record.work_date != expected_work_date:
        raise RuntimeError("stale")
    record.employee = locked_employee
    if record.review_state != WorkInOfficeRecord.ReviewState.APPROVED:
        raise ValidationError("Only approved records can be reversed.")
    if period and (period.state == FiscalPeriod.State.FINAL or _past_unreopened_cutoff(period)):
        raise ValidationError("The fiscal period must be reopened before approval reversal.")
    previous_approval = {
        "previous_approval_method": record.approval_method,
        "previous_approved_at": record.approved_at.isoformat() if record.approved_at else None,
        "previous_approved_by_snapshot": record.approved_by_snapshot,
    }
    owner_id = record.approval_owner_snapshot.get("membership_id")
    owner_is_usable = (
        bool(owner_id)
        and CompanyMembership.objects.filter(
            pk=owner_id,
            company=record.employee.company,
            is_active=True,
            user__is_active=True,
            role=CompanyMembership.Role.MANAGER,
        ).exists()
    )
    record.approval_owner_snapshot = record.approval_owner_snapshot if owner_is_usable else {}
    record.review_state = (
        WorkInOfficeRecord.ReviewState.PENDING
        if owner_is_usable
        else WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    )
    record.approval_method = None
    record.approved_at = None
    record.approved_by_snapshot = {}
    record.version += 1
    record.save(
        update_fields=[
            "review_state",
            "approval_owner_snapshot",
            "approval_method",
            "approved_at",
            "approved_by_snapshot",
            "version",
            "updated_at",
        ]
    )
    audit_record(
        actor=actor,
        event_type="work_logs.approval_reversed_by_admin",
        record=record,
        reason=reason.strip(),
        from_state=WorkInOfficeRecord.ReviewState.APPROVED,
        to_state=record.review_state,
        **previous_approval,
    )
    return record


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
        cutoff_date = company_today(employee.company).replace(day=1) - timedelta(days=1)

    if cutoff_date >= company_today(employee.company):
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


def _validate_transition_values(*, company, cutoff_month, target_days, achieved_days):
    cutoff_date = date(
        cutoff_month.year,
        cutoff_month.month,
        monthrange(cutoff_month.year, cutoff_month.month)[1],
    )
    if cutoff_date >= company_today(company):
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
    company_id = employee.company_id
    company = Company.objects.select_for_update().get(pk=company_id)
    cutoff_date = _validate_transition_values(
        company=company,
        cutoff_month=cutoff_month,
        target_days=target_days,
        achieved_days=achieved_days,
    )
    target_periods = list(
        FiscalPeriod.objects.select_for_update()
        .filter(
            company_id=company_id,
            start_date__lte=cutoff_date,
            end_date__gte=cutoff_date,
        )
        .order_by("pk")[:2]
    )
    if len(target_periods) != 1:
        raise ValidationError("Transition cutoff must fall inside exactly one fiscal period.")
    target_period_id = target_periods[0].pk
    existing_period_id = (
        WioTransitionBaseline.objects.filter(employee_id=employee.pk)
        .values_list("period_id", flat=True)
        .first()
    )
    period_ids = {target_period_id}
    if existing_period_id is not None:
        period_ids.add(existing_period_id)
    locked_periods = {
        period.pk: period
        for period in FiscalPeriod.objects.select_for_update()
        .filter(pk__in=period_ids)
        .order_by("pk")
    }
    if set(locked_periods) != period_ids:
        raise RuntimeError("stale")
    target_matches = [
        locked_period
        for locked_period in locked_periods.values()
        if locked_period.company_id == company_id
        and locked_period.start_date <= cutoff_date <= locked_period.end_date
    ]
    if len(target_matches) != 1 or target_matches[0].pk != target_period_id:
        raise RuntimeError("stale")
    for locked_period in locked_periods.values():
        if (
            locked_period.state == FiscalPeriod.State.FINAL
            or _past_unreopened_cutoff(locked_period)
            or FinalizedLedgerRevision.objects.filter(
                period=locked_period,
                employee_id=employee.pk,
            ).exists()
        ):
            raise ValidationError("A finalized fiscal period cannot receive a transition baseline.")
    period = locked_periods[target_period_id]
    employee = CompanyMembership.objects.select_for_update().get(pk=employee.pk)
    if employee.company_id != company_id:
        raise RuntimeError("stale")
    baseline = WioTransitionBaseline.objects.select_for_update().filter(employee=employee).first()
    if baseline is not None and baseline.period_id not in period_ids:
        raise RuntimeError("stale")
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
