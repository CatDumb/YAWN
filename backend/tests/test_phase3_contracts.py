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
from django.db.models import QuerySet
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator

import apps.work_logs.finalization as finalization
from apps.accounts.models import Company, CompanyMembership, ManagerAssignment, User, UserPreference
from apps.audit.models import AuditEvent
from apps.work_logs.approvals import (
    approve_record,
    assign_pending_record,
    reject_scoped_record,
    role_membership,
    undo_approval,
)
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
from apps.work_logs.services import (
    reopen_fiscal_periods,
    reverse_approved_record,
    save_record,
    undo_self_approval,
)


def membership(*, email, company, role=CompanyMembership.Role.EMPLOYEE):
    user = User.objects.create_user(email=email)
    return CompanyMembership.objects.create(user=user, company=company, role=role)


@pytest.mark.parametrize(
    ("requested_role", "label", "membership_roles", "error"),
    [
        (CompanyMembership.Role.MANAGER, "manager", [CompanyMembership.Role.MANAGER], None),
        (CompanyMembership.Role.HR_ADMIN, "HR/admin", [CompanyMembership.Role.HR_ADMIN], None),
        (CompanyMembership.Role.MANAGER, "manager", [], "required"),
        (CompanyMembership.Role.HR_ADMIN, "HR/admin", [], "required"),
        (CompanyMembership.Role.MANAGER, "manager", [CompanyMembership.Role.EMPLOYEE], "required"),
        (CompanyMembership.Role.HR_ADMIN, "HR/admin", [CompanyMembership.Role.MANAGER], "required"),
        (
            CompanyMembership.Role.HR_ADMIN,
            "HR/admin",
            [CompanyMembership.Role.HR_ADMIN] * 2,
            "ambiguous",
        ),
    ],
)
def test_role_membership_matrix(db, requested_role, label, membership_roles, error):
    user = User.objects.create_user(email="role-membership@example.com")
    memberships = [
        CompanyMembership.objects.create(
            user=user,
            company=Company.objects.create(name=f"Company {index}", slug=f"company-{index}"),
            role=role,
        )
        for index, role in enumerate(membership_roles)
    ]

    if error:
        with pytest.raises(ValidationError, match=error):
            role_membership(user, requested_role, label)
    else:
        assert role_membership(user, requested_role, label) == memberships[0]


def test_approval_api_fails_closed_for_cross_role_company_ambiguity(client, db):
    user = User.objects.create_user(email="cross-role-manager@example.com")
    managed_company = Company.objects.create(name="Managed", slug="managed")
    other_company = Company.objects.create(name="Other", slug="other")
    manager = CompanyMembership.objects.create(
        user=user,
        company=managed_company,
        role=CompanyMembership.Role.MANAGER,
    )
    CompanyMembership.objects.create(
        user=user,
        company=other_company,
        role=CompanyMembership.Role.EMPLOYEE,
    )
    employee = membership(email="cross-role-employee@example.com", company=managed_company)
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot={"membership_id": manager.pk},
        submitted_at=timezone.now(),
    )
    client.force_login(user)

    assert client.get("/api/v1/approvals/").status_code == 403
    response = client.post(
        f"/api/v1/approvals/{record.pk}/approve/",
        {"version": record.version},
        content_type="application/json",
    )

    assert response.status_code == 400
    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING


def test_approval_openapi_requires_decision_request_body():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    operation = schema["paths"]["/api/v1/approvals/{id}/{action}/"]["post"]

    assert operation["requestBody"]["required"] is True
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    if "$ref" in request_schema:
        request_schema = schema["components"]["schemas"][request_schema["$ref"].rsplit("/", 1)[1]]
    assert "version" in request_schema["required"]


