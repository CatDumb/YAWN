import csv
import logging
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import IntegrityError, connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership, ManagerAssignment, User, UserPreference
from apps.audit.models import AuditEvent
from apps.work_logs.approvals import expire_pending_for_period, reject_scoped_record
from apps.work_logs.finalization import run_finalization
from apps.work_logs.models import (
    ApprovedLeave,
    BaseLocation,
    CompanyHoliday,
    FinalizedLedgerRevision,
    FiscalFinalizationStep,
    FiscalPeriod,
    ProjectStatusRule,
    RemoteWorkException,
    WorkInOfficeRecord,
    WorkIntentionOccurrence,
    WorkIntentionSeries,
)
from apps.work_logs.planner import (
    edit_intention,
    notify_planner_purge,
    preview,
    projection,
    purge_intentions_for_period,
    save_intentions,
)
from apps.work_logs.reports import csv_response, freeze_period_ledgers, report_for
from apps.work_logs.services import save_record


def membership(*, email, company, role=CompanyMembership.Role.EMPLOYEE):
    user = User.objects.create_user(email=email)
    return CompanyMembership.objects.create(user=user, company=company, role=role)


def active_period(company, today):
    return FiscalPeriod.objects.create(
        company=company,
        name="Current",
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=30),
        state=FiscalPeriod.State.ACTIVE,
    )


