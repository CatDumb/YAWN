from datetime import date, datetime, time, timedelta
from decimal import Decimal
from importlib import import_module
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps as django_apps
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership, ManagerAssignment, User
from apps.audit.models import AuditEvent
from apps.work_logs import admin as work_logs_admin
from apps.work_logs.admin import AssignmentAdmin, FiscalPeriodAdmin, WorkInOfficeRecordAdmin
from apps.work_logs.lifecycle import advance_fiscal_period_states
from apps.work_logs.models import (
    ApprovedLeave,
    BaseLocation,
    EmployeeBaseLocationAssignment,
    EmployeeProjectAssignment,
    FiscalPeriod,
    Project,
    ProjectBaseLocationAssignment,
    ProjectStatusRule,
    RemoteWorkException,
    WorkInOfficeRecord,
)
from apps.work_logs.ratio import ratio_ledger


@pytest.fixture
def policy_employee(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    user = User.objects.create_user(email="employee@example.com")
    return CompanyMembership.objects.create(user=user, company=company)


def test_fiscal_period_defaults_cutoff_and_rejects_overlap(policy_employee):
    period = FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="FY26",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        state=FiscalPeriod.State.ACTIVE,
    )
    assert period.reconciliation_cutoff == timezone.make_aware(
        datetime(2027, 1, 14, 23, 59, 59, 999999)
    )
    overlap = FiscalPeriod(
        company=policy_employee.company,
        name="duplicate",
        start_date=date(2026, 12, 1),
        end_date=date(2027, 11, 30),
    )
    with pytest.raises(ValidationError, match="cannot overlap"):
        overlap.full_clean()


@override_settings(TIME_ZONE="UTC")
def test_company_local_cutoff_migration_repairs_only_legacy_defaults(db):
    migration = import_module("apps.work_logs.migrations.0010_repair_company_local_cutoffs")
    company = Company.objects.create(
        name="Timezone Repair Co",
        slug="timezone-repair-co",
        timezone="America/Los_Angeles",
    )
    end_date = date(2026, 6, 30)
    legacy_cutoff = migration.default_cutoff(end_date, "Asia/Ho_Chi_Minh")
    expected_cutoff = migration.default_cutoff(end_date, company.timezone)
    repaired = FiscalPeriod.objects.create(
        company=company,
        name="Legacy default",
        start_date=date(2025, 7, 1),
        end_date=end_date,
        reconciliation_cutoff=legacy_cutoff,
    )
    explicit_end_date = date(2027, 6, 30)
    explicit_cutoff = migration.default_cutoff(explicit_end_date, "Asia/Ho_Chi_Minh") + timedelta(
        hours=1
    )
    explicit = FiscalPeriod.objects.create(
        company=company,
        name="Explicit cutoff",
        start_date=date(2026, 7, 1),
        end_date=explicit_end_date,
        reconciliation_cutoff=explicit_cutoff,
    )

    migration.repair_company_local_cutoffs(django_apps, None)

    repaired.refresh_from_db()
    explicit.refresh_from_db()
    assert repaired.reconciliation_cutoff == expected_cutoff
    assert explicit.reconciliation_cutoff == explicit_cutoff
    event = AuditEvent.objects.get(
        event_type=migration.EVENT_TYPE,
        target_id=str(repaired.pk),
    )
    assert event.metadata["actor_company_id"] == company.pk
    assert datetime.fromisoformat(event.metadata["previous_cutoff"]) == legacy_cutoff
    assert datetime.fromisoformat(event.metadata["new_cutoff"]) == expected_cutoff

    migration.reverse_company_local_cutoffs(django_apps, None)

    repaired.refresh_from_db()
    explicit.refresh_from_db()
    assert repaired.reconciliation_cutoff == legacy_cutoff
    assert explicit.reconciliation_cutoff == explicit_cutoff
    assert not AuditEvent.objects.filter(event_type=migration.EVENT_TYPE).exists()