def test_wio_api_rejects_html_notes_on_create_and_update(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="wio-note@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    client.force_login(employee.user)

    created = client.post(
        "/api/v1/work-in-office/",
        {"work_date": today.isoformat(), "note": "<b>not plain text</b>"},
        content_type="application/json",
    )

    assert created.status_code == 400
    assert created.json()["note"] == ["Note must be plain text."]

    draft = client.post(
        "/api/v1/work-in-office/",
        {"work_date": today.isoformat(), "save_as_draft": True},
        content_type="application/json",
    ).json()
    updated = client.put(
        f"/api/v1/work-in-office/{draft['id']}/",
        {
            "work_date": today.isoformat(),
            "note": "<i>still not plain text</i>",
            "save_as_draft": True,
            "version": draft["version"],
        },
        content_type="application/json",
    )

    assert updated.status_code == 400
    assert updated.json()["note"] == ["Note must be plain text."]


def test_wio_openapi_documents_optional_draft_flag():
    schema = SchemaGenerator().get_schema(request=None, public=True)

    for path, method in (
        ("/api/v1/work-in-office/", "post"),
        ("/api/v1/work-in-office/{id}/", "put"),
    ):
        request_schema = schema["paths"][path][method]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        if "$ref" in request_schema:
            request_schema = schema["components"]["schemas"][
                request_schema["$ref"].rsplit("/", 1)[1]
            ]

        draft_flag = request_schema["properties"]["save_as_draft"]
        assert draft_flag["type"] == "boolean"
        assert draft_flag["default"] is False
        assert "save_as_draft" not in request_schema.get("required", [])


def test_approval_revalidates_stale_manager_scope_inside_mutation(db):
    company = Company.objects.create(name="Scope Recheck", slug="scope-recheck")
    employee = membership(email="scope-employee@example.com", company=company)
    manager = membership(
        email="scope-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    ManagerAssignment.objects.create(
        manager=manager,
        employee=employee,
        effective_from=timezone.localdate(),
    )
    record = save_record(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
    )
    CompanyMembership.objects.filter(pk=manager.pk).update(role=CompanyMembership.Role.EMPLOYEE)

    with pytest.raises(ValidationError, match="active manager"):
        approve_record(manager=manager, record_id=record.pk, version=record.version)

    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING


def active_period(company, today):
    return FiscalPeriod.objects.create(
        company=company,
        name="Current",
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=30),
        state=FiscalPeriod.State.ACTIVE,
    )


@pytest.mark.parametrize(
    ("role", "expected_state"),
    [
        (CompanyMembership.Role.MANAGER, WorkInOfficeRecord.ReviewState.PENDING),
        (
            CompanyMembership.Role.HR_ADMIN,
            WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
        ),
    ],
)
def test_privileged_submission_still_requires_manager_approval(client, db, role, expected_state):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(
        email="privileged@example.com",
        company=company,
        role=role,
    )
    if role == CompanyMembership.Role.MANAGER:
        supervisor = membership(
            email="supervisor@example.com",
            company=company,
            role=CompanyMembership.Role.MANAGER,
        )
        ManagerAssignment.objects.create(
            manager=supervisor,
            employee=employee,
            effective_from=timezone.localdate(),
        )
    record = save_record(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        actor=employee.user,
    )

    assert record.review_state == expected_state
    assert record.approval_method is None
    assert record.approved_by_snapshot == {}

    client.force_login(employee.user)
    response = client.post(
        f"/api/v1/work-in-office/{record.pk}/undo-self-approval/",
        {"version": record.version},
        content_type="application/json",
    )

    assert response.status_code == 400


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
    missing_version = client.post(
        f"/api/v1/approvals/{record.pk}/approve/",
        {},
        content_type="application/json",
    )
    blank_reason = client.post(
        f"/api/v1/approvals/{record.pk}/reject/",
        {"version": record.version, "reason": "   "},
        content_type="application/json",
    )
    assert missing_version.status_code == 409
    assert "Version is required" in missing_version.json()["detail"]
    assert blank_reason.status_code == 400
    approved = client.post(
        f"/api/v1/approvals/{record.pk}/approve/",
        {"version": record.version},
        content_type="application/json",
    )
    assert approved.status_code == 200
    assert approved.json()["review_state"] == WorkInOfficeRecord.ReviewState.APPROVED
    assert mail.outbox == []