def test_privileged_submission_self_approves_and_can_be_undone(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    record = save_record(
        employee=manager,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        actor=manager.user,
    )

    assert record.review_state == WorkInOfficeRecord.ReviewState.APPROVED
    assert record.approval_method == WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED
    assert record.approved_by_snapshot["membership_id"] == manager.pk

    client.force_login(manager.user)
    response = client.post(
        f"/api/v1/work-in-office/{record.pk}/undo-self-approval/",
        {"version": record.version},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["review_state"] == WorkInOfficeRecord.ReviewState.DRAFT
    assert response.json()["approval_method"] is None
    assert AuditEvent.objects.filter(event_type="work_logs.self_approval_undone").exists()


def test_employee_submission_stays_pending_and_self_undo_is_hidden(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    ManagerAssignment.objects.create(
        manager=manager, employee=employee, effective_from=timezone.localdate()
    )
    record = save_record(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        actor=employee.user,
    )

    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING
    assert record.approval_method is None

    client.force_login(employee.user)
    response = client.post(
        f"/api/v1/work-in-office/{record.pk}/undo-self-approval/",
        {"version": record.version},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_manager_queue_decision_is_assignment_scoped(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    employee.user.first_name = "Ada"
    employee.user.last_name = "Lovelace"
    employee.user.save(update_fields=["first_name", "last_name"])
    employee.base_location = BaseLocation.objects.create(
        company=company, name="Headquarters", code="hq"
    )
    employee.save(update_fields=["base_location"])
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    today = timezone.localdate()
    ManagerAssignment.objects.create(manager=manager, employee=employee, effective_from=today)
    record = save_record(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
    )
    client.force_login(manager.user)
    queue = client.get("/api/v1/approvals/")
    assert queue.status_code == 200
    assert [item["id"] for item in queue.json()] == [record.pk]
    assert queue.json()[0]["employee_name"] == "Ada Lovelace"
    assert queue.json()[0]["employee_email"] == "employee@example.com"
    assert queue.json()[0]["base_location_name"] == "Headquarters"
    approved = client.post(
        f"/api/v1/approvals/{record.pk}/approve/",
        {"version": record.version},
        content_type="application/json",
    )
    assert approved.status_code == 200
    assert approved.json()["review_state"] == WorkInOfficeRecord.ReviewState.APPROVED
    assert mail.outbox == []


def test_manager_queue_prioritizes_reconciliation_claims_before_active_oldest(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    today = timezone.localdate()
    ManagerAssignment.objects.create(
        manager=manager,
        employee=employee,
        effective_from=today - timedelta(days=60),
    )
    FiscalPeriod.objects.create(
        company=company,
        name="Previous",
        start_date=today - timedelta(days=60),
        end_date=today - timedelta(days=30),
        state=FiscalPeriod.State.RECONCILIATION,
    )
    FiscalPeriod.objects.create(
        company=company,
        name="Current",
        start_date=today - timedelta(days=29),
        end_date=today + timedelta(days=30),
        state=FiscalPeriod.State.ACTIVE,
    )
    older_active = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot={"membership_id": manager.pk},
        submitted_at=timezone.now() - timedelta(days=2),
    )
    newer_reconciliation = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today - timedelta(days=30),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot={"membership_id": manager.pk},
        submitted_at=timezone.now(),
    )

    client.force_login(manager.user)
    queue = client.get("/api/v1/approvals/")

    assert queue.status_code == 200
    assert [item["id"] for item in queue.json()] == [
        newer_reconciliation.pk,
        older_active.pk,
    ]


def test_approval_queues_paginate_at_fifty_and_reject_invalid_page(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    hr = membership(email="hr@example.com", company=company, role=CompanyMembership.Role.HR_ADMIN)
    base_time = timezone.now() - timedelta(days=3)
    ManagerAssignment.objects.create(
        manager=manager,
        employee=employee,
        effective_from=timezone.localdate() - timedelta(days=60),
    )
    manager_records = [
        WorkInOfficeRecord.objects.create(
            employee=employee,
            work_date=timezone.localdate() - timedelta(days=index),
            location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            review_state=WorkInOfficeRecord.ReviewState.PENDING,
            approval_owner_snapshot={"membership_id": manager.pk},
            submitted_at=base_time + timedelta(minutes=index),
        )
        for index in range(55)
    ]
    pending_assignment_records = [
        WorkInOfficeRecord.objects.create(
            employee=employee,
            work_date=timezone.localdate() + timedelta(days=index + 1),
            location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
            submitted_at=base_time + timedelta(minutes=index),
        )
        for index in range(55)
    ]

    client.force_login(manager.user)
    first_page = client.get("/api/v1/approvals/")
    second_page = client.get("/api/v1/approvals/?page=2")
    invalid_page = client.get("/api/v1/approvals/?page=banana")

    assert first_page.status_code == 200
    assert len(first_page.json()) == 50
    assert [item["id"] for item in second_page.json()] == [
        record.pk for record in manager_records[50:]
    ]
    assert invalid_page.status_code == 400
    assert invalid_page.json()["detail"] == "page must be a positive integer."

    client.force_login(hr.user)
    first_assignment_page = client.get("/api/v1/approvals/pending-assignment/")
    second_assignment_page = client.get("/api/v1/approvals/pending-assignment/?page=2")
    invalid_assignment_page = client.get("/api/v1/approvals/pending-assignment/?page=0")

    assert first_assignment_page.status_code == 200
    assert len(first_assignment_page.json()) == 50
    assert [item["id"] for item in second_assignment_page.json()] == [
        record.pk for record in pending_assignment_records[50:]
    ]
    assert invalid_assignment_page.status_code == 400
    assert invalid_assignment_page.json()["detail"] == "page must be a positive integer."


def test_target_size_approval_queues_do_not_add_per_row_queries(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    hr = membership(email="hr@example.com", company=company, role=CompanyMembership.Role.HR_ADMIN)
    today = timezone.localdate()
    for offset in range(55):
        base = BaseLocation.objects.create(
            company=company, name=f"Base {offset}", code=f"base-{offset}"
        )
        employee = membership(email=f"employee-{offset}@example.com", company=company)
        employee.base_location = base
        employee.save(update_fields=["base_location"])
        WorkInOfficeRecord.objects.create(
            employee=employee,
            work_date=today - timedelta(days=offset),
            location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            review_state=WorkInOfficeRecord.ReviewState.PENDING,
            submitted_at=timezone.now() - timedelta(minutes=offset),
            approval_owner_snapshot={"membership_id": manager.pk},
        )
        WorkInOfficeRecord.objects.create(
            employee=employee,
            work_date=today + timedelta(days=offset + 1),
            location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
            submitted_at=timezone.now() - timedelta(minutes=offset),
        )

    client.force_login(manager.user)
    with CaptureQueriesContext(connection) as approval_queries:
        approval_queue = client.get("/api/v1/approvals/")
    client.force_login(hr.user)
    with CaptureQueriesContext(connection) as assignment_queries:
        assignment_queue = client.get("/api/v1/approvals/pending-assignment/")

    assert approval_queue.status_code == 200
    assert assignment_queue.status_code == 200
    assert len(approval_queue.json()) == 50
    assert len(assignment_queue.json()) == 50
    assert len(approval_queries) <= 10
    assert len(assignment_queries) <= 10
    assert approval_queue.json()[0]["base_location_name"] == "Base 54"
    assert assignment_queue.json()[0]["base_location_name"] == "Base 54"


def test_approval_undo_is_server_timed_and_appends_reversal_history(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    today = timezone.localdate()
    ManagerAssignment.objects.create(manager=manager, employee=employee, effective_from=today)
    record = save_record(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
    )
    client.force_login(manager.user)

    approved = client.post(
        f"/api/v1/approvals/{record.pk}/approve/",
        {"version": record.version},
        content_type="application/json",
    )
    undone = client.post(
        f"/api/v1/approvals/{record.pk}/undo/",
        {"version": approved.json()["version"]},
        content_type="application/json",
    )

    assert undone.status_code == 200
    assert undone.json()["review_state"] == WorkInOfficeRecord.ReviewState.PENDING
    assert AuditEvent.objects.filter(
        event_type="work_logs.approval_undone",
        target_type="work_logs.WorkInOfficeRecord",
        target_id=str(record.pk),
    ).exists()

    record.refresh_from_db()
    approved_again = client.post(
        f"/api/v1/approvals/{record.pk}/approve/",
        {"version": record.version},
        content_type="application/json",
    )
    record.refresh_from_db()
    record.approved_at = timezone.now() - timedelta(seconds=11)
    record.save(update_fields=["approved_at"])
    expired_undo = client.post(
        f"/api/v1/approvals/{record.pk}/undo/",
        {"version": approved_again.json()["version"]},
        content_type="application/json",
    )
    record.refresh_from_db()

    assert expired_undo.status_code == 400
    assert "10-second undo window has expired" in expired_undo.json()["detail"]
    assert record.review_state == WorkInOfficeRecord.ReviewState.APPROVED
    assert (
        AuditEvent.objects.filter(
            event_type="work_logs.approval_undone",
            target_type="work_logs.WorkInOfficeRecord",
            target_id=str(record.pk),
        ).count()
        == 1
    )


def test_hr_resolves_pending_assignment_with_audited_explicit_owner(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    hr = membership(email="hr@example.com", company=company, role=CompanyMembership.Role.HR_ADMIN)
    record = save_record(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
    )
    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    client.force_login(manager.user)
    assert client.get("/api/v1/approvals/").json() == []
    client.force_login(hr.user)
    assert [item["id"] for item in client.get("/api/v1/approvals/pending-assignment/").json()] == [
        record.pk
    ]
    assert client.get("/api/v1/approvals/assignees/").json() == [
        {
            "id": manager.pk,
            "name": manager.user.get_full_name() or manager.user.email,
            "email": manager.user.email,
        }
    ]
    assigned = client.post(
        f"/api/v1/approvals/{record.pk}/assign/",
        {
            "version": record.version,
            "manager_membership_id": manager.pk,
            "reason": "Coverage handoff",
        },
        content_type="application/json",
    )
    assert assigned.status_code == 200
    assert assigned.json()["review_state"] == WorkInOfficeRecord.ReviewState.PENDING
    client.force_login(manager.user)
    assert [item["id"] for item in client.get("/api/v1/approvals/").json()] == [record.pk]


def test_phase3_api_role_company_matrix_keeps_private_resources_scoped(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    other_company = Company.objects.create(name="Other", slug="other")
    employee = membership(email="employee@example.com", company=company)
    assigned_manager = membership(
        email="assigned-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    unassigned_manager = membership(
        email="unassigned-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    inactive_manager = membership(
        email="inactive-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    inactive_manager.is_active = False
    inactive_manager.save(update_fields=["is_active"])
    hr = membership(email="hr@example.com", company=company, role=CompanyMembership.Role.HR_ADMIN)
    other_manager = membership(
        email="other-manager@example.com",
        company=other_company,
        role=CompanyMembership.Role.MANAGER,
    )
    other_hr = membership(
        email="other-hr@example.com",
        company=other_company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    no_membership_user = User.objects.create_user(email="no-membership@example.com")
    today = timezone.localdate()
    active_period(company, today)
    active_period(other_company, today)
    for owner in (company, other_company):
        ProjectStatusRule.objects.create(
            company=owner,
            assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
            effective_from=today - timedelta(days=31),
            expected_fraction=Decimal("1.00"),
        )
    pending = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        note="EMPLOYEE_PRIVATE_WIO_NOTE",
        approval_owner_snapshot={"membership_id": assigned_manager.pk},
        submitted_at=timezone.now(),
    )
    pending_assignment = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today - timedelta(days=1),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
        submitted_at=timezone.now(),
    )
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today + timedelta(days=1),
        location="home",
        commitment="flexible",
        note="PLANNER_MATRIX_SECRET",
    )

    for path in (
        "/api/v1/work-in-office/",
        f"/api/v1/work-in-office/{pending.pk}/",
        "/api/v1/planner/",
        "/api/v1/reports/",
        "/api/v1/reports/csv/",
        "/api/v1/approvals/",
        "/api/v1/approvals/pending-assignment/",
    ):
        client.logout()
        assert client.get(path).status_code in {401, 403}
        client.force_login(no_membership_user)
        assert client.get(path).status_code == 403

    client.force_login(employee.user)
    assert {item["id"] for item in client.get("/api/v1/work-in-office/").json()} == {
        pending.pk,
        pending_assignment.pk,
    }
    assert client.get(f"/api/v1/work-in-office/{pending.pk}/").status_code == 200
    assert "PLANNER_MATRIX_SECRET" in str(client.get("/api/v1/planner/").json())
    assert "PLANNER_MATRIX_SECRET" not in client.get("/api/v1/reports/csv/").content.decode("utf-8")
    assert client.get("/api/v1/approvals/").status_code == 403
    assert client.get("/api/v1/approvals/pending-assignment/").status_code == 403

    client.force_login(assigned_manager.user)
    approval_queue = client.get("/api/v1/approvals/")
    assert approval_queue.status_code == 200
    assert [item["id"] for item in approval_queue.json()] == [pending.pk]
    assert client.get(f"/api/v1/work-in-office/{pending.pk}/").status_code == 404
    assert "PLANNER_MATRIX_SECRET" not in str(client.get("/api/v1/planner/").json())

    client.force_login(unassigned_manager.user)
    assert client.get("/api/v1/approvals/").json() == []
    assert (
        client.post(
            f"/api/v1/approvals/{pending.pk}/approve/",
            {"version": pending.version},
            content_type="application/json",
        ).status_code
        == 400
    )

    client.force_login(inactive_manager.user)
    assert client.get("/api/v1/approvals/").status_code == 403

    client.force_login(other_manager.user)
    assert client.get("/api/v1/approvals/").json() == []
    assert client.get(f"/api/v1/work-in-office/{pending.pk}/").status_code == 404
    assert "PLANNER_MATRIX_SECRET" not in str(client.get("/api/v1/planner/").json())

    client.force_login(hr.user)
    assert [item["id"] for item in client.get("/api/v1/approvals/pending-assignment/").json()] == [
        pending_assignment.pk
    ]
    assignees = client.get("/api/v1/approvals/assignees/").json()
    assert {item["id"] for item in assignees} == {assigned_manager.pk, unassigned_manager.pk}

    client.force_login(other_hr.user)
    assert client.get("/api/v1/approvals/pending-assignment/").json() == []
    assert (
        client.post(
            f"/api/v1/approvals/{pending_assignment.pk}/assign/",
            {
                "version": pending_assignment.version,
                "manager_membership_id": other_manager.pk,
                "reason": "Wrong company should not assign",
            },
            content_type="application/json",
        ).status_code
        == 400
    )


def test_error_responses_do_not_echo_private_wio_or_planner_content(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    assigned_manager = membership(
        email="assigned-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    unassigned_manager = membership(
        email="unassigned-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    hr = membership(email="hr@example.com", company=company, role=CompanyMembership.Role.HR_ADMIN)
    today = timezone.localdate()
    active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        expected_fraction=Decimal("1.00"),
    )
    pending = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        note="PRIVATE_WIO_ERROR_SENTINEL",
        approver_note="PRIVATE_MANAGER_ERROR_SENTINEL",
        approval_owner_snapshot={"membership_id": assigned_manager.pk},
    )
    pending_assignment = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today - timedelta(days=1),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
    )
    intention = WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today + timedelta(days=1),
        location="home",
        commitment="flexible",
        note="PRIVATE_PLANNER_ERROR_SENTINEL",
    )
    forbidden = [
        "PRIVATE_WIO_ERROR_SENTINEL",
        "PRIVATE_MANAGER_ERROR_SENTINEL",
        "PRIVATE_PLANNER_ERROR_SENTINEL",
        "REQUEST_PAYLOAD_SECRET",
    ]

    def assert_no_secret(response):
        body = response.content.decode("utf-8")
        for secret in forbidden:
            assert secret not in body

    client.force_login(unassigned_manager.user)
    assert_no_secret(
        client.post(
            f"/api/v1/approvals/{pending.pk}/approve/",
            {"version": pending.version},
            content_type="application/json",
        )
    )
    client.force_login(assigned_manager.user)
    assert_no_secret(
        client.post(
            f"/api/v1/approvals/{pending.pk}/reject/",
            {"version": pending.version, "reason": "REQUEST_PAYLOAD_SECRET"},
            content_type="application/json",
        )
    )
    client.force_login(hr.user)
    assert_no_secret(
        client.post(
            f"/api/v1/approvals/{pending_assignment.pk}/assign/",
            {
                "version": pending_assignment.version,
                "manager_membership_id": employee.pk,
                "reason": "REQUEST_PAYLOAD_SECRET",
            },
            content_type="application/json",
        )
    )
    client.force_login(employee.user)
    assert_no_secret(
        client.post(
            "/api/v1/planner/",
            {
                "start_date": (today + timedelta(days=1)).isoformat(),
                "location": "office",
                "commitment": "firm",
                "note": "<b>REQUEST_PAYLOAD_SECRET</b>",
            },
            content_type="application/json",
        )
    )
    assert_no_secret(
        client.patch(
            f"/api/v1/planner/{intention.pk}/",
            {
                "version": intention.version,
                "location": "office",
                "commitment": "firm",
                "note": "<b>REQUEST_PAYLOAD_SECRET</b>",
            },
            content_type="application/json",
        )
    )


def test_request_logs_do_not_include_private_wio_or_planner_content(client, db, caplog):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    assigned_manager = membership(
        email="assigned-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    unassigned_manager = membership(
        email="unassigned-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    today = timezone.localdate()
    active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        expected_fraction=Decimal("1.00"),
    )
    pending = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        note="PRIVATE_WIO_LOG_SENTINEL",
        approver_note="PRIVATE_MANAGER_LOG_SENTINEL",
        approval_owner_snapshot={"membership_id": assigned_manager.pk},
    )
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today + timedelta(days=1),
        location="home",
        commitment="flexible",
        note="PRIVATE_PLANNER_LOG_SENTINEL",
    )
    forbidden = [
        "PRIVATE_WIO_LOG_SENTINEL",
        "PRIVATE_MANAGER_LOG_SENTINEL",
        "PRIVATE_PLANNER_LOG_SENTINEL",
        "REQUEST_LOG_SECRET",
    ]
    caplog.set_level(logging.INFO)

    client.force_login(unassigned_manager.user)
    client.post(
        f"/api/v1/approvals/{pending.pk}/approve/",
        {"version": pending.version, "reason": "REQUEST_LOG_SECRET"},
        content_type="application/json",
    )
    client.force_login(employee.user)
    client.post(
        "/api/v1/planner/",
        {
            "start_date": (today + timedelta(days=1)).isoformat(),
            "location": "office",
            "commitment": "firm",
            "note": "<b>REQUEST_LOG_SECRET</b>",
        },
        content_type="application/json",
    )

    log_dump = "\n".join(
        "\n".join([record.getMessage(), str(record.args), str(record.__dict__)])
        for record in caplog.records
    )
    for secret in forbidden:
        assert secret not in log_dump


def test_wio_and_approval_failures_recover_without_logging_private_content(
    client, db, monkeypatch, caplog
):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    today = timezone.localdate()
    private_error = "PRIVATE_WIO_APPROVAL_FAILURE_SENTINEL"

    def fail_action(**_kwargs):
        raise ValueError(private_error)

    monkeypatch.setattr("apps.work_logs.views.save_record", fail_action)
    monkeypatch.setattr("apps.work_logs.views.approve_record", fail_action)
    caplog.set_level(logging.ERROR, logger="wio.work_logs")

    client.force_login(employee.user)
    created = client.post(
        "/api/v1/work-in-office/",
        {
            "work_date": today.isoformat(),
            "location_choice": WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            "note": "private WIO note that must not appear",
        },
        content_type="application/json",
    )
    client.force_login(manager.user)
    approved = client.post(
        "/api/v1/approvals/123/approve/",
        {"version": 1, "reason": "private approval text that must not appear"},
        content_type="application/json",
    )

    assert created.status_code == 503
    assert created.json()["detail"] == (
        "Work-in-office record is temporarily unavailable. Try again later."
    )
    assert approved.status_code == 503
    assert approved.json()["detail"] == (
        "Approval action is temporarily unavailable. Try again later."
    )
    assert private_error not in caplog.text
    assert "private WIO note" not in caplog.text
    assert "private approval text" not in caplog.text
    assert [record.message for record in caplog.records if record.name == "wio.work_logs"] == [
        "wio_record_create_failed",
        "approval_decision_failed",
    ]
    assert {record.error_class for record in caplog.records if record.name == "wio.work_logs"} == {
        "ValueError"
    }


def test_wio_update_and_delete_failures_recover_without_logging_private_content(
    client, db, monkeypatch, caplog
):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.NOT_REQUIRED,
    )
    private_error = "PRIVATE_WIO_UPDATE_DELETE_FAILURE_SENTINEL"

    def fail_save(**_kwargs):
        raise ValueError(private_error)

    monkeypatch.setattr("apps.work_logs.views.save_record", fail_save)
    caplog.set_level(logging.ERROR, logger="wio.work_logs")
    client.force_login(employee.user)

    updated = client.put(
        f"/api/v1/work-in-office/{record.pk}/",
        {
            "work_date": today.isoformat(),
            "location_choice": WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            "note": "private update note that must not appear",
            "version": record.version,
        },
        content_type="application/json",
    )
    deleted = client.delete(f"/api/v1/work-in-office/{record.pk}/?version={record.version}")

    assert updated.status_code == 503
    assert deleted.status_code == 503
    assert updated.json()["detail"] == (
        "Work-in-office record is temporarily unavailable. Try again later."
    )
    assert deleted.json()["detail"] == (
        "Work-in-office record is temporarily unavailable. Try again later."
    )
    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.NOT_REQUIRED
    assert private_error not in caplog.text
    assert "private update note" not in caplog.text
    assert [entry.message for entry in caplog.records if entry.name == "wio.work_logs"] == [
        "wio_record_update_failed",
        "wio_record_delete_failed",
    ]
    assert {entry.error_class for entry in caplog.records if entry.name == "wio.work_logs"} == {
        "ValueError"
    }


def test_assignment_and_undo_failures_recover_without_logging_private_content(
    client, db, monkeypatch, caplog
):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    hr = membership(email="hr@example.com", company=company, role=CompanyMembership.Role.HR_ADMIN)
    today = timezone.localdate()
    pending_assignment = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
    )
    approved = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today - timedelta(days=1),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
        approval_owner_snapshot={"membership_id": manager.pk},
        approved_by_snapshot={"membership_id": manager.pk},
        approved_at=timezone.now(),
    )
    private_error = "PRIVATE_ASSIGN_UNDO_FAILURE_SENTINEL"

    def fail_action(**_kwargs):
        raise ValueError(private_error)

    monkeypatch.setattr("apps.work_logs.views.assign_pending_record", fail_action)
    monkeypatch.setattr("apps.work_logs.views.undo_approval", fail_action)
    caplog.set_level(logging.ERROR, logger="wio.work_logs")

    client.force_login(hr.user)
    assigned = client.post(
        f"/api/v1/approvals/{pending_assignment.pk}/assign/",
        {
            "version": pending_assignment.version,
            "manager_membership_id": manager.pk,
            "reason": "private assignment reason that must not appear",
        },
        content_type="application/json",
    )
    client.force_login(manager.user)
    undone = client.post(
        f"/api/v1/approvals/{approved.pk}/undo/",
        {
            "version": approved.version,
            "reason": "private undo reason that must not appear",
        },
        content_type="application/json",
    )

    assert assigned.status_code == 503
    assert undone.status_code == 503
    assert assigned.json()["detail"] == (
        "Approval action is temporarily unavailable. Try again later."
    )
    assert undone.json()["detail"] == "Approval action is temporarily unavailable. Try again later."
    assert private_error not in caplog.text
    assert "private assignment reason" not in caplog.text
    assert "private undo reason" not in caplog.text
    assert [entry.message for entry in caplog.records if entry.name == "wio.work_logs"] == [
        "approval_assignment_failed",
        "approval_undo_failed",
    ]
    assert {entry.error_class for entry in caplog.records if entry.name == "wio.work_logs"} == {
        "ValueError"
    }


def test_dashboard_ratio_failures_recover_without_logging_private_content(
    client, db, monkeypatch, caplog
):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        expected_fraction=Decimal("0.50"),
    )
    private_error = "PRIVATE_DASHBOARD_RATIO_SENTINEL"

    def fail_report(**_kwargs):
        raise RuntimeError(private_error)

    monkeypatch.setattr("apps.work_logs.dashboard_views.report_for", fail_report)
    caplog.set_level(logging.ERROR, logger="wio.dashboard")
    client.force_login(employee.user)

    failed = client.get("/api/v1/dashboard/ratio/")

    assert failed.status_code == 503
    assert failed.json()["detail"] == (
        "Dashboard ratio is temporarily unavailable. Try again later."
    )
    assert private_error not in caplog.text
    assert [record.message for record in caplog.records if record.name == "wio.dashboard"] == [
        "dashboard_ratio_failed"
    ]
    assert {record.error_class for record in caplog.records if record.name == "wio.dashboard"} == {
        "RuntimeError"
    }


