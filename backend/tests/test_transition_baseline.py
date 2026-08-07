from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Company, CompanyMembership, User
from apps.audit.models import AuditEvent
from apps.work_logs.models import FiscalPeriod, ProjectStatusRule, WorkInOfficeRecord
from apps.work_logs.reports import report_for
from apps.work_logs.services import (
    save_record,
    save_transition_baseline,
    transition_baseline_state,
)


@pytest.fixture
def policy_employee(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    user = User.objects.create_user(email="employee@example.com")
    return CompanyMembership.objects.create(user=user, company=company)


@pytest.fixture
def transition_period(policy_employee):
    return FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="FY26",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        state=FiscalPeriod.State.ACTIVE,
    )


def create_baseline(employee):
    return save_transition_baseline(
        employee=employee,
        cutoff_month=date(2026, 6, 1),
        target_days=Decimal("10.50"),
        achieved_days=Decimal("8.25"),
        actor=employee.user,
    )


def test_employee_entered_transition_baseline_is_not_approved_credit(
    policy_employee, transition_period
):
    save_transition_baseline(
        employee=policy_employee,
        cutoff_month=date(2026, 6, 1),
        target_days=Decimal("10.00"),
        achieved_days=Decimal("10.00"),
        actor=policy_employee.user,
    )

    report = report_for(
        employee=policy_employee,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 30),
    )

    assert report["approved_days"] == Decimal("0")
    assert report["self_submitted_days"] == Decimal("10.00")
    assert report["ledger"][0]["approval_credit"] == "0"
    assert report["ledger"][0]["self_submitted_credit"] == "10.00"


def test_transition_baseline_carries_into_local_ratio(policy_employee, transition_period):
    baseline = create_baseline(policy_employee)
    ProjectStatusRule.objects.create(
        company=policy_employee.company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=date(2026, 1, 1),
        expected_fraction=Decimal("0.50"),
    )
    WorkInOfficeRecord.objects.create(
        employee=policy_employee,
        work_date=date(2026, 7, 1),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
    )

    report = report_for(
        employee=policy_employee,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 3),
    )

    assert baseline.cutoff_date == date(2026, 6, 30)
    assert report["approved_days"] == Decimal("1")
    assert report["self_submitted_days"] == Decimal("9.25")
    assert report["expected_fraction_sum"] == Decimal("12.00")
    assert report["ratio_display"] == "8.34%"
    assert report["self_submitted_ratio_display"] == "77.09%"
    assert report["baseline_included"] is True
    assert report["ledger"][0]["source"] == "legacy_carry_forward"
    assert AuditEvent.objects.filter(event_type="work_logs.transition_baseline_created").exists()


def test_transition_baseline_blocks_legacy_dates_and_pre_cutoff_report(
    policy_employee, transition_period
):
    create_baseline(policy_employee)
    policy_employee.role = CompanyMembership.Role.HR_ADMIN
    policy_employee.save(update_fields=["role"])

    with pytest.raises(ValidationError, match="legacy transition balance"):
        save_record(
            employee=policy_employee,
            work_date=date(2026, 6, 30),
            location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            actor=policy_employee.user,
            override_reason="legacy correction",
        )
    with pytest.raises(ValidationError, match="Legacy daily history"):
        report_for(
            employee=policy_employee,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 29),
        )


def test_transition_baseline_api_requires_version_for_updates(
    client, policy_employee, transition_period
):
    client.force_login(policy_employee.user)
    response = client.post(
        "/api/v1/transition-baseline/",
        data={
            "cutoff_month": "2026-06",
            "target_days": "10.50",
            "achieved_days": "8.25",
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["baseline"]["ratio_display"] == "78.58%"

    update = client.put(
        "/api/v1/transition-baseline/",
        data={
            "cutoff_month": "2026-06",
            "target_days": "10.50",
            "achieved_days": "8.25",
        },
        content_type="application/json",
    )
    assert update.status_code == 409


def test_transition_baseline_allows_post_cutoff_owned_wio_and_locks(
    client, policy_employee, transition_period
):
    policy_employee.role = CompanyMembership.Role.MANAGER
    policy_employee.save(update_fields=["role"])
    WorkInOfficeRecord.objects.create(
        employee=policy_employee,
        work_date=date(2026, 7, 2),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
    )
    WorkInOfficeRecord.objects.create(
        employee=policy_employee,
        work_date=date(2026, 7, 3),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
    )

    state = transition_baseline_state(policy_employee)
    assert state["eligible"] is True
    assert state["latest_cutoff_month"] == "2026-06"

    client.force_login(policy_employee.user)
    response = client.post(
        "/api/v1/transition-baseline/",
        data={
            "cutoff_month": "2026-06",
            "target_days": "10.50",
            "achieved_days": "8.25",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["baseline"]["can_edit"] is False
    assert response.json()["lock_reason"] == "A post-cutoff WIO record exists."
    assert WorkInOfficeRecord.objects.filter(employee=policy_employee).count() == 2


def test_transition_baseline_rejects_owned_wio_on_or_before_cutoff(
    policy_employee, transition_period
):
    WorkInOfficeRecord.objects.create(
        employee=policy_employee,
        work_date=date(2026, 6, 30),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
    )

    with pytest.raises(ValidationError, match="must precede your earliest"):
        create_baseline(policy_employee)


def test_transition_baseline_fails_closed_for_ambiguous_legacy_periods(
    policy_employee, transition_period
):
    FiscalPeriod.objects.bulk_create(
        [
            FiscalPeriod(
                company=policy_employee.company,
                name="Legacy overlap",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 7, 31),
                reconciliation_cutoff=transition_period.reconciliation_cutoff,
            )
        ]
    )

    with pytest.raises(ValidationError, match="exactly one fiscal period"):
        create_baseline(policy_employee)