def test_approval_detail_exposes_note_only_to_current_assigned_manager(client, db):
    company = Company.objects.create(name="Approval Detail", slug="approval-detail")
    employee = membership(email="detail-employee@example.com", company=company)
    assigned_manager = membership(
        email="detail-assigned@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    unassigned_manager = membership(
        email="detail-unassigned@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    hr = membership(
        email="detail-hr@example.com",
        company=company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        note="Badge reader outage; visitor log has proof.",
        approval_owner_snapshot={"membership_id": assigned_manager.pk},
        submitted_at=timezone.now(),
    )
    detail_url = f"/api/v1/approvals/{record.pk}/"

    client.force_login(assigned_manager.user)
    response = client.get(detail_url)
    assert response.status_code == 200
    assert response.json()["note"] == record.note
    assert "note" not in client.get("/api/v1/approvals/").json()[0]

    client.force_login(unassigned_manager.user)
    assert client.get(detail_url).status_code == 404

    client.force_login(hr.user)
    assert client.get(detail_url).status_code == 403

    record.approval_owner_snapshot = {"membership_id": unassigned_manager.pk}
    record.save(update_fields=["approval_owner_snapshot", "updated_at"])

    client.force_login(assigned_manager.user)
    assert client.get(detail_url).status_code == 404

    client.force_login(unassigned_manager.user)
    reassigned_response = client.get(detail_url)
    assert reassigned_response.status_code == 200
    assert reassigned_response.json()["note"] == record.note


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

    WorkInOfficeRecord.objects.filter(
        pk__in=[record.pk for record in manager_records[:10]]
    ).delete()
    first_ownership_page = client.get("/api/v1/approvals/ownership/")
    final_full_ownership_page = client.get("/api/v1/approvals/ownership/?page=2")

    assert len(first_ownership_page.json()) == 50
    assert first_ownership_page.headers["X-Has-Next"] == "true"
    assert len(final_full_ownership_page.json()) == 50
    assert final_full_ownership_page.headers["X-Has-Next"] == "false"


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
    record.refresh_from_db()
    assert record.approved_by_snapshot == {}
    assert AuditEvent.objects.filter(
        event_type="work_logs.approval_undone",
        target_type="work_logs.WorkInOfficeRecord",
        target_id=str(record.pk),
    ).exists()

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


