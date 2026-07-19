import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership, EmailOTPChallenge, User
from apps.accounts.permissions import IsHRAdmin, IsManagerOrHRAdmin
from apps.audit.models import AuditEvent


@pytest.fixture
def active_user(db):
    company = Company.objects.create(name="Example Company", slug="example")
    user = User.objects.create_user(email="employee@example.com")
    CompanyMembership.objects.create(user=user, company=company)
    return user


@pytest.mark.django_db
def test_otp_login_is_single_use_and_creates_audit_event(client, active_user):
    request_response = client.post(
        "/api/v1/auth/otp/request/",
        {"email": active_user.email},
        content_type="application/json",
    )

    assert request_response.status_code == 202
    assert len(mail.outbox) == 1
    code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group(0)
    payload = {
        "email": active_user.email,
        "challenge_id": request_response.json()["challenge_id"],
        "code": code,
    }

    verify_response = client.post(
        "/api/v1/auth/otp/verify/",
        payload,
        content_type="application/json",
    )
    replay_response = client.post(
        "/api/v1/auth/otp/verify/",
        payload,
        content_type="application/json",
    )

    assert verify_response.status_code == 200
    assert verify_response.json()["email"] == active_user.email
    assert replay_response.status_code == 400
    assert AuditEvent.objects.filter(
        actor=active_user,
        event_type="auth.otp_login_succeeded",
    ).exists()


@pytest.mark.django_db
def test_unknown_email_gets_generic_response(client):
    response = client.post(
        "/api/v1/auth/otp/request/",
        {"email": "unknown@example.com"},
        content_type="application/json",
    )

    assert response.status_code == 202
    assert "eligible" in response.json()["detail"]
    assert len(mail.outbox) == 0
    assert EmailOTPChallenge.objects.filter(email="unknown@example.com").exists()


@pytest.mark.django_db
def test_protected_endpoint_requires_authentication(client):
    response = client.get("/api/v1/users/me/")

    assert response.status_code in {401, 403}


def test_csrf_endpoint_sets_cookie(client):
    response = client.get("/api/v1/auth/csrf/")

    assert response.status_code == 204
    assert "csrftoken" in response.cookies


@pytest.mark.django_db
def test_otp_verify_requires_csrf_proof(active_user):
    client = Client(enforce_csrf_checks=True)
    request_response = client.post(
        "/api/v1/auth/otp/request/",
        {"email": active_user.email},
        content_type="application/json",
    )
    code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group(0)
    payload = {
        "email": active_user.email,
        "challenge_id": request_response.json()["challenge_id"],
        "code": code,
    }

    rejected = client.post("/api/v1/auth/otp/verify/", payload, content_type="application/json")
    csrf_response = client.get("/api/v1/auth/csrf/")
    accepted = client.post(
        "/api/v1/auth/otp/verify/",
        payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_response.cookies["csrftoken"].value,
    )

    assert rejected.status_code == 403
    assert accepted.status_code == 200


@pytest.mark.django_db
def test_authenticated_user_requires_active_membership(client):
    user = User.objects.create_user(email="inactive@example.com")
    client.force_login(user)

    response = client.get("/api/v1/users/me/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_revoked_user_can_log_out(client, active_user):
    membership = active_user.memberships.get()
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    client.force_login(active_user)

    response = client.post("/api/v1/auth/logout/")

    assert response.status_code == 204
    assert not client.session.get("_auth_user_id")


@pytest.mark.django_db
def test_expired_latest_otp_does_not_hold_email_rate_limit(client, active_user):
    now = timezone.now()
    for _ in range(5):
        challenge = EmailOTPChallenge.objects.create(
            user=active_user,
            email=active_user.email,
            code_hash="unused",
            request_fingerprint="test-fingerprint",
            expires_at=now - timedelta(seconds=1),
        )
        EmailOTPChallenge.objects.filter(pk=challenge.pk).update(created_at=now)

    response = client.post(
        "/api/v1/auth/otp/request/",
        {"email": active_user.email},
        content_type="application/json",
    )

    assert response.status_code == 202
    assert EmailOTPChallenge.objects.filter(email=active_user.email).count() == 6
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_company_role_permissions(active_user):
    membership = active_user.memberships.get()
    request = SimpleNamespace(user=active_user)

    assert not IsManagerOrHRAdmin().has_permission(request, None)
    assert not IsHRAdmin().has_permission(request, None)

    membership.role = CompanyMembership.Role.MANAGER
    membership.save(update_fields=["role"])
    assert IsManagerOrHRAdmin().has_permission(request, None)
    assert not IsHRAdmin().has_permission(request, None)

    membership.role = CompanyMembership.Role.HR_ADMIN
    membership.save(update_fields=["role"])
    assert IsManagerOrHRAdmin().has_permission(request, None)
    assert IsHRAdmin().has_permission(request, None)


def test_purge_expired_otps_rejects_negative_retention():
    with pytest.raises(CommandError, match="--hours must be zero or greater"):
        call_command("purge_expired_otps", hours=-1)