def test_fiscal_lifecycle_coordinator_persists_and_audits_due_states(policy_employee):
    past = FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="FY25",
        start_date=date(2025, 7, 1),
        end_date=date(2026, 6, 30),
        state=FiscalPeriod.State.ACTIVE,
    )
    current = FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="FY26",
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        state=FiscalPeriod.State.UPCOMING,
    )
    for status in ProjectStatusRule.AssignmentStatus.values:
        ProjectStatusRule.objects.create(
            company=policy_employee.company,
            assignment_status=status,
            effective_from=current.start_date,
            effective_to=current.end_date,
            expected_fraction=Decimal("0.50"),
        )
    at = timezone.make_aware(datetime(2026, 7, 15, 12))

    assert advance_fiscal_period_states(at=at) == 2
    past.refresh_from_db()
    current.refresh_from_db()
    assert past.state == FiscalPeriod.State.RECONCILIATION
    assert current.state == FiscalPeriod.State.ACTIVE
    assert (
        AuditEvent.objects.filter(
            event_type="work_logs.period_state_advanced",
            target_type="work_logs.FiscalPeriod",
        ).count()
        == 2
    )

    assert advance_fiscal_period_states(at=at) == 0
    assert (
        AuditEvent.objects.filter(
            event_type="work_logs.period_state_advanced",
            target_type="work_logs.FiscalPeriod",
        ).count()
        == 2
    )


def test_fiscal_lifecycle_rejects_incomplete_policy_coverage(policy_employee):
    period = FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="FY26",
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        state=FiscalPeriod.State.UPCOMING,
    )
    ProjectStatusRule.objects.create(
        company=policy_employee.company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=period.start_date,
        effective_to=period.end_date,
        expected_fraction=Decimal("0.50"),
    )

    with pytest.raises(ValidationError, match="policy coverage"):
        advance_fiscal_period_states(at=timezone.make_aware(datetime(2026, 7, 15, 12)))

    period.refresh_from_db()
    assert period.state == FiscalPeriod.State.UPCOMING


def test_fiscal_lifecycle_revalidates_an_already_active_period(policy_employee):
    period = FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="FY26",
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        state=FiscalPeriod.State.ACTIVE,
    )

    with pytest.raises(ValidationError, match="policy coverage"):
        advance_fiscal_period_states(at=timezone.make_aware(datetime(2026, 7, 15, 12)))

    period.refresh_from_db()
    assert period.state == FiscalPeriod.State.ACTIVE


def test_manager_can_be_reassigned_to_same_employee_in_disjoint_periods(policy_employee):
    manager_user = User.objects.create_user(email="manager@example.com")
    manager = CompanyMembership.objects.create(
        user=manager_user,
        company=policy_employee.company,
        role=CompanyMembership.Role.MANAGER,
    )
    original = ManagerAssignment.objects.create(
        manager=manager,
        employee=policy_employee,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 3, 31),
    )

    later = ManagerAssignment.objects.create(
        manager=manager,
        employee=policy_employee,
        effective_from=date(2026, 7, 1),
    )

    assert later.effective_from == date(2026, 7, 1)
    original.effective_from = date(2026, 2, 1)
    with pytest.raises(ValidationError, match="assignments are immutable"):
        original.save()
    original.refresh_from_db()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        original.delete()


def test_manager_history_migration_only_rejects_overlapping_active_rows():
    migration = import_module("apps.accounts.migrations.0009_manager_assignment_history_integrity")
    rows = [
        (1, date(2026, 1, 1), date(2026, 3, 31)),
        (1, date(2026, 7, 1), None),
        (2, date(2026, 1, 1), None),
        (2, date(2026, 7, 1), None),
    ]

    assert migration.ambiguous_employee_ids(rows) == [2]


def test_legacy_fiscal_cutoff_migration_preserves_end_of_day():
    migration = import_module("apps.work_logs.migrations.0004_remediation_foundations")

    normalized = migration.normalize_legacy_cutoff(datetime(2027, 1, 14))

    assert normalized.time() == time.max