def test_dashboard_future_projection_failure_keeps_verified_ratio_without_private_logs(
    client, db, monkeypatch, caplog
):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        expected_fraction=Decimal("0.50"),
    )
    private_error = "PRIVATE_FUTURE_RATIO_SENTINEL"

    def fail_future_ratio(**_kwargs):
        raise RuntimeError(private_error)

    monkeypatch.setattr("apps.work_logs.dashboard_views.ratio_ledger", fail_future_ratio)
    caplog.set_level(logging.ERROR, logger="wio.dashboard")
    client.force_login(employee.user)

    response = client.get("/api/v1/dashboard/ratio/")

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["remaining_eligible_days"] is None
    assert private_error not in caplog.text
    assert [record.message for record in caplog.records if record.name == "wio.dashboard"] == [
        "dashboard_future_projection_failed"
    ]
    assert {record.error_class for record in caplog.records if record.name == "wio.dashboard"} == {
        "RuntimeError"
    }


@override_settings(WIO_ENFORCE_SINGLE_COMPANY=True)
def test_production_single_active_company_invariant_rejects_create_and_activation(db):
    Company.objects.create(name="Yawn", slug="yawn")
    with pytest.raises(ValidationError, match="Only one active company is supported"):
        Company.objects.create(name="Second", slug="second")

    inactive = Company.objects.create(name="Inactive", slug="inactive", is_active=False)
    inactive.is_active = True
    with pytest.raises(ValidationError, match="Only one active company is supported"):
        inactive.save(update_fields=["is_active"])