def test_final_fiscal_period_blocks_every_wio_and_approval_mutation(db):
    company = Company.objects.create(name="Frozen", slug="frozen")
    manager = membership(
        email="frozen-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    hr = membership(
        email="frozen-hr@example.com",
        company=company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    employees = [
        membership(email=f"frozen-{index}@example.com", company=company) for index in range(5)
    ]
    start = date(2026, 1, 1)
    FiscalPeriod.objects.create(
        company=company,
        name="Frozen period",
        start_date=start,
        end_date=start + timedelta(days=10),
        reconciliation_cutoff=timezone.now() - timedelta(days=1),
        state=FiscalPeriod.State.FINAL,
    )
    for employee in employees:
        ManagerAssignment.objects.create(
            manager=manager,
            employee=employee,
            effective_from=start,
        )
    pending_for_approve = WorkInOfficeRecord.objects.create(
        employee=employees[0],
        work_date=start,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot={"membership_id": manager.pk},
    )
    pending_for_reject = WorkInOfficeRecord.objects.create(
        employee=employees[1],
        work_date=start + timedelta(days=1),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot={"membership_id": manager.pk},
    )
    pending_assignment = WorkInOfficeRecord.objects.create(
        employee=employees[2],
        work_date=start + timedelta(days=2),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
    )
    manager_approved = WorkInOfficeRecord.objects.create(
        employee=employees[3],
        work_date=start + timedelta(days=3),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
        approved_at=timezone.now(),
        approved_by_snapshot={"membership_id": manager.pk},
        approval_owner_snapshot={"membership_id": manager.pk},
    )
    self_approved = WorkInOfficeRecord.objects.create(
        employee=employees[4],
        work_date=start + timedelta(days=4),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.APPROVED,
        approval_method=WorkInOfficeRecord.ApprovalMethod.SELF_APPROVED,
        approved_at=timezone.now(),
        approved_by_snapshot={"membership_id": employees[4].pk},
    )

    with pytest.raises(ValidationError, match="fiscal period is final"):
        approve_record(
            manager=manager,
            record_id=pending_for_approve.pk,
            version=pending_for_approve.version,
        )
    with pytest.raises(ValidationError, match="fiscal period is final"):
        reject_scoped_record(
            manager=manager,
            record_id=pending_for_reject.pk,
            version=pending_for_reject.version,
            reason="No evidence",
        )
    with pytest.raises(ValidationError, match="fiscal period is final"):
        assign_pending_record(
            hr=hr,
            record_id=pending_assignment.pk,
            manager_id=manager.pk,
            version=pending_assignment.version,
            reason="Assign owner",
        )
    with pytest.raises(ValidationError, match="fiscal period is final"):
        undo_approval(
            manager=manager,
            record_id=manager_approved.pk,
            version=manager_approved.version,
        )
    with pytest.raises(ValidationError, match="fiscal period is final"):
        undo_self_approval(
            employee=employees[4],
            record_id=self_approved.pk,
            version=self_approved.version,
            actor=employees[4].user,
        )
    with pytest.raises(ValidationError, match="fiscal period is final"):
        reverse_approved_record(
            record=manager_approved,
            actor=hr.user,
            reason="Frozen correction",
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
    rejected_hr_owner = client.post(
        f"/api/v1/approvals/{record.pk}/assign/",
        {
            "version": record.version,
            "manager_membership_id": hr.pk,
            "reason": "HR must not become the hidden approval owner",
        },
        content_type="application/json",
    )
    assert rejected_hr_owner.status_code == 400
    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT
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


def test_hr_reassigns_owned_pending_claim_with_reason_and_history(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    first_manager = membership(
        email="first-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    next_manager = membership(
        email="next-manager@example.com",
        company=company,
        role=CompanyMembership.Role.MANAGER,
    )
    hr = membership(email="hr@example.com", company=company, role=CompanyMembership.Role.HR_ADMIN)
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot={"membership_id": first_manager.pk},
        submitted_at=timezone.now(),
    )
    client.force_login(hr.user)

    ownership = client.get("/api/v1/approvals/ownership/")
    reassigned = client.post(
        f"/api/v1/approvals/{record.pk}/assign/",
        {
            "version": record.version,
            "manager_membership_id": next_manager.pk,
            "reason": "Manager leave coverage",
        },
        content_type="application/json",
    )

    assert ownership.status_code == 200
    assert [item["id"] for item in ownership.json()] == [record.pk]
    assert reassigned.status_code == 200
    record.refresh_from_db()
    assert record.review_state == WorkInOfficeRecord.ReviewState.PENDING
    assert record.approval_owner_snapshot["membership_id"] == next_manager.pk
    event = AuditEvent.objects.get(event_type="work_logs.record_pending_reassigned")
    assert event.metadata["previous_manager_membership_id"] == first_manager.pk
    assert event.metadata["assigned_manager_membership_id"] == next_manager.pk
    assert event.metadata["reason"] == "Manager leave coverage"

    client.force_login(first_manager.user)
    assert client.get("/api/v1/approvals/").json() == []
    client.force_login(next_manager.user)
    assert [item["id"] for item in client.get("/api/v1/approvals/").json()] == [record.pk]


def test_employee_and_manager_audit_timelines_are_bounded_and_scoped(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    manager = membership(
        email="manager@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    outsider = membership(
        email="outsider@example.com", company=company, role=CompanyMembership.Role.MANAGER
    )
    record = WorkInOfficeRecord.objects.create(
        employee=employee,
        work_date=timezone.localdate(),
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot={"membership_id": manager.pk},
        submitted_at=timezone.now(),
    )
    AuditEvent.objects.bulk_create(
        [
            AuditEvent(
                event_type="work_logs.record_submitted",
                target_type="work_logs.WorkInOfficeRecord",
                target_id=str(record.pk),
                metadata={
                    "actor_role": "employee",
                    "revision": index,
                    "private_snapshot": f"SECRET-{index}",
                },
            )
            for index in range(51)
        ]
    )

    client.force_login(manager.user)
    first = client.get(f"/api/v1/approvals/{record.pk}/timeline/")
    second = client.get(f"/api/v1/approvals/{record.pk}/timeline/?page=2")
    assert first.status_code == 200
    assert len(first.json()["results"]) == 50
    assert first.json()["next_page"] == 2
    assert len(second.json()["results"]) == 1
    assert "SECRET" not in str(first.json())

    client.force_login(outsider.user)
    assert client.get(f"/api/v1/approvals/{record.pk}/timeline/").status_code == 404

    client.force_login(employee.user)
    detail = client.get(f"/api/v1/work-in-office/{record.pk}/")
    older = client.get(f"/api/v1/work-in-office/{record.pk}/timeline/?page=2")
    assert detail.status_code == 200
    assert len(detail.json()["audit_timeline"]) == 50
    assert detail.json()["audit_timeline_next_page"] == 2
    assert len(older.json()["results"]) == 1


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
        f"/api/v1/approvals/{pending.pk}/timeline/",
        "/api/v1/approvals/ownership/",
        "/api/v1/approvals/pending-assignment/",
        f"/api/v1/work-in-office/{pending.pk}/timeline/",
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
    assert client.get(f"/api/v1/approvals/{pending.pk}/timeline/").status_code == 403
    assert client.get("/api/v1/approvals/ownership/").status_code == 403
    assert client.get("/api/v1/approvals/pending-assignment/").status_code == 403
    assert client.get(f"/api/v1/work-in-office/{pending.pk}/timeline/").status_code == 200

    client.force_login(assigned_manager.user)
    approval_queue = client.get("/api/v1/approvals/")
    assert approval_queue.status_code == 200
    assert [item["id"] for item in approval_queue.json()] == [pending.pk]
    assert client.get(f"/api/v1/approvals/{pending.pk}/timeline/").status_code == 200
    assert client.get("/api/v1/approvals/ownership/").status_code == 403
    assert client.get(f"/api/v1/work-in-office/{pending.pk}/").status_code == 404
    assert "PLANNER_MATRIX_SECRET" not in str(client.get("/api/v1/planner/").json())

    client.force_login(unassigned_manager.user)
    assert client.get("/api/v1/approvals/").json() == []
    assert client.get(f"/api/v1/approvals/{pending.pk}/timeline/").status_code == 404
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
    assert client.get(f"/api/v1/approvals/{pending.pk}/timeline/").status_code == 404
    assert client.get(f"/api/v1/work-in-office/{pending.pk}/").status_code == 404
    assert "PLANNER_MATRIX_SECRET" not in str(client.get("/api/v1/planner/").json())

    client.force_login(hr.user)
    assert {item["id"] for item in client.get("/api/v1/approvals/ownership/").json()} == {
        pending.pk,
        pending_assignment.pk,
    }
    assert [item["id"] for item in client.get("/api/v1/approvals/pending-assignment/").json()] == [
        pending_assignment.pk
    ]
    assignees = client.get("/api/v1/approvals/assignees/").json()
    assert {item["id"] for item in assignees} == {assigned_manager.pk, unassigned_manager.pk}

    client.force_login(other_hr.user)
    assert client.get("/api/v1/approvals/ownership/").json() == []
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


def test_planner_save_skips_initially_ineligible_dates_without_creating_empty_series(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    active_period(company, today)
    monday = today + timedelta(days=(7 - today.weekday()) % 7)
    saturday = monday + timedelta(days=5)
    CompanyHoliday.objects.create(company=company, date=monday, name="Founders")
    ApprovedLeave.objects.create(
        employee=employee,
        effective_from=monday + timedelta(days=1),
        effective_to=monday + timedelta(days=1),
        reason="Private leave reason",
    )
    RemoteWorkException.objects.create(
        employee=employee,
        effective_from=monday + timedelta(days=2),
        effective_to=monday + timedelta(days=2),
        reason="Private remote reason",
    )

    previewed = preview(
        employee=employee,
        start=monday,
        end=saturday,
        weekdays=[0, 1, 2, 5],
    )
    records = save_intentions(
        employee=employee,
        start=monday,
        end=saturday,
        weekdays=[0, 1, 2, 5],
        location="office",
        commitment="firm",
        note="Must not be persisted",
    )

    assert [(item["date"], item["reason"]) for item in previewed] == [
        (monday, "Public holiday"),
        (monday + timedelta(days=1), "Approved leave"),
        (monday + timedelta(days=2), "Approved remote-work exception"),
        (saturday, "Weekend"),
    ]
    assert all(not item["eligible"] for item in previewed)
    assert records == []
    assert not WorkIntentionOccurrence.objects.filter(employee=employee).exists()
    assert not WorkIntentionSeries.objects.filter(employee=employee).exists()


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
        {"work_date": today.isoformat(), "save_as_draft": True},
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
    later_date = today + timedelta(days=1)
    while later_date.weekday() >= 5:
        later_date += timedelta(days=1)
    series = WorkIntentionSeries.objects.create(
        employee=employee,
        location="office",
        commitment="firm",
        starts_on=today,
        ends_on=later_date,
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
        date=later_date,
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
    assert series.ends_on == later_date - timedelta(days=1)
    assert later.series_id != series.pk
    assert later.location == "home"
    assert later.commitment == "flexible"


def test_planner_one_occurrence_override_survives_whole_series_edit(db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    series_date = today + timedelta(days=1)
    while series_date.weekday() >= 5:
        series_date += timedelta(days=1)
    series = WorkIntentionSeries.objects.create(
        employee=employee,
        location="office",
        commitment="firm",
        starts_on=today,
        ends_on=series_date,
        note="Original series",
    )
    override = WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today,
        location="office",
        commitment="firm",
        series=series,
        note="Original series",
    )
    series_member = WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=series_date,
        location="office",
        commitment="firm",
        series=series,
        note="Original series",
    )

    edit_intention(
        employee=employee,
        record_id=override.pk,
        version=override.version,
        scope="one",
        location="home",
        commitment="flexible",
        note="One-date override",
    )
    edit_intention(
        employee=employee,
        record_id=series_member.pk,
        version=series_member.version,
        scope="series",
        note="Updated series",
    )

    override.refresh_from_db()
    series_member.refresh_from_db()
    assert override.series_id is None
    assert (override.location, override.commitment, override.note) == (
        "home",
        "flexible",
        "One-date override",
    )
    assert series_member.note == "Updated series"


def test_planner_one_occurrence_override_survives_series_deletion(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    employee = membership(email="employee@example.com", company=company)
    today = timezone.localdate()
    series_date = today + timedelta(days=1)
    while series_date.weekday() >= 5:
        series_date += timedelta(days=1)
    series = WorkIntentionSeries.objects.create(
        employee=employee,
        location="office",
        commitment="firm",
        starts_on=today,
        ends_on=series_date,
    )
    override = WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=today,
        location="office",
        commitment="firm",
        series=series,
    )
    series_member = WorkIntentionOccurrence.objects.create(
        employee=employee,
        date=series_date,
        location="office",
        commitment="firm",
        series=series,
    )
    edit_intention(
        employee=employee,
        record_id=override.pk,
        version=override.version,
        scope="one",
        location="home",
        commitment="flexible",
        note="Keep after series deletion",
    )

    client.force_login(employee.user)
    deleted = client.delete(
        f"/api/v1/planner/{series_member.pk}/"
        f"?version={series_member.version}&scope=series&confirm=true"
    )

    assert deleted.status_code == 204
    assert not WorkIntentionSeries.objects.filter(pk=series.pk).exists()
    override.refresh_from_db()
    assert override.series_id is None
    assert (override.location, override.commitment, override.note) == (
        "home",
        "flexible",
        "Keep after series deletion",
    )


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
    invalid_week_start = client.put(
        "/api/v1/preferences/",
        {"week_start": 2, "version": saved.json()["version"]},
        content_type="application/json",
    )
    assert invalid_week_start.status_code == 400
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
    with pytest.raises(ValidationError, match="versions are immutable"):
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
    run_finalization(period.pk)
    first = FinalizedLedgerRevision.objects.get(period=period, employee=employee, revision=1)

    reopen_fiscal_periods(
        period_ids=[period.pk],
        actor=User.objects.create_superuser(email="revision-reopen@example.com"),
        reason="Correct finalized attendance evidence",
    )
    period.refresh_from_db()
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

    run_finalization(period.pk)
    run_finalization(period.pk)

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


def test_finalization_runs_fixed_steps_once(db, monkeypatch):
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
    monkeypatch.setattr(
        finalization,
        "expire_pending_for_period",
        lambda _: calls.append("expire") or 0,
    )
    monkeypatch.setattr(
        finalization,
        "freeze_period_ledgers",
        lambda _: calls.append("freeze") or {},
    )
    monkeypatch.setattr(
        finalization,
        "purge_intentions_for_period",
        lambda _: calls.append("purge") or {},
    )
    final = run_finalization(period.pk)
    assert final.state == FiscalPeriod.State.FINAL
    assert calls == ["expire", "freeze", "purge"]
    run_finalization(period.pk)
    assert calls == ["expire", "freeze", "purge"]


def test_finalization_locks_company_before_period(db, monkeypatch):
    company = Company.objects.create(name="Finalization Lock Co", slug="finalization-lock")
    today = timezone.localdate()
    period = FiscalPeriod.objects.create(
        company=company,
        name="Lock order",
        start_date=today - timedelta(days=60),
        end_date=today - timedelta(days=31),
        reconciliation_cutoff=timezone.now() - timedelta(seconds=1),
        state=FiscalPeriod.State.RECONCILIATION,
    )
    locked_models = []
    original_select_for_update = QuerySet.select_for_update

    def track_select_for_update(queryset, *args, **kwargs):
        locked_models.append(queryset.model)
        return original_select_for_update(queryset, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "select_for_update", track_select_for_update)

    run_finalization(period.pk)

    assert locked_models[:2] == [Company, FiscalPeriod]


def test_finalization_failure_retries_expiration_freeze_and_purge_without_duplicates(
    db, caplog, monkeypatch
):
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

    monkeypatch.setattr(finalization, "purge_intentions_for_period", flaky_purge)
    caplog.set_level(logging.ERROR, logger="wio.finalization")

    with pytest.raises(RuntimeError, match="injected purge failure"):
        run_finalization(period.pk)

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

    final = run_finalization(period.pk)
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
