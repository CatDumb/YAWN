from datetime import UTC, date, datetime, timedelta
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import QuerySet
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership, ManagerAssignment, User
from apps.audit.models import AuditEvent
from apps.work_logs import services as work_log_services
from apps.work_logs.admin import WorkInOfficeRecordAdmin, WorkInOfficeRecordAdminForm
from apps.work_logs.approvals import assign_pending_record
from apps.work_logs.models import CompanyHoliday, FiscalPeriod, WorkInOfficeRecord
from apps.work_logs.services import (
    company_date,
    reverse_approved_record,
    save_record,
    undo_self_approval,
)


@pytest.fixture
def employee_client(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    user = User.objects.create_user(email="employee@example.com")
    membership = CompanyMembership.objects.create(user=user, company=company)
    client.force_login(user)
    return client, membership


def create_payload(work_date, **overrides):
    return {"work_date": str(work_date), **overrides}


def older_weekday():
    work_date = timezone.localdate() - timedelta(days=7)
    while work_date.weekday() >= 5:
        work_date -= timedelta(days=1)
    return work_date


def test_explicit_draft_reserves_date_and_can_be_deleted(employee_client):
    client, membership = employee_client
    today = timezone.localdate()
    response = client.post(
        "/api/v1/work-in-office/",
        create_payload(today, save_as_draft=True),
        content_type="application/json",
    )
    assert response.status_code == 201
    record = WorkInOfficeRecord.objects.get(employee=membership, work_date=today)
    assert record.review_state == WorkInOfficeRecord.ReviewState.DRAFT
    assert (
        client.delete(f"/api/v1/work-in-office/{record.pk}/?version={record.version}").status_code
        == 204
    )
    assert not WorkInOfficeRecord.objects.filter(pk=record.pk).exists()
    assert AuditEvent.objects.filter(
        event_type="work_logs.record_draft_deleted", target_id=str(record.pk)
    ).exists()


def test_blank_submission_requires_explicit_draft_intent(employee_client):
    client, membership = employee_client

    response = client.post(
        "/api/v1/work-in-office/",
        create_payload(timezone.localdate()),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not WorkInOfficeRecord.objects.filter(employee=membership).exists()


def test_office_and_remote_submission_follow_review_contract(employee_client):
    client, membership = employee_client
    today = timezone.localdate()
    office = client.post(
        "/api/v1/work-in-office/",
        create_payload(today, location_choice="in_office", note="Client workshop"),
        content_type="application/json",
    )
    assert office.status_code == 201
    office_record = WorkInOfficeRecord.objects.get(employee=membership, work_date=today)
    assert office_record.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert AuditEvent.objects.filter(target_id=str(office_record.pk)).exists()

    remote = client.post(
        "/api/v1/work-in-office/",
        create_payload(today - timedelta(days=1), location_choice="not_in_office", note=""),
        content_type="application/json",
    )
    assert remote.status_code == 201
    assert remote.json()["review_state"] == WorkInOfficeRecord.ReviewState.NOT_REQUIRED


def test_record_rejects_future_and_duplicate_dates(employee_client):
    client, _ = employee_client
    today = timezone.localdate()
    future = client.post(
        "/api/v1/work-in-office/",
        create_payload(today + timedelta(days=1), location_choice="not_in_office"),
        content_type="application/json",
    )
    assert future.status_code == 400
    first = client.post(
        "/api/v1/work-in-office/",
        create_payload(today, location_choice="not_in_office"),
        content_type="application/json",
    )
    duplicate = client.post(
        "/api/v1/work-in-office/",
        create_payload(today, location_choice="not_in_office"),
        content_type="application/json",
    )
    assert first.status_code == 201
    assert duplicate.status_code == 409


def test_personal_record_api_never_exposes_another_employee(employee_client):
    client, membership = employee_client
    other_user = User.objects.create_user(email="other@example.com")
    other_membership = CompanyMembership.objects.create(user=other_user, company=membership.company)
    record = WorkInOfficeRecord.objects.create(
        employee=other_membership, work_date=timezone.localdate()
    )
    assert client.get(f"/api/v1/work-in-office/{record.pk}/").status_code == 404


def test_update_keeps_reserved_work_date(employee_client):
    client, membership = employee_client
    today = timezone.localdate()
    created = client.post(
        "/api/v1/work-in-office/",
        create_payload(today, save_as_draft=True),
        content_type="application/json",
    ).json()
    updated = client.put(
        f"/api/v1/work-in-office/{created['id']}/",
        create_payload(
            today + timedelta(days=1),
            location_choice="not_in_office",
            note="",
            version=created["version"],
        ),
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["work_date"] == str(today)
    assert WorkInOfficeRecord.objects.filter(employee=membership).count() == 1


def test_update_rejects_deleted_or_replaced_record_identity(employee_client):
    _, membership = employee_client
    work_date = timezone.localdate()
    original = WorkInOfficeRecord.objects.create(
        employee=membership,
        work_date=work_date,
        review_state=WorkInOfficeRecord.ReviewState.DRAFT,
    )
    original_id = original.pk
    original.delete()
    replacement = WorkInOfficeRecord.objects.create(
        employee=membership,
        work_date=work_date,
        review_state=WorkInOfficeRecord.ReviewState.DRAFT,
    )

    with pytest.raises(RuntimeError, match="stale"):
        save_record(
            employee=membership,
            work_date=work_date,
            location_choice=WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
            version=1,
            expected_record_id=original_id,
            actor=membership.user,
        )

    replacement.refresh_from_db()
    assert replacement.review_state == WorkInOfficeRecord.ReviewState.DRAFT
    assert replacement.location_choice is None


def test_save_rejects_membership_company_drift_after_period_lock(
    employee_client,
    monkeypatch,
):
    _, employee = employee_client
    original_company_id = employee.company_id
    other_company = Company.objects.create(
        name="Drifted Company",
        slug="drifted-company",
        is_active=False,
    )
    original_lock_wio_period = work_log_services.lock_wio_period

    def drift_company_after_period_lock(*, company_id, work_date):
        period = original_lock_wio_period(company_id=company_id, work_date=work_date)
        CompanyMembership.objects.filter(pk=employee.pk).update(company=other_company)
        return period

    monkeypatch.setattr(
        work_log_services,
        "lock_wio_period",
        drift_company_after_period_lock,
    )

    with pytest.raises(RuntimeError, match="stale"):
        save_record(
            employee=employee,
            work_date=timezone.localdate(),
            save_as_draft=True,
            actor=employee.user,
        )

    employee.refresh_from_db()
    assert employee.company_id == original_company_id
    assert not WorkInOfficeRecord.objects.filter(employee=employee).exists()


def test_save_rejects_membership_user_drift_after_period_lock(
    employee_client,
    monkeypatch,
):
    _, employee = employee_client
    original_user_id = employee.user_id
    replacement_user = User.objects.create_user(email="drifted-user@example.com")
    original_lock_wio_period = work_log_services.lock_wio_period

    def drift_user_after_period_lock(*, company_id, work_date):
        period = original_lock_wio_period(company_id=company_id, work_date=work_date)
        CompanyMembership.objects.filter(pk=employee.pk).update(user=replacement_user)
        return period

    monkeypatch.setattr(
        work_log_services,
        "lock_wio_period",
        drift_user_after_period_lock,
    )

    with pytest.raises(RuntimeError, match="stale"):
        save_record(
            employee=employee,
            work_date=timezone.localdate(),
            save_as_draft=True,
            actor=employee.user,
        )

    employee.refresh_from_db()
    assert employee.user_id == original_user_id
    assert not WorkInOfficeRecord.objects.filter(employee=employee).exists()


def test_save_rejects_membership_deactivation_after_period_lock(
    employee_client,
    monkeypatch,
):
    _, employee = employee_client
    original_lock_wio_period = work_log_services.lock_wio_period

    def deactivate_after_period_lock(*, company_id, work_date):
        period = original_lock_wio_period(company_id=company_id, work_date=work_date)
        CompanyMembership.objects.filter(pk=employee.pk).update(is_active=False)
        return period

    monkeypatch.setattr(
        work_log_services,
        "lock_wio_period",
        deactivate_after_period_lock,
    )

    with pytest.raises(RuntimeError, match="stale"):
        save_record(
            employee=employee,
            work_date=timezone.localdate(),
            save_as_draft=True,
            actor=employee.user,
        )

    employee.refresh_from_db()
    assert employee.is_active is True
    assert not WorkInOfficeRecord.objects.filter(employee=employee).exists()


def test_save_rejects_inactive_company_from_stale_request_scope(employee_client):
    _, employee = employee_client
    Company.objects.filter(pk=employee.company_id).update(is_active=False)

    with pytest.raises(RuntimeError, match="stale"):
        save_record(
            employee=employee,
            work_date=timezone.localdate(),
            save_as_draft=True,
            actor=employee.user,
        )

    assert not WorkInOfficeRecord.objects.filter(employee=employee).exists()


def test_save_locks_company_before_period_and_employee_identity(
    employee_client,
    monkeypatch,
):
    _, employee = employee_client
    locked_models = []
    original_select_for_update = QuerySet.select_for_update

    def track_select_for_update(queryset, *args, **kwargs):
        locked_models.append(queryset.model)
        return original_select_for_update(queryset, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "select_for_update", track_select_for_update)

    save_record(
        employee=employee,
        work_date=timezone.localdate(),
        save_as_draft=True,
        actor=employee.user,
    )

    assert locked_models[:4] == [
        Company,
        FiscalPeriod,
        User,
        CompanyMembership,
    ]


@pytest.mark.parametrize("operation", ["undo", "reverse"])
def test_approval_reversal_rejects_membership_company_drift_after_period_lock(
    employee_client,
    monkeypatch,
    operation,
):
    _, employee = employee_client
    other_company = Company.objects.create(
        name=f"Reversal Drift {operation}",
        slug=f"reversal-drift-{operation}",
        is_active=False,
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED,
        approved_at=timezone.now(),
    )
    original_lock_wio_period = work_log_services.lock_wio_period

    def drift_company_after_period_lock(*, company_id, work_date):
        period = original_lock_wio_period(company_id=company_id, work_date=work_date)
        CompanyMembership.objects.filter(pk=employee.pk).update(company=other_company)
        return period

    monkeypatch.setattr(
        work_log_services,
        "lock_wio_period",
        drift_company_after_period_lock,
    )

    with pytest.raises(RuntimeError, match="stale"):
        if operation == "undo":
            undo_self_approval(
                employee=employee,
                record_id=record.pk,
                version=record.version,
                actor=employee.user,
            )
        else:
            reverse_approved_record(
                record=record,
                actor=User.objects.create_superuser(email="reversal-root@example.com"),
                reason="Correct historical approval",
            )

    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.APPROVED


def test_self_approval_undo_rejects_inactive_company_scope(employee_client):
    _, employee = employee_client
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED,
        approved_at=timezone.now(),
    )
    Company.objects.filter(pk=employee.company_id).update(is_active=False)

    with pytest.raises(RuntimeError, match="stale"):
        undo_self_approval(
            employee=employee,
            record_id=record.pk,
            version=record.version,
            actor=employee.user,
        )

    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.APPROVED


@pytest.mark.parametrize("operation", ["older_override", "reverse"])
def test_hr_wio_mutations_fail_closed_for_ambiguous_active_scope(
    employee_client,
    operation,
):
    _, employee = employee_client
    work_date = older_weekday()
    FiscalPeriod.objects.create(
        company=employee.company,
        name=f"Ambiguous HR {operation}",
        start_date=work_date - timedelta(days=1),
        end_date=timezone.localdate(),
        reconciliation_cutoff=timezone.now() + timedelta(days=14),
        state=FiscalPeriod.State.ACTIVE,
    )
    hr_user = User.objects.create_user(email=f"ambiguous-hr-{operation}@example.com")
    CompanyMembership.objects.create(
        user=hr_user,
        company=employee.company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    other_company = Company.objects.bulk_create(
        [
            Company(
                name=f"Other HR {operation}",
                slug=f"other-hr-{operation}",
            )
        ]
    )[0]
    CompanyMembership.objects.bulk_create(
        [
            CompanyMembership(
                user=hr_user,
                company=other_company,
                role=CompanyMembership.Role.HR_ADMIN,
            )
        ]
    )

    with pytest.raises(ValidationError, match="Only HR/admin"):
        if operation == "older_override":
            save_record(
                employee=employee,
                work_date=work_date,
                location_choice=WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
                actor=hr_user,
                override_reason="Correct historical record",
            )
        else:
            record = WorkInOfficeRecord.objects.create(
                employee=employee,
                work_date=work_date,
                location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
                review_state=WorkInOfficeRecord.ReviewState.APPROVED,
                approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
                approved_at=timezone.now(),
            )
            reverse_approved_record(
                record=record,
                actor=hr_user,
                reason="Correct historical approval",
            )

    assert not WorkInOfficeRecord.objects.filter(
        employee=employee,
        work_date=work_date,
        review_state=WorkInOfficeRecord.ReviewState.NOT_REQUIRED,
    ).exists()


def test_hr_override_locks_actor_and_employee_identities_in_global_order(
    employee_client,
):
    _, employee = employee_client
    employee.role = CompanyMembership.Role.HR_ADMIN
    employee.save(update_fields=["role"])
    work_date = older_weekday()
    FiscalPeriod.objects.create(
        company=employee.company,
        name="Cross-HR lock order",
        start_date=work_date - timedelta(days=1),
        end_date=timezone.localdate(),
        reconciliation_cutoff=timezone.now() + timedelta(days=14),
        state=FiscalPeriod.State.ACTIVE,
    )
    actor = User.objects.create_user(email="cross-hr-actor@example.com")
    CompanyMembership.objects.create(
        user=actor,
        company=employee.company,
        role=CompanyMembership.Role.HR_ADMIN,
    )

    with CaptureQueriesContext(connection) as queries:
        save_record(
            employee=employee,
            work_date=work_date,
            location_choice=WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
            actor=actor,
            override_reason="Cross-HR correction",
        )

    user_union_locks = [
        query["sql"]
        for query in queries.captured_queries
        if 'FROM "accounts_user"' in query["sql"]
        and 'WHERE "accounts_user"."id" IN (' in query["sql"]
        and 'ORDER BY "accounts_user"."id" ASC' in query["sql"]
    ]
    membership_union_locks = [
        query["sql"]
        for query in queries.captured_queries
        if 'FROM "accounts_companymembership"' in query["sql"]
        and 'ORDER BY "accounts_companymembership"."user_id" ASC' in query["sql"]
        and '"accounts_companymembership"."id" ASC' in query["sql"]
    ]
    assert len(user_union_locks) == 1
    assert len(membership_union_locks) == 1


@pytest.mark.parametrize(
    "state",
    [
        WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
        WorkInOfficeRecord.ReviewState.EXPIRED_PENDING,
    ],
)
def test_locked_queue_states_cannot_be_edited(employee_client, state):
    client, membership = employee_client
    record = WorkInOfficeRecord.objects.create(
        employee=membership,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=state,
    )

    response = client.put(
        f"/api/v1/work-in-office/{record.pk}/",
        {
            "work_date": str(record.work_date),
            "location_choice": "not_in_office",
            "version": record.version,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    record.refresh_from_db()
    assert record.review_state == state
    assert record.location_choice == WorkInOfficeRecord.LocationChoice.IN_OFFICE


def test_submission_ignores_demoted_or_inactive_assigned_manager(employee_client):
    _, employee = employee_client
    manager = CompanyMembership.objects.create(
        user=User.objects.create_user(email="former-manager@example.com"),
        company=employee.company,
        role=CompanyMembership.Role.MANAGER,
    )
    ManagerAssignment.objects.create(
        manager=manager,
        employee=employee,
        effective_from=timezone.localdate(),
    )
    manager.role = CompanyMembership.Role.EMPLOYEE
    manager.save(update_fields=["role"])

    record = save_record(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        actor=employee.user,
    )

    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert record.approval_owner_snapshot == {}


def test_submission_does_not_use_hr_admin_as_silent_manager(employee_client):
    _, employee = employee_client
    hr = CompanyMembership.objects.create(
        user=User.objects.create_user(email="silent-hr-owner@example.com"),
        company=employee.company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    ManagerAssignment.objects.bulk_create(
        [
            ManagerAssignment(
                manager=hr,
                employee=employee,
                effective_from=timezone.localdate(),
            )
        ]
    )

    record = save_record(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
    )

    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert record.approval_owner_snapshot == {}


def test_save_draft_preserves_partial_location_and_note(employee_client):
    client, membership = employee_client
    response = client.post(
        "/api/v1/work-in-office/",
        {
            "work_date": str(timezone.localdate()),
            "location_choice": "in_office",
            "note": "Partial note",
            "save_as_draft": True,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    record = WorkInOfficeRecord.objects.get(employee=membership)
    assert record.review_state == WorkInOfficeRecord.ReviewState.DRAFT
    assert record.location_choice == WorkInOfficeRecord.LocationChoice.IN_OFFICE
    assert record.note == "Partial note"


@pytest.mark.parametrize(
    ("save_as_draft", "location_choice"),
    [(True, "in_office"), (False, None)],
)
def test_rejected_record_cannot_escape_to_draft(
    employee_client,
    save_as_draft,
    location_choice,
):
    client, membership = employee_client
    record = WorkInOfficeRecord.objects.create(
        employee=membership,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.REJECTED,
        correction_deadline=timezone.now() + timedelta(hours=1),
    )

    response = client.put(
        f"/api/v1/work-in-office/{record.pk}/",
        {
            "work_date": str(record.work_date),
            "location_choice": location_choice,
            "note": record.note,
            "save_as_draft": save_as_draft,
            "version": record.version,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.REJECTED


def test_rejected_not_in_office_correction_has_distinct_audit_event(employee_client):
    client, membership = employee_client
    record = WorkInOfficeRecord.objects.create(
        employee=membership,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        note="Original office evidence",
        review_state=WorkInOfficeRecord.ReviewState.REJECTED,
        approver_note="Evidence needs correction",
        rejected_at=timezone.now(),
        correction_deadline=timezone.now() + timedelta(hours=1),
    )

    response = client.put(
        f"/api/v1/work-in-office/{record.pk}/",
        {
            "work_date": str(record.work_date),
            "location_choice": "not_in_office",
            "version": record.version,
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["review_state"] == WorkInOfficeRecord.ReviewState.NOT_REQUIRED
    record.refresh_from_db()
    assert record.approver_note == ""
    assert record.rejected_at is None
    assert record.correction_deadline is None
    event = AuditEvent.objects.get(
        event_type="work_logs.record_rejection_corrected_not_in_office",
        target_id=str(record.pk),
    )
    assert event.metadata["previous_location_choice"] == "in_office"
    assert event.metadata["previous_note"] == "Original office evidence"
    assert event.metadata["rejection_reason"] == "Evidence needs correction"
    assert event.metadata["location_choice"] == "not_in_office"


def test_existing_draft_can_transition_to_approved_but_approved_record_is_immutable(
    employee_client,
):
    _, membership = employee_client
    record = WorkInOfficeRecord.objects.create(
        employee=membership,
        work_date=timezone.localdate(),
        review_state=WorkInOfficeRecord.ReviewState.DRAFT,
    )

    record.location_choice = WorkInOfficeRecord.LocationChoice.IN_OFFICE
    record.review_state = WorkInOfficeRecord.ReviewState.APPROVED
    record.approval_method = WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED
    record.full_clean()
    record.save()

    record.note = "Changed after approval"
    with pytest.raises(ValidationError, match="Approved records are immutable"):
        record.full_clean()
    record.refresh_from_db()
    record.work_date -= timedelta(days=1)
    with pytest.raises(ValidationError, match="Approved records are immutable"):
        record.full_clean()
    record.refresh_from_db()
    record.policy_snapshot = {"tampered": True}
    with pytest.raises(ValidationError, match="Approved records are immutable"):
        record.full_clean()


def test_invalid_record_date_filter_returns_400(employee_client):
    client, _ = employee_client

    response = client.get("/api/v1/work-in-office/?start_date=not-a-date")

    assert response.status_code == 400


@pytest.mark.parametrize(
    "query",
    [
        "?start_date=2026-01-01",
        "?end_date=2026-01-31",
        "?start_date=2025-01-01&end_date=2026-01-02",
        "?start_date=2025-01-01&end_date=2026-02-01",
    ],
)
def test_record_date_filter_rejects_partial_or_unbounded_ranges(employee_client, query):
    client, _ = employee_client

    response = client.get(f"/api/v1/work-in-office/{query}")

    assert response.status_code == 400


@pytest.mark.parametrize(
    "query",
    [
        "?work_date=2026-07-01&month=2026-07",
        "?month=2026-07&start_date=2026-07-01&end_date=2026-07-31",
        "?work_date=2026-07-01&start_date=2026-07-01&end_date=2026-07-31",
    ],
)
def test_record_date_filters_are_mutually_exclusive(employee_client, query):
    client, _ = employee_client

    assert client.get(f"/api/v1/work-in-office/{query}").status_code == 400


def test_attention_records_ignore_month_scope_and_exclude_other_states(employee_client):
    client, membership = employee_client
    current = timezone.localdate()
    old_date = date(2020, 1, 2)
    draft = WorkInOfficeRecord.objects.create(
        employee=membership,
        work_date=old_date,
        review_state=WorkInOfficeRecord.ReviewState.DRAFT,
    )
    WorkInOfficeRecord.objects.create(
        employee=membership,
        work_date=current,
        location_choice=WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.NOT_REQUIRED,
    )

    response = client.get("/api/v1/work-in-office/?attention=true")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [draft.pk]


def test_attention_filter_cannot_be_combined_with_list_filters(employee_client):
    client, _ = employee_client

    response = client.get("/api/v1/work-in-office/?attention=true&review_state=draft")

    assert response.status_code == 400


def test_hr_can_create_audited_older_date_record_in_django_admin(db):
    company = Company.objects.create(name="Override Co", slug="override-co")
    hr = CompanyMembership.objects.create(
        user=User.objects.create_user(email="override-hr@example.com"),
        company=company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="override-employee@example.com"),
        company=company,
    )
    today = timezone.localdate()
    work_date = older_weekday()
    FiscalPeriod.objects.create(
        company=company,
        name="Override period",
        start_date=work_date,
        end_date=today,
        reconciliation_cutoff=timezone.now() + timedelta(days=2),
        state=FiscalPeriod.State.ACTIVE,
    )
    form = WorkInOfficeRecordAdminForm(
        data={
            "employee": employee.pk,
            "work_date": str(work_date),
            "location_choice": WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            "note": "Badge reader outage",
            "override_reason": "Verified against facilities log",
        }
    )
    assert form.is_valid(), form.errors
    record_admin = WorkInOfficeRecordAdmin(WorkInOfficeRecord, admin.site)
    request = type("Request", (), {"user": hr.user})()
    record_admin.save_model(request, form.save(commit=False), form, change=False)

    record = WorkInOfficeRecord.objects.get(employee=employee, work_date=work_date)
    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    event = AuditEvent.objects.get(
        event_type="work_logs.record_older_date_overridden",
        target_id=str(record.pk),
    )
    assert AuditEvent.objects.filter(
        event_type="work_logs.record_submitted",
        target_id=str(record.pk),
    ).exists()
    assert event.actor == hr.user
    assert event.metadata["actor_role"] == CompanyMembership.Role.HR_ADMIN
    assert event.metadata["reason"] == "Verified against facilities log"


def test_hr_can_correct_an_older_rejected_record_in_django_admin(db):
    company = Company.objects.create(name="Correction Co", slug="correction-co")
    hr = CompanyMembership.objects.create(
        user=User.objects.create_user(email="correction-hr@example.com"),
        company=company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="correction-employee@example.com"),
        company=company,
    )
    work_date = older_weekday()
    FiscalPeriod.objects.create(
        company=company,
        name="Correction period",
        start_date=work_date,
        end_date=timezone.localdate(),
        reconciliation_cutoff=timezone.now() + timedelta(days=2),
        state=FiscalPeriod.State.ACTIVE,
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=work_date,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.REJECTED,
        approver_note="Wrong location",
        rejected_at=timezone.now(),
        correction_deadline=timezone.now() + timedelta(days=1),
    )
    form = WorkInOfficeRecordAdminForm(
        instance=record,
        data={
            "employee": employee.pk,
            "work_date": str(work_date),
            "location_choice": WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
            "note": "",
            "override_reason": "HR verified corrected attendance",
        },
    )
    assert form.is_valid(), form.errors

    WorkInOfficeRecordAdmin(WorkInOfficeRecord, admin.site).save_model(
        type("Request", (), {"user": hr.user})(),
        form.save(commit=False),
        form,
        change=True,
    )

    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.NOT_REQUIRED
    assert record.version == 2
    assert AuditEvent.objects.filter(
        event_type="work_logs.record_older_date_overridden",
        target_id=str(record.pk),
        metadata__reason="HR verified corrected attendance",
    ).exists()
    assert AuditEvent.objects.filter(
        event_type="work_logs.record_rejection_corrected_not_in_office",
        target_id=str(record.pk),
    ).exists()


def test_older_date_admin_rejects_html_note(db):
    company = Company.objects.create(name="Plain Note Co", slug="plain-note-co")
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="plain-note@example.com"),
        company=company,
    )
    work_date = older_weekday()
    FiscalPeriod.objects.create(
        company=company,
        name="Plain note period",
        start_date=work_date,
        end_date=timezone.localdate(),
        reconciliation_cutoff=timezone.now() + timedelta(days=2),
        state=FiscalPeriod.State.ACTIVE,
    )

    form = WorkInOfficeRecordAdminForm(
        data={
            "employee": employee.pk,
            "work_date": str(work_date),
            "location_choice": WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            "note": "<b>badge proof</b>",
            "override_reason": "Verified",
        }
    )

    assert not form.is_valid()
    assert "plain text" in str(form.errors["note"]).lower()


def test_older_date_admin_validates_duplicate_and_expired_correction(db):
    company = Company.objects.create(name="Admin Guard Co", slug="admin-guard-co")
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="admin-guard@example.com"),
        company=company,
    )
    work_date = older_weekday()
    FiscalPeriod.objects.create(
        company=company,
        name="Admin guard period",
        start_date=work_date,
        end_date=timezone.localdate(),
        reconciliation_cutoff=timezone.now() + timedelta(days=2),
        state=FiscalPeriod.State.ACTIVE,
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=work_date,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.REJECTED,
        correction_deadline=timezone.now() - timedelta(seconds=1),
    )
    data = {
        "employee": employee.pk,
        "work_date": str(work_date),
        "location_choice": WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
        "note": "",
        "override_reason": "Verified",
    }

    duplicate_form = WorkInOfficeRecordAdminForm(data=data)
    correction_form = WorkInOfficeRecordAdminForm(instance=record, data=data)

    assert not duplicate_form.is_valid()
    assert "already exists" in str(duplicate_form.errors).lower()
    assert not correction_form.is_valid()
    assert "deadline has passed" in str(correction_form.errors).lower()


def test_older_date_override_rejects_non_hr_and_recent_dates(employee_client):
    _, employee = employee_client
    today = timezone.localdate()
    FiscalPeriod.objects.create(
        company=employee.company,
        name="Current period",
        start_date=today - timedelta(days=7),
        end_date=today,
        reconciliation_cutoff=timezone.now() + timedelta(days=2),
        state=FiscalPeriod.State.ACTIVE,
    )
    with pytest.raises(ValidationError, match="Only HR/admin"):
        save_record(
            employee=employee,
            work_date=older_weekday(),
            location_choice=WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
            actor=employee.user,
            override_reason="Verified correction",
        )

    employee.role = CompanyMembership.Role.HR_ADMIN
    employee.save(update_fields=["role"])
    with pytest.raises(ValidationError, match="only available for older dates"):
        save_record(
            employee=employee,
            work_date=today,
            location_choice=WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
            actor=employee.user,
            override_reason="Verified correction",
        )


def test_older_date_override_cannot_bypass_day_eligibility(db):
    company = Company.objects.create(name="Eligibility Co", slug="eligibility-co")
    hr = CompanyMembership.objects.create(
        user=User.objects.create_user(email="eligibility-hr@example.com"),
        company=company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="eligibility-employee@example.com"),
        company=company,
    )
    work_date = older_weekday()
    CompanyHoliday.objects.create(company=company, date=work_date, name="Company holiday")
    FiscalPeriod.objects.create(
        company=company,
        name="Eligibility period",
        start_date=work_date,
        end_date=timezone.localdate(),
        reconciliation_cutoff=timezone.now() + timedelta(days=2),
        state=FiscalPeriod.State.ACTIVE,
    )

    with pytest.raises(ValidationError, match="ineligible: Public holiday"):
        save_record(
            employee=employee,
            work_date=work_date,
            location_choice=WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
            actor=hr.user,
            override_reason="Verified correction",
        )


def test_pending_owner_migration_queues_every_unaudited_legacy_owner(db):
    migration = import_module("apps.work_logs.migrations.0009_repair_pending_approval_ownership")
    company = Company.objects.create(name="Migration Co", slug="migration-co")
    manager = CompanyMembership.objects.create(
        user=User.objects.create_user(email="migration-manager@example.com"),
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    assigned_employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="assigned@example.com"),
        company=company,
    )
    unassigned_employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="unassigned@example.com"),
        company=company,
    )
    invalid_manager = CompanyMembership.objects.create(
        user=User.objects.create_user(email="invalid-manager@example.com"),
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    invalid_owner_employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="invalid-owner@example.com"),
        company=company,
    )
    work_date = date(2026, 7, 24)
    ManagerAssignment.objects.create(
        manager=manager,
        employee=assigned_employee,
        effective_from=date(1970, 1, 1),
    )
    ManagerAssignment.objects.create(
        manager=invalid_manager,
        employee=invalid_owner_employee,
        effective_from=work_date,
    )
    invalid_manager.role = CompanyMembership.Role.EMPLOYEE
    invalid_manager.save(update_fields=["role"])
    assigned = WorkInOfficeRecord.objects.create(
        employee=assigned_employee,
        work_date=work_date,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
    )
    unassigned = WorkInOfficeRecord.objects.create(
        employee=unassigned_employee,
        work_date=work_date,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
    )
    invalid_owner = WorkInOfficeRecord.objects.create(
        employee=invalid_owner_employee,
        work_date=work_date,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot={
            "membership_id": invalid_manager.pk,
            "assignment_id": ManagerAssignment.objects.get(employee=invalid_owner_employee).pk,
        },
    )
    invalid_owner_snapshot = invalid_owner.approval_owner_snapshot

    migration.repair_pending_approval_ownership(django_apps, None)

    assigned.refresh_from_db()
    unassigned.refresh_from_db()
    invalid_owner.refresh_from_db()
    assert assigned.approval_owner_snapshot == {}
    assert assigned.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert unassigned.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert invalid_owner.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert invalid_owner.approval_owner_snapshot == {}
    assigned_event = AuditEvent.objects.get(
        event_type="work_logs.pending_assignment_migrated",
        target_id=str(assigned.pk),
    )
    unassigned_event = AuditEvent.objects.get(
        event_type="work_logs.pending_assignment_migrated",
        target_id=str(unassigned.pk),
    )
    for event in (assigned_event, unassigned_event):
        assert event.metadata["actor_role"] == "system"
        assert event.metadata["actor_company_id"] == company.pk
        assert event.metadata["from_state"] == WorkInOfficeRecord.ReviewState.PENDING
        assert event.metadata["reason"]
    assert assigned_event.metadata["to_state"] == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert (
        unassigned_event.metadata["to_state"] == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    )

    migration.reverse_pending_approval_ownership(django_apps, None)
    assigned.refresh_from_db()
    unassigned.refresh_from_db()
    invalid_owner.refresh_from_db()
    for repaired_record in (assigned, unassigned):
        assert repaired_record.review_state == WorkInOfficeRecord.ReviewState.PENDING
        assert repaired_record.approval_owner_snapshot == {}
        assert repaired_record.version == 1
    assert invalid_owner.review_state == WorkInOfficeRecord.ReviewState.PENDING
    assert invalid_owner.approval_owner_snapshot == invalid_owner_snapshot
    assert invalid_owner.version == 1
    assert not AuditEvent.objects.filter(
        event_type__in=[
            "work_logs.pending_owner_migrated",
            "work_logs.pending_assignment_migrated",
        ]
    ).exists()


def test_pending_owner_migration_reverts_unproven_legacy_self_approval(db):
    migration = import_module("apps.work_logs.migrations.0009_repair_pending_approval_ownership")
    company = Company.objects.create(name="Repair Co", slug="repair-co")
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="repair-manager@example.com"),
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=date(2026, 7, 24),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED,
        approved_at=timezone.now(),
        approved_by_snapshot={"membership_id": employee.pk, "role": employee.role},
    )
    AuditEvent.objects.create(
        actor=employee.user,
        event_type="work_logs.self_approval_migrated",
        target_type="work_logs.WorkInOfficeRecord",
        target_id=str(record.pk),
        metadata={
            "original_state": WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
            "membership_id": employee.pk,
        },
    )

    migration.repair_pending_approval_ownership(django_apps, None)

    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert record.approval_method is None
    assert record.approved_at is None
    assert record.approved_by_snapshot == {}
    event = AuditEvent.objects.get(
        event_type="work_logs.self_approval_migration_reverted",
        target_id=str(record.pk),
    )
    assert event.metadata["actor_role"] == "system"
    assert event.metadata["actor_company_id"] == company.pk
    assert event.metadata["from_state"] == WorkInOfficeRecord.ReviewState.APPROVED
    assert event.metadata["to_state"] == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert event.metadata["reason"]

    migration.reverse_pending_approval_ownership(django_apps, None)
    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.APPROVED
    assert record.approval_method == WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED
    assert record.approved_at is not None
    assert record.approved_by_snapshot["membership_id"] == employee.pk
    assert record.version == 1
    assert not AuditEvent.objects.filter(
        event_type="work_logs.self_approval_migration_reverted",
        target_id=str(record.pk),
    ).exists()