def test_manager_assignment_overlap_rejected_and_ambiguous_legacy_scope_fails_closed(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    other_manager = membership(
        email="other-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    today = timezone.localdate()
    ManagerAssignment.objects.create(manager=manager, employee=employee, effective_from=today)

    with pytest.raises(ValidationError, match="cannot overlap"):
        ManagerAssignment.objects.create(
            manager=other_manager,
            employee=employee,
            effective_from=today,
        )

    ManagerAssignment.objects.bulk_create(
        [
            ManagerAssignment(
                manager=other_manager,
                employee=employee,
                effective_from=today,
            )
        ]
    )

    record = save_record(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
    )

    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert record.approval_owner_snapshot == {}


@override_settings(WIO_APP_URL="https://app.example.test")
def test_rejection_email_uses_employee_language_and_omits_private_reason(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    UserPreference.objects.create(user=employee.user, language=UserPreference.Language.VIETNAMESE)
    today = timezone.localdate()
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot={"membership_id": manager.pk},
    )

    reject_scoped_record(
        manager=manager,
        record_id=record.pk,
        version=record.version,
        reason="Sensitive manager-only reason",
    )

    assert mail.outbox[0].subject == "Bản ghi làm việc tại văn phòng cần sửa"
    assert f"ngày {today.isoformat()}" in mail.outbox[0].body
    assert f"https://app.example.test/work-in-office/{record.pk}" in mail.outbox[0].body
    assert "Sensitive manager-only reason" not in mail.outbox[0].body


@override_settings(WIO_APP_URL="https://app.example.test")
def test_rejection_email_failure_rolls_back_without_logging_private_content(
    client, db, monkeypatch, caplog
):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot={"membership_id": manager.pk},
    )

    def fail_send_mail(**kwargs):
        raise RuntimeError("PRIVATE_REJECTION_EMAIL_FAILURE_SENTINEL")

    monkeypatch.setattr("apps.work_logs.approvals.send_mail", fail_send_mail)
    caplog.set_level(logging.ERROR, logger="wio.approvals")
    caplog.set_level(logging.ERROR, logger="wio.work_logs")
    client.force_login(manager.user)

    response = client.post(
        f"/api/v1/approvals/{record.pk}/reject/",
        {
            "version": record.version,
            "reason": "PRIVATE_MANAGER_REJECTION_REASON",
        },
        content_type="application/json",
    )

    assert response.status_code == 503
    assert (
        response.json()["detail"] == "Approval action is temporarily unavailable. Try again later."
    )
    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING
    assert record.rejected_at is None
    assert not AuditEvent.objects.filter(
        event_type="work_logs.record_rejected",
        target_id=str(record.pk),
    ).exists()
    assert "PRIVATE_REJECTION_EMAIL_FAILURE_SENTINEL" not in caplog.text
    assert "PRIVATE_MANAGER_REJECTION_REASON" not in caplog.text
    assert [
        entry.message
        for entry in caplog.records
        if entry.name in {"wio.approvals", "wio.work_logs"}
    ] == ["approval_rejection_email_failed", "approval_decision_failed"]
    assert {entry.error_class for entry in caplog.records if hasattr(entry, "error_class")} == {
        "RejectionEmailDeliveryError",
        "RuntimeError",
    }


def test_rejected_correction_survives_normal_close_until_deadline(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    work_date = today - timedelta(days=10)
    FiscalPeriod.objects.create(
        company=company,
        name="Current",
        start_date=work_date,
        end_date=today,
        reconciliation_cutoff=timezone.now() + timedelta(days=2),
        state=FiscalPeriod.State.ACTIVE,
    )
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=work_date,
        expected_fraction=Decimal("1.00"),
    )
    rejected = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=work_date,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.REJECTED,
        correction_deadline=timezone.now() + timedelta(hours=1),
    )
    expired = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=work_date + timedelta(days=1),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.REJECTED,
        correction_deadline=timezone.now() - timedelta(seconds=1),
    )
    client.force_login(employee.user)

    accepted = client.put(
        f"/api/v1/work-in-office/{rejected.pk}/",
        {
            "work_date": str(rejected.work_date),
            "location_choice": WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            "note": "Corrected inside deadline",
            "version": rejected.version,
        },
        content_type="application/json",
    )
    blocked = client.put(
        f"/api/v1/work-in-office/{expired.pk}/",
        {
            "work_date": str(expired.work_date),
            "location_choice": WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            "note": "Too late",
            "version": expired.version,
        },
        content_type="application/json",
    )

    assert accepted.status_code == 200
    assert accepted.json()["review_state"] == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
    assert blocked.status_code == 400
    assert "deadline has passed" in str(blocked.json())


def test_planner_preview_save_and_delete_stay_owner_private(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        expected_fraction=Decimal("0.50"),
    )
    previewed = preview(employee=employee, start=today, end=today)
    assert previewed == [{"date": today, "reason": None, "existing": False, "eligible": True}]
    records = save_intentions(
        employee=employee,
        start=today,
        end=today,
        location="office",
        commitment="firm",
        note="Private",
    )
    assert len(records) == 1
    assert records[0].employee_id == employee.pk
    assert (
        len(
            save_intentions(
                employee=employee,
                start=today,
                end=today,
                location="office",
                commitment="firm",
            )
        )
        == 0
    )
    assert WorkIntentionSeries.objects.count() == 1
    client.force_login(employee.user)
    projected = client.get("/api/v1/planner/projection/")
    assert projected.status_code == 200
    assert projected.json()["minimum_planned_fraction"] == "0.50"
    assert projected.json()["flexible_office_days"] == 0
    other = membership(email="other@example.com", company=company)
    client.force_login(other.user)
    assert (
        client.delete(f"/api/v1/planner/{records[0].pk}/?version={records[0].version}").status_code
        == 404
    )
    client.force_login(employee.user)
    deleted = client.delete(f"/api/v1/planner/{records[0].pk}/?version={records[0].version}")
    assert deleted.status_code == 204