def test_ratio_ledger_explains_exclusions_and_rounds_once(policy_employee):
    monday = date(2026, 7, 20)
    ProjectStatusRule.objects.create(
        company=policy_employee.company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=date(2026, 1, 1),
        expected_fraction=Decimal("0.50"),
    )
    ApprovedLeave.objects.create(
        employee=policy_employee,
        effective_from=monday + timedelta(days=1),
        effective_to=monday + timedelta(days=1),
        reason="Approved leave",
        approved_at=timezone.now(),
    )
    RemoteWorkException.objects.create(
        employee=policy_employee,
        effective_from=monday + timedelta(days=2),
        effective_to=monday + timedelta(days=2),
        reason="Approved exception",
        approved_at=timezone.now(),
    )
    WorkInOfficeRecord.objects.create(
        employee=policy_employee,
        work_date=monday,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
    )
    result = ratio_ledger(
        employee=policy_employee,
        start_date=monday,
        end_date=monday + timedelta(days=4),
        as_of_date=monday + timedelta(days=4),
    )
    assert len(result["days"]) == 5
    assert result["expected_fraction_sum"] == Decimal("1.50")
    assert result["days"][1].reason == "Approved leave"
    assert result["days"][2].reason == "Approved remote-work exception"
    assert result["days"][0].approval_credit == Decimal("1")


def test_ratio_ledger_uses_effective_dated_base_locations(policy_employee):
    day = date(2026, 7, 20)
    headquarters = BaseLocation.objects.create(
        company=policy_employee.company, name="Headquarters", code="hq"
    )
    remote_hub = BaseLocation.objects.create(
        company=policy_employee.company, name="Remote hub", code="remote"
    )
    policy_employee.base_location = remote_hub
    policy_employee.save(update_fields=["base_location"])
    project = Project.objects.create(
        company=policy_employee.company,
        name="Core",
        code="core",
        base_location=headquarters,
    )
    EmployeeBaseLocationAssignment.objects.create(
        employee=policy_employee,
        base_location=headquarters,
        effective_from=date(2026, 1, 1),
        effective_to=day,
    )
    EmployeeBaseLocationAssignment.objects.create(
        employee=policy_employee,
        base_location=remote_hub,
        effective_from=day + timedelta(days=1),
    )
    ProjectBaseLocationAssignment.objects.create(
        project=project,
        base_location=headquarters,
        effective_from=date(2026, 1, 1),
    )
    EmployeeProjectAssignment.objects.create(
        employee=policy_employee,
        project=project,
        effective_from=date(2026, 1, 1),
    )
    ProjectStatusRule.objects.create(
        company=policy_employee.company,
        assignment_status=ProjectStatusRule.AssignmentStatus.SAME_BASE,
        effective_from=date(2026, 1, 1),
        expected_fraction=Decimal("0.50"),
    )
    ProjectStatusRule.objects.create(
        company=policy_employee.company,
        assignment_status=ProjectStatusRule.AssignmentStatus.DIFFERENT_BASE,
        effective_from=date(2026, 1, 1),
        expected_fraction=Decimal("1.00"),
    )

    result = ratio_ledger(
        employee=policy_employee,
        start_date=day,
        end_date=day,
        as_of_date=day,
    )

    assert result["days"][0].assignment_status == "same_base"
    assert result["expected_fraction_sum"] == Decimal("0.50")


