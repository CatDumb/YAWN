"""Persist due fiscal-period lifecycle transitions."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership
from apps.audit.models import AuditEvent
from apps.work_logs.models import (
    EmployeeBaseLocationAssignment,
    FiscalPeriod,
    Project,
    ProjectBaseLocationAssignment,
    ProjectStatusRule,
)


def _due_state(period: FiscalPeriod, *, at):
    local_day = timezone.localtime(at, ZoneInfo(period.company.timezone)).date()
    if local_day < period.start_date:
        return FiscalPeriod.State.UPCOMING
    if local_day <= period.end_date:
        return FiscalPeriod.State.ACTIVE
    return FiscalPeriod.State.RECONCILIATION


def _persist_state(period: FiscalPeriod, state: str):
    previous = period.state
    period.state = state
    period.save(update_fields=["state", "updated_at"])
    AuditEvent.objects.create(
        event_type="work_logs.period_state_advanced",
        target_type="work_logs.FiscalPeriod",
        target_id=str(period.pk),
        metadata={"from": previous, "to": state},
    )


def validate_period_policy_coverage(period: FiscalPeriod):
    """Require continuous rule coverage for every derived assignment status."""
    for status in ProjectStatusRule.AssignmentStatus.values:
        rules = list(
            ProjectStatusRule.objects.filter(
                company=period.company,
                assignment_status=status,
                effective_from__lte=period.end_date,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period.start_date))
            .order_by("effective_from", "pk")
        )
        cursor = period.start_date
        previous_end = None
        for rule in rules:
            if previous_end is not None and rule.effective_from <= previous_end:
                raise ValidationError(
                    f"Overlapping {status} policy coverage for fiscal period {period.name}."
                )
            if rule.effective_from > cursor:
                break
            covered_through = rule.effective_to or period.end_date
            previous_end = covered_through
            cursor = max(cursor, covered_through + timedelta(days=1))
            if cursor > period.end_date:
                break
        if cursor <= period.end_date:
            raise ValidationError(
                f"Incomplete {status} policy coverage for fiscal period {period.name}."
            )


@transaction.atomic
def synchronize_current_base_locations(*, at=None):
    """Refresh denormalized current-location projections from dated history."""
    at = at or timezone.now()
    changed = 0
    companies = list(Company.objects.select_for_update().filter(is_active=True))
    for company in companies:
        local_day = timezone.localtime(at, ZoneInfo(company.timezone)).date()
        employee_versions = (
            EmployeeBaseLocationAssignment.objects.filter(
                employee__company=company,
                effective_from__lte=local_day,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=local_day))
            .order_by("employee_id", "-effective_from", "-pk")
        )
        employee_locations = {}
        for version in employee_versions:
            employee_locations.setdefault(version.employee_id, version.base_location_id)
        memberships = list(
            CompanyMembership.objects.filter(pk__in=employee_locations).only(
                "pk", "base_location_id"
            )
        )
        changed_memberships = []
        for membership in memberships:
            location_id = employee_locations[membership.pk]
            if membership.base_location_id != location_id:
                membership.base_location_id = location_id
                changed_memberships.append(membership)
        CompanyMembership.objects.bulk_update(changed_memberships, ["base_location"])
        changed += len(changed_memberships)
        project_versions = (
            ProjectBaseLocationAssignment.objects.filter(
                project__company=company,
                effective_from__lte=local_day,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=local_day))
            .order_by("project_id", "-effective_from", "-pk")
        )
        project_locations = {}
        for version in project_versions:
            project_locations.setdefault(version.project_id, version.base_location_id)
        projects = list(
            Project.objects.filter(pk__in=project_locations).only("pk", "base_location_id")
        )
        changed_projects = []
        for project in projects:
            location_id = project_locations[project.pk]
            if project.base_location_id != location_id:
                project.base_location_id = location_id
                changed_projects.append(project)
        Project.objects.bulk_update(changed_projects, ["base_location"])
        changed += len(changed_projects)
    return changed


@transaction.atomic
def advance_fiscal_period_states(*, at=None):
    """Advance all non-final periods to their date-derived persisted state."""
    at = at or timezone.now()
    company_ids = (
        FiscalPeriod.objects.exclude(state=FiscalPeriod.State.FINAL)
        .values_list("company_id", flat=True)
        .distinct()
    )
    list(Company.objects.select_for_update().filter(pk__in=company_ids))
    periods = list(
        FiscalPeriod.objects.select_for_update()
        .select_related("company")
        .exclude(state=FiscalPeriod.State.FINAL)
    )
    due = [(period, _due_state(period, at=at)) for period in periods]
    for period, state in due:
        if state == FiscalPeriod.State.ACTIVE:
            validate_period_policy_coverage(period)
    changes = [(period, state) for period, state in due if period.state != state]

    # Release any old Active row before promoting its successor so the partial
    # unique constraint remains valid throughout the transaction.
    for period, state in changes:
        if period.state == FiscalPeriod.State.ACTIVE and state != FiscalPeriod.State.ACTIVE:
            _persist_state(period, state)
    for period, state in changes:
        if period.state != state:
            _persist_state(period, state)
    synchronize_current_base_locations(at=at)
    return len(changes)