def test_planner_projection_and_save_failures_recover_without_logging_private_content(
    client, db, monkeypatch, caplog
):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    private_error = "PRIVATE_PLANNER_FAILURE_SENTINEL"

    def fail_planner(**_kwargs):
        raise RuntimeError(private_error)

    monkeypatch.setattr("apps.work_logs.planner_views.projection", fail_planner)
    monkeypatch.setattr("apps.work_logs.planner_views.save_intentions", fail_planner)
    caplog.set_level(logging.ERROR, logger="wio.planner")
    client.force_login(employee.user)

    projected = client.get("/api/v1/planner/projection/")
    saved = client.post(
        "/api/v1/planner/",
        {
            "start_date": today.isoformat(),
            "location": "office",
            "commitment": "firm",
            "note": "private note that must not appear in failure logs",
        },
        content_type="application/json",
    )

    assert projected.status_code == 503
    assert projected.json()["detail"] == (
        "Planner projection is temporarily unavailable. Try again later."
    )
    assert saved.status_code == 503
    assert saved.json()["detail"] == "Planner save is temporarily unavailable. Try again later."
    assert private_error not in caplog.text
    assert "private note that must not appear" not in caplog.text
    assert [record.message for record in caplog.records if record.name == "wio.planner"] == [
        "planner_projection_failed",
        "planner_save_failed",
    ]
    assert {record.error_class for record in caplog.records if record.name == "wio.planner"} == {
        "RuntimeError"
    }


def test_planner_notes_reject_html_on_create_and_edit(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        expected_fraction=Decimal("0.50"),
    )

    with pytest.raises(ValidationError, match="plain text"):
        save_intentions(
            employee=employee,
            start=today,
            end=today,
            location="office",
            commitment="firm",
            note="<b>Private</b>",
        )
    record = save_intentions(
        employee=employee,
        start=today,
        end=today,
        location="office",
        commitment="firm",
        note="Private",
    )[0]

    with pytest.raises(ValidationError, match="plain text"):
        edit_intention(
            employee=employee,
            record_id=record.pk,
            version=record.version,
            scope="one",
            note="<script>private</script>",
        )


def test_planner_skip_existing_preserves_private_notes_until_explicit_replace(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        expected_fraction=Decimal("0.50"),
    )
    original = save_intentions(
        employee=employee,
        start=today,
        end=today,
        location="office",
        commitment="firm",
        note="Keep this private note",
    )[0]

    skipped = save_intentions(
        employee=employee,
        start=today,
        end=today,
        location="home",
        commitment="flexible",
        note="Replacement note",
    )
    original.refresh_from_db()

    assert skipped == []
    assert original.note == "Keep this private note"
    assert original.location == "office"
    assert original.commitment == "firm"

    replaced = save_intentions(
        employee=employee,
        start=today,
        end=today,
        location="home",
        commitment="flexible",
        note="Replacement note",
        replace=True,
    )
    original.refresh_from_db()

    assert [record.pk for record in replaced] == [original.pk]
    assert original.note == "Replacement note"
    assert original.location == "home"
    assert original.commitment == "flexible"


def test_planner_bulk_replace_rolls_back_all_rows_when_one_write_fails(db, monkeypatch):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    start = today + timedelta(days=(7 - today.weekday()) % 7)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        expected_fraction=Decimal("0.50"),
    )
    first = WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=start,
        location="office",
        commitment="firm",
        note="First stays",
    )
    second = WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=start + timedelta(days=1),
        location="office",
        commitment="firm",
        note="Second stays",
    )
    original_save = WorkIntentionOccurrence.save

    def fail_on_second_row(self, *args, **kwargs):
        if self.pk == second.pk:
            raise RuntimeError("injected write failure")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(WorkIntentionOccurrence, "save", fail_on_second_row)

    with pytest.raises(RuntimeError, match="injected write failure"):
        save_intentions(
            employee=employee,
            start=start,
            end=start + timedelta(days=1),
            location="home",
            commitment="flexible",
            note="Replacement note",
            replace=True,
        )

    monkeypatch.undo()
    first.refresh_from_db()
    second.refresh_from_db()

    assert first.location == "office"
    assert first.commitment == "firm"
    assert first.note == "First stays"
    assert second.location == "office"
    assert second.commitment == "firm"
    assert second.note == "Second stays"


def test_duplicate_wio_and_intention_dates_are_stopped_by_database_constraints(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    WorkInOfficeRecord.objects.create(employee=employee, work_date=today)
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today,
        location="office",
        commitment="firm",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        WorkInOfficeRecord.objects.create(employee=employee, work_date=today)
    with pytest.raises(IntegrityError), transaction.atomic():
        WorkIntentionOccurrence.objects.create(
            employee=employee,
            date=today,
            location="home",
            commitment="flexible",
        )


def test_wio_and_planner_mutations_reject_missing_version(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    client.force_login(employee.user)
    created = client.post(
        "/api/v1/work-in-office/",
        {"work_date": today.isoformat()},
        content_type="application/json",
    ).json()

    wio_update = client.put(
        f"/api/v1/work-in-office/{created['id']}/",
        {"work_date": today.isoformat(), "location_choice": "not_in_office"},
        content_type="application/json",
    )
    wio_delete = client.delete(f"/api/v1/work-in-office/{created['id']}/")
    intention = WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today,
        location="office",
        commitment="firm",
    )
    planner_update = client.patch(
        f"/api/v1/planner/{intention.pk}/",
        {"location": "home", "commitment": "flexible"},
        content_type="application/json",
    )
    planner_delete = client.delete(f"/api/v1/planner/{intention.pk}/")

    assert wio_update.status_code == 409
    assert "Version is required" in wio_update.json()["detail"]
    assert wio_delete.status_code == 409
    assert "Version is required" in wio_delete.json()["detail"]
    assert planner_update.status_code == 409
    assert planner_delete.status_code == 409
    assert "Version is required" in planner_delete.json()["detail"]


def test_planner_future_edit_splits_without_rewriting_earlier_occurrence(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    series = WorkIntentionSeries.objects.create(
        employee=employee,
        location="office",
        commitment="firm",
        starts_on=today,
        ends_on=today + timedelta(days=2),
    )
    earlier = WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today,
        location="office",
        commitment="firm",
        series=series,
    )
    later = WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today + timedelta(days=1),
        location="office",
        commitment="firm",
        series=series,
    )
    updated = edit_intention(
        employee=employee,
        record_id=later.pk,
        version=later.version,
        scope="future",
        location="home",
        commitment="flexible",
    )
    earlier.refresh_from_db()
    later.refresh_from_db()
    series.refresh_from_db()
    assert len(updated) == 1
    assert earlier.series_id == series.pk
    assert earlier.location == "office"
    assert series.ends_on == today
    assert later.series_id != series.pk
    assert later.location == "home"
    assert later.commitment == "flexible"


def test_planner_purge_removes_linked_series_idempotently(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    period = active_period(company, today)
    series = WorkIntentionSeries.objects.create(
        employee=employee,
        location="office",
        commitment="firm",
        starts_on=today,
        ends_on=today,
        note="Private",
    )
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today,
        location="office",
        commitment="firm",
        note="Private",
        series=series,
    )
    assert purge_intentions_for_period(period) == {
        "occurrences_purged": 1,
        "series_purged": 1,
    }
    assert not WorkIntentionSeries.objects.filter(pk=series.pk).exists()
    assert purge_intentions_for_period(period) == {
        "occurrences_purged": 0,
        "series_purged": 0,
    }


@override_settings(WIO_APP_URL="https://app.example.test")
def test_planner_purge_notification_excludes_private_intention_content(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    unaffected = membership(email="unaffected@example.com", company=company)
    UserPreference.objects.create(user=employee.user, language=UserPreference.Language.VIETNAMESE)
    today = timezone.localdate()
    period = active_period(company, today)
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today,
        location="office",
        commitment="firm",
        note="Secret pizza plan",
    )

    assert notify_planner_purge(period) == {"notifications_sent": 1}

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [employee.user.email]
    content = f"{mail.outbox[0].subject}\n{mail.outbox[0].body}"
    assert unaffected.user.email not in content
    assert period.name in content
    assert period.start_date.isoformat() in content
    assert period.end_date.isoformat() in content
    assert period.reconciliation_cutoff.isoformat() in content
    assert "https://app.example.test/planner" in content
    assert "Secret pizza plan" not in content
    assert "office" not in content
    assert "firm" not in content


@override_settings(WIO_APP_URL="https://app.example.test")
def test_planner_purge_notification_command_runs(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    period = active_period(company, today)
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today,
        location="home",
        commitment="flexible",
        note="Private note",
    )
    output = StringIO()

    call_command("notify_planner_purge", period.pk, stdout=output)

    assert "Sent 1 Planner purge notification(s)." in output.getvalue()
    assert len(mail.outbox) == 1