def test_profile_resolves_a_future_location_when_it_becomes_effective(
    client, monkeypatch, policy_employee
):
    today = timezone.localdate()
    effective_day = today + timedelta(days=30)
    old_location = BaseLocation.objects.create(
        company=policy_employee.company, name="Old office", code="old"
    )
    new_location = BaseLocation.objects.create(
        company=policy_employee.company, name="New office", code="new"
    )
    policy_employee.base_location = old_location
    policy_employee.save(update_fields=["base_location"])
    EmployeeBaseLocationAssignment.objects.create(
        employee=policy_employee,
        base_location=new_location,
        effective_from=effective_day,
    )
    monkeypatch.setattr(
        "apps.work_logs.profile_views.company_today", lambda _company: effective_day
    )
    client.force_login(policy_employee.user)

    response = client.get("/api/v1/profile/")

    assert response.status_code == 200
    assert response.json()["base_location"] == "New office"
    policy_employee.refresh_from_db()
    assert policy_employee.base_location == old_location

    at = timezone.make_aware(datetime.combine(effective_day, time(12)))
    assert advance_fiscal_period_states(at=at) == 0
    policy_employee.refresh_from_db()
    assert policy_employee.base_location == new_location


def test_started_location_history_is_append_only(policy_employee):
    original = BaseLocation.objects.create(
        company=policy_employee.company, name="Original", code="original"
    )
    replacement = BaseLocation.objects.create(
        company=policy_employee.company, name="Replacement", code="replacement"
    )
    version = EmployeeBaseLocationAssignment.objects.create(
        employee=policy_employee,
        base_location=original,
        effective_from=timezone.localdate() - timedelta(days=1),
        effective_to=timezone.localdate() + timedelta(days=7),
    )
    policy_employee.refresh_from_db()
    assert policy_employee.base_location == original

    version.base_location = replacement
    with pytest.raises(ValidationError, match="versions are immutable"):
        version.save()
    version.refresh_from_db()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        version.delete()


def test_active_period_future_policy_coverage_cannot_be_deleted(policy_employee):
    today = timezone.localdate()
    period = FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="Current",
        start_date=today,
        end_date=today + timedelta(days=30),
        state=FiscalPeriod.State.ACTIVE,
    )
    rule = ProjectStatusRule.objects.create(
        company=policy_employee.company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today + timedelta(days=1),
        effective_to=period.end_date,
        expected_fraction=Decimal("0.50"),
    )

    with pytest.raises(ValidationError, match="cannot be deleted"):
        rule.delete()


def test_zero_expected_days_returns_na_and_combines_exclusion_reasons(policy_employee):
    day = date(2026, 7, 20)
    ApprovedLeave.objects.create(
        employee=policy_employee,
        effective_from=day,
        effective_to=day,
        reason="Leave",
        approved_at=timezone.now(),
    )
    RemoteWorkException.objects.create(
        employee=policy_employee,
        effective_from=day,
        effective_to=day,
        reason="Exception",
        approved_at=timezone.now(),
    )
    result = ratio_ledger(employee=policy_employee, start_date=day, end_date=day, as_of_date=day)
    assert result["ratio"] is None
    assert result["ratio_display"] == "N/A"
    assert result["days"][0].reason == "Approved leave; Approved remote-work exception"


def test_ratio_rejects_an_effective_policy_coverage_gap(policy_employee):
    with pytest.raises(ValidationError, match="No effective policy rule covers benched"):
        ratio_ledger(
            employee=policy_employee,
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 20),
            as_of_date=date(2026, 7, 20),
        )


def test_ratio_ledger_query_count_does_not_grow_per_calendar_day(policy_employee):
    start = date(2026, 7, 1)
    ProjectStatusRule.objects.create(
        company=policy_employee.company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=date(2026, 1, 1),
        expected_fraction=Decimal("0.50"),
    )

    def query_count_for(day_count):
        with CaptureQueriesContext(connection) as queries:
            result = ratio_ledger(
                employee=policy_employee,
                start_date=start,
                end_date=start + timedelta(days=day_count - 1),
                as_of_date=start + timedelta(days=day_count - 1),
            )
        assert len(result["days"]) == day_count
        return len(queries)

    assert query_count_for(31) == query_count_for(7)