def test_pending_owner_migration_preserves_later_self_approval_changes(db):
    migration = import_module("apps.work_logs.migrations.0009_repair_pending_approval_ownership")
    company = Company.objects.create(name="Later Repair Co", slug="later-repair-co")
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="later-repair-manager@example.com"),
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=date(2026, 7, 24),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED,
        approved_at=timezone.now(),
        approved_by_snapshot={"membership_id": employee.pk, "role": employee.role},
    )
    AuditEvent.objects.create(
        actor=employee.user,
        event_type="work_logs.self_approval_migrated",
        target_type="work_logs.WorkInOfficeRecord",
        target_id=str(record.pk),
        metadata={
            "original_state": WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
            "membership_id": employee.pk,
        },
    )
    record.note = "Legitimate later correction"
    record.version += 1
    record.save(update_fields=["note", "version", "updated_at"])
    AuditEvent.objects.create(
        actor=employee.user,
        event_type="work_logs.record_corrected",
        target_type="work_logs.WorkInOfficeRecord",
        target_id=str(record.pk),
        metadata={"revision": record.version},
    )

    migration.repair_pending_approval_ownership(django_apps, None)

    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.APPROVED
    assert record.approval_method == WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED
    assert record.note == "Legitimate later correction"
    assert record.version == 2
    assert not AuditEvent.objects.filter(
        event_type="work_logs.self_approval_migration_reverted",
        target_id=str(record.pk),
    ).exists()