@override_settings(WIO_APP_URL="https://app.example.test")
def test_planner_purge_notification_failure_is_controlled_and_private_free(db, monkeypatch, caplog):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    period = active_period(company, today)
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today,
        location="home",
        commitment="flexible",
        note="PRIVATE_PLANNER_PURGE_NOTE",
    )

    def fail_send_mail(**_kwargs):
        raise RuntimeError("PRIVATE_SMTP_PURGE_SENTINEL")

    monkeypatch.setattr("apps.work_logs.planner.send_mail", fail_send_mail)
    caplog.set_level(logging.ERROR, logger="wio.planner")

    with pytest.raises(CommandError, match="Planner purge notification delivery failed."):
        call_command("notify_planner_purge", period.pk)

    assert "PRIVATE_SMTP_PURGE_SENTINEL" not in caplog.text
    assert "PRIVATE_PLANNER_PURGE_NOTE" not in caplog.text
    assert [record.message for record in caplog.records if record.name == "wio.planner"] == [
        "planner_purge_notification_failed"
    ]
    assert {record.error_class for record in caplog.records if record.name == "wio.planner"} == {
        "RuntimeError"
    }


def test_finalize_fiscal_period_command_runs_registered_sequence(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    day = timezone.localdate() - timedelta(days=1)
    period = FiscalPeriod.objects.create(
        company=company,
        name="Closed",
        start_date=day,
        end_date=day,
        state=FiscalPeriod.State.RECONCILIATION,
        reconciliation_cutoff=timezone.now() - timedelta(seconds=1),
    )
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=day - timedelta(days=31),
        expected_fraction=Decimal("0.50"),
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=day,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        submitted_at=timezone.now(),
    )
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=day,
        location="home",
        commitment="flexible",
        note="Private note",
    )
    output = StringIO()

    call_command("finalize_fiscal_period", period.pk, stdout=output)

    period.refresh_from_db()
    record.refresh_from_db()
    assert f"Finalized Closed ({period.pk})." in output.getvalue()
    assert period.state == FiscalPeriod.State.FINAL
    assert record.review_state == WorkInOfficeRecord.ReviewState.EXPIRED_PENDING
    assert FinalizedLedgerRevision.objects.filter(period=period, employee=employee).count() == 1
    assert not WorkIntentionOccurrence.objects.filter(employee=employee).exists()