def test_used_assignment_and_rule_are_immutable(policy_employee):
    location = BaseLocation.objects.create(company=policy_employee.company, name="HQ", code="hq")
    policy_employee.base_location = location
    policy_employee.save(update_fields=["base_location"])
    project = Project.objects.create(
        company=policy_employee.company, name="Core", code="core", base_location=location
    )
    assignment = EmployeeProjectAssignment.objects.create(
        employee=policy_employee, project=project, effective_from=date(2026, 1, 1)
    )
    rule = ProjectStatusRule.objects.create(
        company=policy_employee.company,
        assignment_status=ProjectStatusRule.AssignmentStatus.SAME_BASE,
        effective_from=date(2026, 1, 1),
        expected_fraction=Decimal("1.00"),
    )
    WorkInOfficeRecord.objects.create(
        employee=policy_employee,
        work_date=date(2026, 7, 20),
        assignment_snapshot={"id": assignment.pk, "status": "same_base"},
        policy_snapshot={"rule": {"id": rule.pk, "fraction": "1.00"}},
    )
    assignment.effective_to = date(2026, 12, 31)
    with pytest.raises(ValidationError, match="cannot be changed"):
        assignment.full_clean()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        rule.delete()


def test_work_log_admin_is_scoped_to_hr_company(policy_employee):
    hr = User.objects.create_user(email="hr@example.com", is_staff=True)
    CompanyMembership.objects.create(
        user=hr,
        company=policy_employee.company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    request = RequestFactory().get("/admin/work_logs/fiscalperiod/")
    request.user = hr
    site_admin = FiscalPeriodAdmin(FiscalPeriod, admin.site)
    assert site_admin.has_module_permission(request)
    assert not site_admin.has_view_permission(
        request,
        FiscalPeriod(company=Company.objects.create(name="Other", slug="other")),
    )


def test_employee_assignment_admin_registration_is_shared():
    assert isinstance(admin.site._registry[EmployeeProjectAssignment], AssignmentAdmin)
    assert isinstance(admin.site._registry[EmployeeBaseLocationAssignment], AssignmentAdmin)
    assert type(admin.site._registry[ProjectBaseLocationAssignment]) is not AssignmentAdmin


def test_final_period_admin_change_post_cannot_bypass_audited_reopen(
    policy_employee,
    client,
):
    superuser = User.objects.create_superuser(
        email="final-period-admin@example.com",
        password="secret",
    )
    period = FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="Final FY26",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        reconciliation_cutoff=timezone.make_aware(
            datetime(2027, 1, 14, 23, 59, 59, 999999)
        ),
        state=FiscalPeriod.State.FINAL,
    )
    original = {
        "company_id": period.company_id,
        "start_date": period.start_date,
        "end_date": period.end_date,
        "reconciliation_cutoff": period.reconciliation_cutoff,
        "state": period.state,
    }
    other_company = Company.objects.create(name="Other Final Co", slug="other-final-co")
    client.force_login(superuser)

    response = client.post(
        reverse("admin:work_logs_fiscalperiod_change", args=[period.pk]),
        {
            "company": other_company.pk,
            "name": period.name,
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "reconciliation_cutoff_0": "2026-01-14",
            "reconciliation_cutoff_1": "23:59:59",
            "state": FiscalPeriod.State.RECONCILIATION,
            "_save": "Save",
        },
    )

    assert response.status_code == 302
    period.refresh_from_db()
    assert {
        "company_id": period.company_id,
        "start_date": period.start_date,
        "end_date": period.end_date,
        "reconciliation_cutoff": period.reconciliation_cutoff,
        "state": period.state,
    } == original
    assert not AuditEvent.objects.filter(
        event_type="work_logs.period_reopened",
        target_id=str(period.pk),
    ).exists()