def test_pending_owner_migration_preserves_audited_explicit_reassignment(db):
    migration = import_module("apps.work_logs.migrations.0009_repair_pending_approval_ownership")
    company = Company.objects.create(name="Explicit Owner Co", slug="explicit-owner-co")
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="explicit-owner-employee@example.com"),
        company=company,
    )
    manager = CompanyMembership.objects.create(
        user=User.objects.create_user(email="explicit-owner-manager@example.com"),
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    hr = CompanyMembership.objects.create(
        user=User.objects.create_user(email="explicit-owner-hr@example.com"),
        company=company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=date(2026, 7, 24),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
    )
    assigned = assign_pending_record(
        hr=hr,
        record_id=record.pk,
        manager_id=manager.pk,
        version=record.version,
        reason="Audited coverage handoff",
    )
    assigned_snapshot = assigned.approval_owner_snapshot.copy()
    assigned_version = assigned.version

    migration.repair_pending_approval_ownership(django_apps, None)

    assigned.refresh_from_db()
    assert assigned.review_state == WorkInOfficeRecord.ReviewState.PENDING
    assert assigned.approval_owner_snapshot == assigned_snapshot
    assert assigned.version == assigned_version
    assert not AuditEvent.objects.filter(
        event_type__in=[
            "work_logs.pending_owner_migrated",
            "work_logs.pending_assignment_migrated",
        ],
        target_id=str(assigned.pk),
    ).exists()


def test_company_date_uses_each_company_timezone():
    at = datetime(2026, 7, 24, 20, tzinfo=UTC)
    vietnam = Company(timezone="Asia/Ho_Chi_Minh")
    california = Company(timezone="America/Los_Angeles")

    assert company_date(at, vietnam) == date(2026, 7, 25)
    assert company_date(at, california) == date(2026, 7, 24)


def test_wio_metadata_reports_persisted_fiscal_state(employee_client):
    client, membership = employee_client
    today = timezone.localdate()
    FiscalPeriod.objects.create(
        company=membership.company,
        name="Awaiting validated promotion",
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=1),
        state=FiscalPeriod.State.UPCOMING,
    )

    response = client.get("/api/v1/work-in-office/meta/")

    assert response.status_code == 200
    assert response.json()["fiscal_period"]["state"] == FiscalPeriod.State.UPCOMING


@override_settings(WIO_FIXED_NOW=datetime(2020, 1, 2, 12, tzinfo=UTC))
def test_fixed_wio_clock_controls_correction_checks_and_timestamps(employee_client):
    _, membership = employee_client
    record = WorkInOfficeRecord.objects.create(
        employee=membership,
        work_date=date(2020, 1, 1),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.REJECTED,
        correction_deadline=datetime(2020, 1, 2, 13, tzinfo=UTC),
    )

    corrected = save_record(
        employee=membership,
        work_date=record.work_date,
        location_choice=WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
        version=record.version,
        expected_record_id=record.pk,
    )

    assert corrected.review_state == WorkInOfficeRecord.ReviewState.NOT_REQUIRED
    assert corrected.submitted_at == datetime(2020, 1, 2, 12, tzinfo=UTC)