def test_finalize_fiscal_period_command_fails_cleanly_before_cutoff(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    period = FiscalPeriod.objects.create(
        company=company,
        name="Open",
        start_date=timezone.localdate(),
        end_date=timezone.localdate(),
        state=FiscalPeriod.State.RECONCILIATION,
        reconciliation_cutoff=timezone.now() + timedelta(days=1),
    )

    with pytest.raises(CommandError, match="Fiscal period cutoff has not passed."):
        call_command("finalize_fiscal_period", period.pk)
    with pytest.raises(CommandError, match=f"Fiscal period {period.pk + 100} does not exist."):
        call_command("finalize_fiscal_period", period.pk + 100)

    period.refresh_from_db()
    assert period.state == FiscalPeriod.State.RECONCILIATION


def test_report_and_preference_api_contracts(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        expected_fraction=Decimal("0.50"),
    )
    client.force_login(employee.user)
    report = client.get(
        f"/api/v1/reports/?start_date={today.isoformat()}&end_date={today.isoformat()}"
    )
    assert report.status_code == 200
    assert report.json()["expected_fraction_sum"] == "0.50"
    initial_preferences = client.get("/api/v1/preferences/")
    assert initial_preferences.status_code == 200
    assert initial_preferences.json()["version"] == 1
    saved = client.put(
        "/api/v1/preferences/",
        {
            "theme": "dark",
            "language": "vi",
            "reduced_motion": True,
            "week_start": 1,
            "version": initial_preferences.json()["version"],
        },
        content_type="application/json",
    )
    assert saved.status_code == 200
    assert saved.json()["version"] == 2
    missing_version = client.put(
        "/api/v1/preferences/",
        {"theme": "light", "language": "en", "reduced_motion": False, "week_start": 1},
        content_type="application/json",
    )
    stale = client.put(
        "/api/v1/preferences/",
        {
            "theme": "light",
            "language": "en",
            "reduced_motion": False,
            "week_start": 1,
            "version": initial_preferences.json()["version"],
        },
        content_type="application/json",
    )
    assert missing_version.status_code == 409
    assert missing_version.json()["detail"] == "Version is required for preferences."
    assert stale.status_code == 409
    assert stale.json()["detail"] == "Preferences changed. Reload latest state and retry."
    assert client.get("/api/v1/preferences/").json()["language"] == "vi"
    invalid = client.put(
        "/api/v1/preferences/",
        {"planner_location": "remote", "version": saved.json()["version"]},
        content_type="application/json",
    )
    assert invalid.status_code == 400
    metadata = client.get("/api/v1/work-in-office/meta/")
    assert metadata.status_code == 200
    assert metadata.json()["fiscal_period"]["name"] == "Current"
    profile = client.get("/api/v1/profile/")
    assert profile.status_code == 200
    assert isinstance(profile.json(), dict), profile.json()
    assert profile.json()["company"] == "Yawn"
    assert profile.json()["policy"]["assignment_status"] == "benched"


def test_report_range_errors_are_clear_for_ui_and_csv(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    period = active_period(company, today)
    client.force_login(employee.user)

    missing_end = client.get(f"/api/v1/reports/?start_date={today.isoformat()}")
    invalid_date = client.get("/api/v1/reports/?start_date=nope&end_date=2026-07-23")
    cross_period = client.get(
        "/api/v1/reports/csv/"
        f"?start_date={period.start_date.isoformat()}"
        f"&end_date={(period.end_date + timedelta(days=1)).isoformat()}"
    )

    assert missing_end.status_code == 400
    assert missing_end.json()["detail"] == "Report range requires both start_date and end_date."
    assert invalid_date.status_code == 400
    assert invalid_date.json()["detail"] == "Report dates must use ISO format YYYY-MM-DD."
    assert cross_period.status_code == 400
    assert cross_period.json()["detail"] == "Cross-period calculations are not supported."


def test_report_and_csv_failures_recover_without_logging_private_content(
    client, db, monkeypatch, caplog
):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    private_error = "PRIVATE_REPORT_EXPORT_SENTINEL"

    def fail_report(**_kwargs):
        raise RuntimeError(private_error)

    monkeypatch.setattr("apps.work_logs.report_views.report_for", fail_report)
    caplog.set_level(logging.ERROR, logger="wio.reports")
    client.force_login(employee.user)

    report = client.get("/api/v1/reports/")
    csv_export = client.get("/api/v1/reports/csv/")

    assert report.status_code == 503
    assert report.json()["detail"] == "Report is temporarily unavailable. Try again later."
    assert csv_export.status_code == 503
    assert csv_export.json()["detail"] == (
        "Report export is temporarily unavailable. Try again later."
    )
    assert private_error not in caplog.text
    assert [record.message for record in caplog.records if record.name == "wio.reports"] == [
        "report_generation_failed",
        "report_export_failed",
    ]
    assert {record.error_class for record in caplog.records if record.name == "wio.reports"} == {
        "RuntimeError"
    }


def test_report_dashboard_csv_and_frozen_revision_share_raw_denominator_fixture(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    start = today - timedelta(days=2)
    period = FiscalPeriod.objects.create(
        company=company,
        name="Current",
        start_date=start,
        end_date=today,
        state=FiscalPeriod.State.ACTIVE,
    )
    rule = ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=start,
        expected_fraction=Decimal("0.60"),
    )
    for offset in (0, 1):
        WorkInOfficeRecord.objects.create(
            employee=employee,
            work_date=start + timedelta(days=offset),
            location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
            review_state=WorkInOfficeRecord.ReviewState.APPROVED,
            approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
        )
    WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
    )
    client.force_login(employee.user)

    report = client.get(
        f"/api/v1/reports/?start_date={start.isoformat()}&end_date={today.isoformat()}"
    ).json()
    dashboard = client.get("/api/v1/dashboard/ratio/").json()
    csv_body = client.get(
        f"/api/v1/reports/csv/?start_date={start.isoformat()}&end_date={today.isoformat()}"
    ).content.decode("utf-8-sig")
    csv_rows = list(csv.reader(StringIO(csv_body)))
    header_index = csv_rows.index(
        [
            "Date",
            "Eligible",
            "Reason",
            "Expected fraction",
            "Approved credit",
            "Self-submitted credit",
            "Review state",
            "Approval method",
            "Source",
        ]
    )
    ledger_rows = csv_rows[header_index + 1 :]

    assert report["approved_days"] == "2"
    assert report["self_submitted_days"] == "3"
    assert report["expected_fraction_sum"] == "1.80"
    assert report["percentage"] == "111.12"
    assert report["ratio_display"] == "111.12%"
    assert report["balance"] == "0.20"
    assert dashboard["approved_days"] == "2"
    assert dashboard["self_submitted_days"] == "3"
    assert dashboard["expected_display"] == "1.80"
    assert dashboard["ratio_display"] == "111.12%"
    assert dashboard["balance"] == "0.20"
    assert sum(Decimal(row[3]) for row in ledger_rows) == Decimal("1.80")
    assert sum(Decimal(row[4]) for row in ledger_rows) == Decimal("2")

    period.state = FiscalPeriod.State.RECONCILIATION
    period.save(update_fields=["state"])
    assert freeze_period_ledgers(period) == {"revisions_created": 1}
    period.state = FiscalPeriod.State.FINAL
    period.save(update_fields=["state"])
    rule.expected_fraction = Decimal("0.10")
    rule.save(update_fields=["expected_fraction"])

    frozen_report = client.get(
        f"/api/v1/reports/?start_date={start.isoformat()}&end_date={today.isoformat()}"
    ).json()
    frozen_dashboard = client.get("/api/v1/dashboard/ratio/").json()

    assert FinalizedLedgerRevision.objects.get(period=period, employee=employee).summary == {
        "approved_days": "2",
        "self_submitted_days": "3",
        "expected_fraction_sum": "1.80",
        "percentage": "111.12",
    }
    assert frozen_report["revision"] == 1
    assert frozen_report["expected_fraction_sum"] == "1.80"
    assert frozen_report["percentage"] == "111.12"
    assert frozen_dashboard["revision"] == 1
    assert frozen_dashboard["expected_display"] == "1.80"
    assert frozen_dashboard["ratio_display"] == "111.12%"


def test_dashboard_modules_keep_fiscal_empty_state_and_month_independent(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        expected_fraction=Decimal("0.50"),
    )
    client.force_login(employee.user)

    ratio = client.get("/api/v1/dashboard/ratio/")
    assert ratio.status_code == 200
    assert ratio.json()["available"] is True
    assert "balance" in ratio.json()

    month = client.get(f"/api/v1/dashboard/activity/?year={today.year}&month={today.month}")
    assert month.status_code == 200
    assert set(month.json()) == {"records", "intentions"}

    heatmap = client.get(f"/api/v1/dashboard/heatmap/?year={today.year}&month={today.month}")
    assert heatmap.status_code == 200
    assert heatmap.json()[0].keys() >= {
        "date",
        "record_id",
        "review_state",
        "intention",
        "commitment",
        "ineligible_reason",
        "unavailable_reason",
        "action",
    }

    FiscalPeriod.objects.all().delete()
    empty_ratio = client.get("/api/v1/dashboard/ratio/")
    assert empty_ratio.status_code == 200
    assert empty_ratio.json() == {
        "available": False,
        "message": "No active fiscal period covers today.",
    }


def test_dashboard_heatmap_exposes_intention_commitment(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=date(2026, 7, 20),
        location="office",
        commitment="firm",
    )
    client.force_login(employee.user)

    response = client.get("/api/v1/dashboard/heatmap/?year=2026&month=7")

    assert response.status_code == 200
    days = {item["date"]: item for item in response.json()}
    assert days["2026-07-20"]["commitment"] == "firm"
    assert days["2026-07-21"]["commitment"] is None


def test_target_size_heatmap_uses_bulk_eligibility_without_per_day_queries(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    month_start = date(2026, 7, 1)
    dates = [month_start + timedelta(days=offset) for offset in range(31)]
    WorkInOfficeRecord.objects.bulk_create(
        [
            WorkInOfficeRecord(
                employee=employee,
                work_date=current,
                location_choice=WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE,
                review_state=WorkInOfficeRecord.ReviewState.NOT_REQUIRED,
            )
            for current in dates
        ]
    )
    WorkIntentionOccurrence.objects.bulk_create(
        [
            WorkIntentionOccurrence(
                employee=employee,
                date=current,
                location="office",
                commitment="flexible",
            )
            for current in dates
        ]
    )
    CompanyHoliday.objects.create(company=company, date=date(2026, 7, 6), name="Founders")
    ApprovedLeave.objects.create(
        employee=employee,
        effective_from=date(2026, 7, 7),
        effective_to=date(2026, 7, 8),
        reason="private leave reason",
    )
    RemoteWorkException.objects.create(
        employee=employee,
        effective_from=date(2026, 7, 8),
        effective_to=date(2026, 7, 9),
        reason="private remote reason",
    )
    client.force_login(employee.user)

    with CaptureQueriesContext(connection) as queries:
        response = client.get("/api/v1/dashboard/heatmap/?year=2026&month=7")

    assert response.status_code == 200
    assert len(queries) <= 10
    days = {item["date"]: item for item in response.json()}
    assert len(days) == 31
    assert days["2026-07-04"]["ineligible_reason"] == "Weekend"
    assert days["2026-07-06"]["ineligible_reason"] == "Public holiday"
    assert days["2026-07-07"]["ineligible_reason"] == "Approved leave"
    assert days["2026-07-08"]["ineligible_reason"] == (
        "Approved leave; Approved remote-work exception"
    )
    assert days["2026-07-09"]["ineligible_reason"] == "Approved remote-work exception"
    assert "private leave reason" not in response.content.decode("utf-8")
    assert "private remote reason" not in response.content.decode("utf-8")


def test_target_size_report_export_and_projection_do_not_add_per_day_queries(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    period = active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=period.start_date,
        expected_fraction=Decimal("0.50"),
    )
    WorkInOfficeRecord.objects.bulk_create(
        [
            WorkInOfficeRecord(
                employee=employee,
                work_date=period.start_date + timedelta(days=offset),
                location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
                review_state=WorkInOfficeRecord.ReviewState.APPROVED,
                approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
            )
            for offset in range((today - period.start_date).days + 1)
        ]
    )
    WorkIntentionOccurrence.objects.bulk_create(
        [
            WorkIntentionOccurrence(
                employee=employee,
                date=today + timedelta(days=offset),
                location="office",
                commitment="flexible",
            )
            for offset in range((period.end_date - today).days + 1)
        ]
    )

    def report_export_queries(day_count):
        start = today - timedelta(days=day_count - 1)
        with CaptureQueriesContext(connection) as queries:
            report = report_for(employee=employee, start_date=start, end_date=today)
            response = csv_response(report, start_date=start, end_date=today)
        assert response.status_code == 200
        assert len(report["ledger"]) == day_count
        return len(queries)

    def projection_queries():
        with CaptureQueriesContext(connection) as queries:
            projected = projection(employee=employee)
        assert projected["maximum_planned_fraction"] != "0"
        return len(queries)

    assert report_export_queries(31) == report_export_queries(7)
    assert projection_queries() <= 10


def test_dashboard_ratio_keeps_verified_progress_when_future_projection_has_policy_gap(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today - timedelta(days=31),
        effective_to=today,
        expected_fraction=Decimal("0.50"),
    )
    WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
    )
    client.force_login(employee.user)

    response = client.get("/api/v1/dashboard/ratio/")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["approved_days"] == "1"
    assert body["ratio_display"].endswith("%")
    assert body["remaining_eligible_days"] is None


def test_csv_escapes_dynamic_formula_cells():
    report = {
        "period": SimpleNamespace(name="=danger", pk=1, state="active"),
        "revision": None,
        "ledger": [
            {
                "date": "2026-07-23",
                "eligible": True,
                "reason": "+danger",
                "expected_fraction": "0.50",
                "approval_credit": "0",
            }
        ],
    }
    response = csv_response(
        report,
        start_date=date(2026, 7, 23),
        end_date=date(2026, 7, 23),
    )
    body = response.content.decode("utf-8")
    assert "'=danger" in body
    assert "'+danger" in body


def test_csv_localizes_vietnamese_metadata_and_values():
    report = {
        "period": SimpleNamespace(name="FY26", pk=1, state="reconciliation"),
        "revision": None,
        "ledger": [
            {
                "date": "2026-07-23",
                "eligible": False,
                "reason": None,
                "expected_fraction": "0.00",
                "approval_credit": "0",
            }
        ],
    }
    response = csv_response(
        report,
        start_date=date(2026, 7, 23),
        end_date=date(2026, 7, 23),
        language="vi",
    )
    body = response.content.decode("utf-8")

    assert body.startswith("\ufeff")
    assert "Kỳ tài chính,FY26" in body
    assert "Trạng thái kỳ,Đang đối soát" in body
    assert "Khoảng ngày,2026-07-23 đến 2026-07-23" in body
    assert "Bản chốt,đang tính" in body
    assert "Ngày,Đủ điều kiện,Lý do,Phần kỳ vọng,Tín dụng đã duyệt" in body
    assert "2026-07-23,Không,,0.00,0" in body


def test_csv_excludes_wio_notes_and_private_planner_data(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    day = date(2026, 7, 23)
    FiscalPeriod.objects.create(
        company=company,
        name="FY26",
        start_date=day,
        end_date=day,
        state=FiscalPeriod.State.ACTIVE,
    )
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=day,
        expected_fraction=Decimal("1.00"),
    )
    WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=day,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
        note="EMPLOYEE_TO_APPROVER_SECRET",
        approver_note="MANAGER_PRIVATE_REASON_SECRET",
    )
    series = WorkIntentionSeries.objects.create(
        employee=employee,
        location="home",
        commitment="flexible",
        weekdays=[day.weekday()],
        starts_on=day,
        ends_on=day,
        note="PLANNER_SERIES_SECRET",
    )
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=day,
        location="home",
        commitment="flexible",
        note="PLANNER_OCCURRENCE_SECRET",
        series=series,
    )

    report = report_for(employee=employee, start_date=day, end_date=day)
    response = csv_response(report, start_date=day, end_date=day)
    body = response.content.decode("utf-8")

    assert "2026-07-23,Yes,,1.00,1" in body
    assert "EMPLOYEE_TO_APPROVER_SECRET" not in body
    assert "MANAGER_PRIVATE_REASON_SECRET" not in body
    assert "PLANNER_SERIES_SECRET" not in body
    assert "PLANNER_OCCURRENCE_SECRET" not in body
    assert "flexible" not in body
    assert "home" not in body