def test_final_period_model_rejects_boundary_and_state_mutation(policy_employee):
    period = FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="Immutable FY26",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        reconciliation_cutoff=timezone.make_aware(
            datetime(2027, 1, 14, 23, 59, 59, 999999)
        ),
        state=FiscalPeriod.State.FINAL,
    )
    other_company = Company.objects.create(name="Other Immutable Co", slug="other-immutable-co")
    attempts = (
        ("company", other_company),
        ("start_date", date(2025, 1, 1)),
        ("end_date", date(2027, 12, 31)),
        (
            "reconciliation_cutoff",
            timezone.make_aware(datetime(2027, 1, 15, 23, 59, 59, 999999)),
        ),
        ("state", FiscalPeriod.State.RECONCILIATION),
    )

    for field, value in attempts:
        candidate = FiscalPeriod.objects.get(pk=period.pk)
        setattr(candidate, field, value)
        with pytest.raises(ValidationError, match="Final fiscal period"):
            candidate.save()


def test_policy_admin_delete_is_audited(policy_employee):
    hr = User.objects.create_user(email="delete-auditor@example.com", is_staff=True)
    CompanyMembership.objects.create(
        user=hr,
        company=policy_employee.company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    rule = ProjectStatusRule.objects.create(
        company=policy_employee.company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=timezone.localdate() + timedelta(days=30),
        expected_fraction=Decimal("0.50"),
    )
    request = RequestFactory().post(f"/admin/work_logs/projectstatusrule/{rule.pk}/delete/")
    request.user = hr
    site_admin = admin.site._registry[ProjectStatusRule]
    rule_id = rule.pk

    site_admin.delete_model(request, rule)

    assert not ProjectStatusRule.objects.filter(pk=rule_id).exists()
    assert AuditEvent.objects.filter(
        actor=hr,
        event_type="work_logs.admin_deleted",
        target_type="work_logs.ProjectStatusRule",
        target_id=str(rule_id),
    ).exists()


def test_hr_can_extend_rejected_correction_without_passing_fiscal_cutoff(policy_employee):
    hr = User.objects.create_user(email="hr@example.com", is_staff=True)
    CompanyMembership.objects.create(
        user=hr,
        company=policy_employee.company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    period = FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="FY26",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        reconciliation_cutoff=timezone.make_aware(datetime(2027, 1, 14, 23, 59, 59, 999999)),
        state=FiscalPeriod.State.RECONCILIATION,
    )
    record = WorkInOfficeRecord.objects.create(
        employee=policy_employee,
        work_date=date(2026, 12, 31),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.REJECTED,
        correction_deadline=timezone.make_aware(datetime(2027, 1, 13, 23, 59)),
    )
    request = RequestFactory().post(
        "/admin/work_logs/workinofficerecord/",
        {
            "action": "extend_rejected_correction",
            "apply": "1",
            "_selected_action": str(record.pk),
            "audit_reason": "Employee needs more time",
        },
    )
    request.user = hr
    site_admin = WorkInOfficeRecordAdmin(WorkInOfficeRecord, admin.site)
    site_admin.extend_rejected_correction(request, WorkInOfficeRecord.objects.filter(pk=record.pk))
    record.refresh_from_db()
    assert record.correction_deadline.date() == period.reconciliation_cutoff.date()
    assert record.correction_deadline <= period.reconciliation_cutoff
    event = AuditEvent.objects.get(
        event_type="work_logs.rejection_correction_extended", target_id=str(record.pk)
    )
    assert event.metadata["actor_role"] == CompanyMembership.Role.HR_ADMIN
    assert event.metadata["actor_company_id"] == policy_employee.company_id
    assert event.metadata["reason"] == "Employee needs more time"
    assert event.metadata["revision"] == record.version
    assert event.metadata["from_state"] == WorkInOfficeRecord.ReviewState.REJECTED
    assert event.metadata["to_state"] == WorkInOfficeRecord.ReviewState.REJECTED


def test_correction_extension_rejects_hr_revoked_after_fiscal_lock(
    policy_employee,
    monkeypatch,
):
    hr = User.objects.create_user(email="revoked-extension-hr@example.com", is_staff=True)
    hr_membership = CompanyMembership.objects.create(
        user=hr,
        company=policy_employee.company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    today = timezone.localdate()
    FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="Revocation period",
        start_date=today - timedelta(days=30),
        end_date=today,
        reconciliation_cutoff=timezone.now() + timedelta(days=14),
        state=FiscalPeriod.State.ACTIVE,
    )
    original_deadline = timezone.now() + timedelta(hours=1)
    record = WorkInOfficeRecord.objects.create(
        employee=policy_employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.REJECTED,
        correction_deadline=original_deadline,
    )
    request = RequestFactory().post(
        "/admin/work_logs/workinofficerecord/",
        {
            "action": "extend_rejected_correction",
            "apply": "1",
            "_selected_action": str(record.pk),
            "audit_reason": "Employee needs more time",
        },
    )
    request.user = hr
    original_lock_wio_period = work_logs_admin.lock_wio_period

    def revoke_after_fiscal_lock(*, company_id, work_date):
        period = original_lock_wio_period(company_id=company_id, work_date=work_date)
        CompanyMembership.objects.filter(pk=hr_membership.pk).update(
            role=CompanyMembership.Role.EMPLOYEE
        )
        return period

    monkeypatch.setattr(work_logs_admin, "lock_wio_period", revoke_after_fiscal_lock)
    site_admin = WorkInOfficeRecordAdmin(WorkInOfficeRecord, admin.site)
    monkeypatch.setattr(site_admin, "message_user", lambda *args, **kwargs: None)

    site_admin.extend_rejected_correction(
        request,
        WorkInOfficeRecord.objects.filter(pk=record.pk),
    )

    record.refresh_from_db()
    assert record.correction_deadline == original_deadline
    assert not AuditEvent.objects.filter(
        event_type="work_logs.rejection_correction_extended",
        target_id=str(record.pk),
    ).exists()


def test_reasoned_reopen_enables_post_cutoff_correction_extension(policy_employee):
    hr = User.objects.create_user(email="reopen-hr@example.com", is_staff=True)
    CompanyMembership.objects.create(
        user=hr,
        company=policy_employee.company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    now = timezone.now()
    end_day = timezone.localdate() - timedelta(days=2)
    period = FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="Closed period",
        start_date=end_day - timedelta(days=30),
        end_date=end_day,
        reconciliation_cutoff=now - timedelta(days=1),
        state=FiscalPeriod.State.FINAL,
    )
    record = WorkInOfficeRecord.objects.create(
        employee=policy_employee,
        work_date=end_day,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.REJECTED,
        correction_deadline=now - timedelta(days=2),
    )
    period_admin = FiscalPeriodAdmin(FiscalPeriod, admin.site)
    period_queryset = FiscalPeriod.objects.filter(pk=period.pk)
    confirmation_request = RequestFactory().post(
        "/admin/work_logs/fiscalperiod/",
        {
            "action": "reopen_for_correction",
            "_selected_action": str(period.pk),
        },
    )
    confirmation_request.user = hr

    confirmation = period_admin.reopen_for_correction(
        confirmation_request,
        period_queryset,
    )

    assert confirmation.template_name == "admin/work_logs/wio_action_confirmation.html"
    period.refresh_from_db()
    assert period.state == FiscalPeriod.State.FINAL

    reopen_request = RequestFactory().post(
        "/admin/work_logs/fiscalperiod/",
        {
            "action": "reopen_for_correction",
            "apply": "1",
            "_selected_action": str(period.pk),
            "audit_reason": "Correct verified attendance evidence",
        },
    )
    reopen_request.user = hr
    period_admin.reopen_for_correction(reopen_request, period_queryset)

    period.refresh_from_db()
    assert period.state == FiscalPeriod.State.RECONCILIATION
    event = AuditEvent.objects.get(
        event_type="work_logs.period_reopened",
        target_id=str(period.pk),
    )
    assert event.metadata["reason"] == "Correct verified attendance evidence"
    assert event.metadata["from_state"] == FiscalPeriod.State.FINAL
    assert event.metadata["to_state"] == FiscalPeriod.State.RECONCILIATION

    extension_request = RequestFactory().post(
        "/admin/work_logs/workinofficerecord/",
        {
            "action": "extend_rejected_correction",
            "apply": "1",
            "_selected_action": str(record.pk),
            "audit_reason": "Give employee one correction day",
        },
    )
    extension_request.user = hr
    WorkInOfficeRecordAdmin(WorkInOfficeRecord, admin.site).extend_rejected_correction(
        extension_request,
        WorkInOfficeRecord.objects.filter(pk=record.pk),
    )

    record.refresh_from_db()
    assert record.correction_deadline > now
    assert record.correction_deadline > period.reconciliation_cutoff


def test_default_fiscal_cutoff_uses_company_timezone(db):
    company = Company.objects.create(
        name="California",
        slug="california",
        timezone="America/Los_Angeles",
    )
    period = FiscalPeriod.objects.create(
        company=company,
        name="Local cutoff",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    local_cutoff = period.reconciliation_cutoff.astimezone(ZoneInfo("America/Los_Angeles"))
    assert local_cutoff.date() == date(2026, 2, 14)
    assert local_cutoff.time() == time.max


def test_wio_admin_actions_collect_reason_and_reverse_approval(policy_employee):
    hr = User.objects.create_user(email="reverse-hr@example.com", is_staff=True)
    CompanyMembership.objects.create(
        user=hr,
        company=policy_employee.company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    manager = CompanyMembership.objects.create(
        user=User.objects.create_user(email="reverse-manager@example.com"),
        company=policy_employee.company,
        role=CompanyMembership.Role.MANAGER,
    )
    ManagerAssignment.objects.create(
        manager=manager,
        employee=policy_employee,
        effective_from=date(2026, 1, 1),
    )
    FiscalPeriod.objects.create(
        company=policy_employee.company,
        name="Reverse period",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 7, 29),
        reconciliation_cutoff=timezone.make_aware(datetime(2026, 8, 1, 23, 59, 59)),
        state=FiscalPeriod.State.RECONCILIATION,
    )
    record = WorkInOfficeRecord.objects.create(
        employee=policy_employee,
        work_date=date(2026, 7, 29),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
        approved_at=timezone.now() - timedelta(minutes=5),
        approved_by_snapshot={"membership_id": manager.pk, "role": manager.role},
        approval_owner_snapshot={
            "membership_id": manager.pk,
            "assigned_by_membership_id": 999,
            "assigned_reason": "Prior audited reassignment",
        },
    )
    site_admin = WorkInOfficeRecordAdmin(WorkInOfficeRecord, admin.site)
    queryset = WorkInOfficeRecord.objects.filter(pk=record.pk)
    confirmation_request = RequestFactory().post(
        "/admin/work_logs/workinofficerecord/",
        {
            "action": "reverse_approved_records",
            "_selected_action": str(record.pk),
        },
    )
    confirmation_request.user = hr

    confirmation = site_admin.reverse_approved_records(confirmation_request, queryset)

    assert confirmation.template_name == "admin/work_logs/wio_action_confirmation.html"

    request = RequestFactory().post(
        "/admin/work_logs/workinofficerecord/",
        {
            "action": "reverse_approved_records",
            "apply": "1",
            "_selected_action": str(record.pk),
            "audit_reason": "Approval evidence was invalid",
        },
    )
    request.user = hr
    site_admin.reverse_approved_records(request, queryset)

    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING
    assert record.approval_method is None
    assert record.approved_at is None
    assert record.approved_by_snapshot == {}
    assert record.approval_owner_snapshot == {
        "membership_id": manager.pk,
        "assigned_by_membership_id": 999,
        "assigned_reason": "Prior audited reassignment",
    }
    event = AuditEvent.objects.get(
        event_type="work_logs.approval_reversed_by_admin",
        target_id=str(record.pk),
    )
    assert event.metadata["reason"] == "Approval evidence was invalid"
    assert event.metadata["from_state"] == WorkInOfficeRecord.ReviewState.APPROVED
    assert event.metadata["to_state"] == WorkInOfficeRecord.ReviewState.PENDING
