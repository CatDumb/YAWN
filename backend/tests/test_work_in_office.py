from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership, ManagerAssignment, User
from apps.audit.models import AuditEvent
from apps.work_logs.models import WorkInOfficeRecord
from apps.work_logs.services import reject_record


@pytest.fixture
def employee_client(client, db):
    company = Company.objects.create(name="Yawn", slug="yawn")
    user = User.objects.create_user(email="employee@example.com")
    membership = CompanyMembership.objects.create(user=user, company=company)
    client.force_login(user)
    return client, membership


def create_payload(work_date, **overrides):
    return {"work_date": str(work_date), **overrides}


def test_explicit_draft_reserves_date_and_can_be_deleted(employee_client):
    client, membership = employee_client
    today = timezone.localdate()
    response = client.post(
        "/api/v1/work-in-office/", create_payload(today), content_type="application/json"
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
        create_payload(today),
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


def test_rejected_record_can_resubmit_or_close_as_not_in_office(employee_client):
    client, membership = employee_client
    today = timezone.localdate()
    manager = User.objects.create_user(email="manager@example.com")
    manager_membership = CompanyMembership.objects.create(
        user=manager,
        company=membership.company,
        role=CompanyMembership.Role.MANAGER,
    )
    ManagerAssignment.objects.create(
        manager=manager_membership,
        employee=membership,
        effective_from=today,
    )
    pending = WorkInOfficeRecord.objects.create(
        employee=membership,
        work_date=today,
        location_choice=WorkInOfficeRecord.LocationChoice.IN_OFFICE,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
    )
    rejected = reject_record(record=pending, actor=manager, reason="Need clarification")
    assert rejected.review_state == WorkInOfficeRecord.ReviewState.REJECTED
    assert rejected.correction_deadline is not None
    resubmitted = client.put(
        f"/api/v1/work-in-office/{rejected.pk}/",
        create_payload(
            today,
            location_choice="in_office",
            note="Clarified",
            version=rejected.version,
        ),
        content_type="application/json",
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["review_state"] == WorkInOfficeRecord.ReviewState.PENDING

    rejected_again = reject_record(
        record=WorkInOfficeRecord.objects.get(pk=rejected.pk),
        actor=manager,
        reason="Still not enough",
    )
    closed = client.put(
        f"/api/v1/work-in-office/{rejected_again.pk}/",
        create_payload(
            today,
            location_choice="not_in_office",
            note="",
            version=rejected_again.version,
        ),
        content_type="application/json",
    )
    assert closed.status_code == 200
    assert closed.json()["review_state"] == WorkInOfficeRecord.ReviewState.NOT_REQUIRED
    assert AuditEvent.objects.filter(event_type="work_logs.record_rejected").count() == 2
