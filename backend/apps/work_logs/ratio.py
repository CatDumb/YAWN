"""Ratio domain math. Database reads prepare inputs; this module calculates no queries."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.work_logs.models import (
    ApprovedLeave,
    CompanyHoliday,
    EmployeeBaseLocationAssignment,
    EmployeeProjectAssignment,
    ProjectBaseLocationAssignment,
    ProjectStatusRule,
    RemoteWorkException,
    WioTransitionBaseline,
    WorkInOfficeRecord,
)


@dataclass(frozen=True)
class LedgerDay:
    date: date
    eligible: bool
    reason: str | None
    assignment_status: str
    rule_version: int | None
    expected_fraction: Decimal
    approval_credit: Decimal
    self_submitted_credit: Decimal
    source: str = "daily"


def percentage_up(value: Decimal) -> Decimal:
    return (value * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def calculate_ratio(days: list[LedgerDay]):
    """Pure contract shared by reports, CSV, dashboard, and Planner projections."""
    expected_total = sum((row.expected_fraction for row in days), Decimal("0"))
    approved_total = sum((row.approval_credit for row in days), Decimal("0"))
    self_submitted_total = sum((row.self_submitted_credit for row in days), Decimal("0"))
    if expected_total == 0:
        return {
            "days": days,
            "approved_days": approved_total,
            "self_submitted_days": self_submitted_total,
            "expected_fraction_sum": expected_total,
            "expected_days": expected_total,
            "expected_display": "0.00",
            "ratio": None,
            "ratio_display": "N/A",
            "percentage": None,
            "self_submitted_ratio": None,
            "self_submitted_ratio_display": "N/A",
            "self_submitted_percentage": None,
        }
    ratio = approved_total / expected_total
    self_submitted_ratio = self_submitted_total / expected_total
    return {
        "days": days,
        "approved_days": approved_total,
        "self_submitted_days": self_submitted_total,
        "expected_fraction_sum": expected_total,
        "expected_days": expected_total,
        "expected_display": f"{expected_total:.2f}",
        "ratio": ratio,
        "ratio_display": f"{percentage_up(ratio):.2f}%",
        "percentage": percentage_up(ratio),
        "self_submitted_ratio": self_submitted_ratio,
        "self_submitted_ratio_display": f"{percentage_up(self_submitted_ratio):.2f}%",
        "self_submitted_percentage": percentage_up(self_submitted_ratio),
    }


def _covers(item, on_date):
    return item.effective_from <= on_date and (
        item.effective_to is None or item.effective_to >= on_date
    )


def _effective_location_id(history, on_date, fallback_id):
    assignment = next((item for item in history if _covers(item, on_date)), None)
    return assignment.base_location_id if assignment else fallback_id


def ratio_ledger(*, employee, start_date, end_date, as_of_date):
    """Prepare a bounded number of queries, then delegate all math to ``calculate_ratio``."""
    legacy_rows = []
    calculation_start = start_date
    baseline = WioTransitionBaseline.objects.filter(employee=employee).first()
    if baseline:
        if start_date <= baseline.cutoff_date <= end_date:
            legacy_rows.append(
                LedgerDay(
                    date=baseline.cutoff_date,
                    eligible=True,
                    reason="Legacy carry-forward",
                    assignment_status="legacy",
                    rule_version=None,
                    expected_fraction=baseline.target_days,
                    approval_credit=Decimal("0"),
                    self_submitted_credit=baseline.achieved_days,
                    source="legacy_carry_forward",
                )
            )
        calculation_start = max(start_date, baseline.cutoff_date + timedelta(days=1))
    if calculation_start > end_date:
        return calculate_ratio(legacy_rows)
    dates = [
        calculation_start + timedelta(days=offset)
        for offset in range((end_date - calculation_start).days + 1)
    ]
    company = employee.company
    holidays = set(
        CompanyHoliday.objects.filter(
            company=company, date__range=(calculation_start, end_date)
        ).values_list("date", flat=True)
    )
    leaves = list(
        ApprovedLeave.objects.filter(employee=employee, effective_from__lte=end_date).filter(
            effective_to__isnull=True
        )
        | ApprovedLeave.objects.filter(
            employee=employee, effective_from__lte=end_date, effective_to__gte=calculation_start
        )
    )
    remote = list(
        RemoteWorkException.objects.filter(employee=employee, effective_from__lte=end_date).filter(
            effective_to__isnull=True
        )
        | RemoteWorkException.objects.filter(
            employee=employee, effective_from__lte=end_date, effective_to__gte=calculation_start
        )
    )
    assignments = list(
        EmployeeProjectAssignment.objects.filter(
            employee=employee,
            effective_from__lte=end_date,
        )
        .select_related("project__base_location", "employee__base_location")
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=calculation_start))
    )
    employee_locations = list(
        EmployeeBaseLocationAssignment.objects.filter(
            employee=employee,
            effective_from__lte=end_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=calculation_start))
        .select_related("base_location")
    )
    project_ids = {assignment.project_id for assignment in assignments}
    project_locations = list(
        ProjectBaseLocationAssignment.objects.filter(
            project_id__in=project_ids,
            effective_from__lte=end_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=calculation_start))
        .select_related("base_location")
    )
    rules = list(
        ProjectStatusRule.objects.filter(company=company, effective_from__lte=end_date).filter(
            effective_to__isnull=True
        )
        | ProjectStatusRule.objects.filter(
            company=company, effective_from__lte=end_date, effective_to__gte=calculation_start
        )
    )
    records = dict(
        WorkInOfficeRecord.objects.filter(
            employee=employee,
            work_date__range=(start_date, end_date),
            location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        ).values_list("work_date", "review_state")
    )
    rows = list(legacy_rows)
    for current in dates:
        reasons = []
        if current.weekday() >= 5:
            reasons.append("Weekend")
        if current in holidays:
            reasons.append("Public holiday")
        if any(_covers(item, current) for item in leaves):
            reasons.append("Approved leave")
        if any(_covers(item, current) for item in remote):
            reasons.append("Approved remote-work exception")
        assignment = next((item for item in assignments if _covers(item, current)), None)
        status = "benched"
        if assignment:
            employee_location_id = _effective_location_id(
                employee_locations,
                current,
                employee.base_location_id,
            )
            assignment_project_locations = [
                item for item in project_locations if item.project_id == assignment.project_id
            ]
            project_location_id = _effective_location_id(
                assignment_project_locations,
                current,
                assignment.project.base_location_id,
            )
            status = (
                "same_base" if project_location_id == employee_location_id else "different_base"
            )
        rule = next(
            (item for item in rules if item.assignment_status == status and _covers(item, current)),
            None,
        )
        if not reasons and current <= as_of_date and rule is None:
            raise ValidationError(f"No effective policy rule covers {status} on {current}.")
        expected = Decimal("0")
        if not reasons and current <= as_of_date and rule:
            expected = rule.expected_fraction
        rows.append(
            LedgerDay(
                date=current,
                eligible=not reasons,
                reason="; ".join(reasons) or None,
                assignment_status=status,
                rule_version=rule.pk if rule else None,
                expected_fraction=expected,
                approval_credit=Decimal("1")
                if records.get(current) == "approved"
                else Decimal("0"),
                self_submitted_credit=(
                    Decimal("1")
                    if records.get(current)
                    in {"pending", "pending_assignment", "approved", "rejected", "expired_pending"}
                    else Decimal("0")
                ),
            )
        )
    return calculate_ratio(rows)