def test_final_report_uses_frozen_wio_state_after_record_changes(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    day = date(2026, 7, 23)
    period = FiscalPeriod.objects.create(
        company=company,
        name="Closed",
        start_date=day,
        end_date=day,
        state=FiscalPeriod.State.RECONCILIATION,
    )
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=day,
        expected_fraction=Decimal("1.00"),
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=day,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
    )
    assert freeze_period_ledgers(period) == {"revisions_created": 1}
    period.state = FiscalPeriod.State.FINAL
    period.save(update_fields=["state", "updated_at"])

    record.review_state = WorkInOfficeRecord.ReviewState.REJECTED
    record.location_choice = WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE
    record.approval_method = None
    record.version += 1
    record.save(
        update_fields=[
            "review_state",
            "location_choice",
            "approval_method",
            "version",
            "updated_at",
        ]
    )

    report = report_for(employee=employee, start_date=day, end_date=day)

    assert report["revision"].ledger[0]["review_state"] == WorkInOfficeRecord.ReviewState.APPROVED
    assert report["ledger"][0]["review_state"] == WorkInOfficeRecord.ReviewState.APPROVED
    assert report["ledger"][0]["location_choice"] == WorkInOfficeRecord.LocationChoice.IN_OFFICE
    assert report["approved_days"] == Decimal("1")


def test_audited_reopen_creates_linked_successor_revision_without_erasing_history(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    day = timezone.localdate() - timedelta(days=1)
    period = FiscalPeriod.objects.create(
        company=company,
        name="Closed",
        start_date=day,
        end_date=day,
        reconciliation_cutoff=timezone.now() - timedelta(seconds=1),
        state=FiscalPeriod.State.RECONCILIATION,
    )
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=day - timedelta(days=31),
        expected_fraction=Decimal("1.00"),
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=day,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
    )
    steps = {"freeze_ledgers": freeze_period_ledgers}

    run_finalization(period.pk, steps)
    first = FinalizedLedgerRevision.objects.get(period=period, employee=employee, revision=1)

    period.refresh_from_db()
    period.state = FiscalPeriod.State.RECONCILIATION
    period.reopened_at = timezone.now()
    period.save(update_fields=["state", "reopened_at", "updated_at"])
    record.location_choice = WorkInOfficeRecord.LocationChoice.NOT_IN_OFFICE
    record.review_state = WorkInOfficeRecord.ReviewState.NOT_REQUIRED
    record.approval_method = None
    record.version += 1
    record.save(
        update_fields=[
            "location_choice",
            "review_state",
            "approval_method",
            "version",
            "updated_at",
        ]
    )

    run_finalization(period.pk, steps)
    run_finalization(period.pk, steps)

    revisions = list(
        FinalizedLedgerRevision.objects.filter(period=period, employee=employee).order_by(
            "revision"
        )
    )
    assert [revision.revision for revision in revisions] == [1, 2]
    assert revisions[1].predecessor == first
    assert revisions[0].ledger[0]["review_state"] == WorkInOfficeRecord.ReviewState.APPROVED
    assert revisions[1].ledger[0]["review_state"] == WorkInOfficeRecord.ReviewState.NOT_REQUIRED
    report = report_for(employee=employee, start_date=day, end_date=day)
    assert report["revision"] == revisions[1]
    assert report["approved_days"] == Decimal("0")


def test_finalization_runs_registered_steps_once(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    today = timezone.localdate()
    period = FiscalPeriod.objects.create(
        company=company,
        name="Closed",
        start_date=today - timedelta(days=60),
        end_date=today - timedelta(days=31),
        reconciliation_cutoff=timezone.now() - timedelta(seconds=1),
        state=FiscalPeriod.State.RECONCILIATION,
    )
    calls = []
    final = run_finalization(
        period.pk,
        {"first": lambda _: calls.append("first") or {"ok": True}},
    )
    assert final.state == FiscalPeriod.State.FINAL
    assert calls == ["first"]
    run_finalization(period.pk, {"first": lambda _: calls.append("again")})
    assert calls == ["first"]


def test_finalization_failure_retries_expiration_freeze_and_purge_without_duplicates(db, caplog):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    day = timezone.localdate() - timedelta(days=1)
    period = FiscalPeriod.objects.create(
        company=company,
        name="Closed",
        start_date=day,
        end_date=day,
        state=FiscalPeriod.State.RECONCILIATION,
        reconciliation_cutoff=timezone.now() - timedelta(seconds=1),
    )
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=day - timedelta(days=31),
        expected_fraction=Decimal("0.50"),
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=day,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        submitted_at=timezone.now(),
    )
    series = WorkIntentionSeries.objects.create(
        employee=employee,
        location="office",
        commitment="firm",
        starts_on=day,
        ends_on=day,
        note="Private",
    )
    WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=day,
        location="office",
        commitment="firm",
        note="Private",
        series=series,
    )
    purge_attempts = 0

    def flaky_purge(step_period):
        nonlocal purge_attempts
        purge_attempts += 1
        if purge_attempts == 1:
            raise RuntimeError("injected purge failure")
        return purge_intentions_for_period(step_period)

    steps = {
        "expire_unresolved_claims": lambda step_period: {
            "expired_claims": expire_pending_for_period(step_period)
        },
        "freeze_ledgers": freeze_period_ledgers,
        "purge_private_intentions": flaky_purge,
    }
    caplog.set_level(logging.ERROR, logger="wio.finalization")

    with pytest.raises(RuntimeError, match="injected purge failure"):
        run_finalization(period.pk, steps)

    assert "injected purge failure" not in caplog.text
    assert "Private" not in caplog.text
    assert [item.message for item in caplog.records if item.name == "wio.finalization"] == [
        "finalization_step_failed"
    ]
    failure_record = next(item for item in caplog.records if item.name == "wio.finalization")
    assert failure_record.step == "purge_private_intentions"
    assert failure_record.error_class == "RuntimeError"

    period.refresh_from_db()
    record.refresh_from_db()
    assert period.state == FiscalPeriod.State.RECONCILIATION
    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING
    assert not FinalizedLedgerRevision.objects.filter(period=period).exists()
    assert WorkIntentionOccurrence.objects.filter(series=series).exists()
    assert not FiscalFinalizationStep.objects.filter(period=period).exists()

    final = run_finalization(period.pk, steps)
    record.refresh_from_db()

    assert final.state == FiscalPeriod.State.FINAL
    assert record.review_state == WorkInOfficeRecord.ReviewState.EXPIRED_PENDING
    assert record.version == 2
    assert FinalizedLedgerRevision.objects.filter(period=period, employee=employee).count() == 1
    assert not WorkIntentionOccurrence.objects.filter(series=series).exists()
    assert not WorkIntentionSeries.objects.filter(pk=series.pk).exists()
    assert purge_attempts == 2
    assert FiscalFinalizationStep.objects.filter(period=period).count() == 3
    assert FiscalFinalizationStep.objects.get(
        period=period, key="expire_unresolved_claims"
    ).metadata == {"expired_claims": 1}
    assert FiscalFinalizationStep.objects.get(period=period, key="freeze_ledgers").metadata == {
        "revisions_created": 1
    }
    assert FiscalFinalizationStep.objects.get(
        period=period, key="purge_private_intentions"
    ).metadata == {"occurrences_purged": 1, "series_purged": 1}
