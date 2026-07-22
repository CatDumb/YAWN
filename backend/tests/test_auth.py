import logging
import re
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.core.management import CommandError, call_command
from django.db import transaction
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership, EmailOTPChallenge, User
from apps.accounts.permissions import IsHRAdmin, IsManagerOrHRAdmin
from apps.accounts.services import send_approval_email, send_otp_email
from apps.accounts.views import _lock_rate_limits
from apps.audit.models import AuditEvent


@pytest.fixture
def active_user(db):
    company = Company.objects.create(name="Example Company", slug="example")
    user = User.objects.create_user(email="employee@example.com")
    CompanyMembership.objects.create(user=user, company=company)
    return user


@pytest.mark.django_db(transaction=True)
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

    assert response.status_code == 200
    assert "csrftoken" in response.cookies
    assert response.json()["csrfToken"]


@pytest.mark.django_db(transaction=True)
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
        HTTP_X_CSRFTOKEN=csrf_response.json()["csrfToken"],
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
def test_email_rate_limit_remains_bounded_after_otp_expiry(client, active_user):
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
    assert EmailOTPChallenge.objects.filter(email=active_user.email).count() == 5
    assert len(mail.outbox) == 0


@pytest.mark.django_db(transaction=True)
def test_otp_fingerprint_rate_limit_remains_generic_and_bounded(client, settings):
    settings.WIO_OTP_IP_REQUESTS_PER_HOUR = 2

    for email in ("first@example.com", "second@example.com", "third@example.com"):
        response = client.post(
            "/api/v1/auth/otp/request/",
            {"email": email},
            content_type="application/json",
        )
        assert response.status_code == 202
        assert response.json()["detail"] == (
            "If the account is eligible, a sign-in code has been sent."
        )

    assert EmailOTPChallenge.objects.count() == 2
    assert len(mail.outbox) == 0


@pytest.mark.django_db(transaction=True)
def test_expired_otp_cannot_create_session_or_be_reused(client, active_user):
    challenge = EmailOTPChallenge.objects.create(
        user=active_user,
        email=active_user.email,
        code_hash=make_password("123456"),
        request_fingerprint="test-fingerprint",
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    response = client.post(
        "/api/v1/auth/otp/verify/",
        {"email": active_user.email, "challenge_id": challenge.pk, "code": "123456"},
        content_type="application/json",
    )
    challenge.refresh_from_db()

    assert response.status_code == 400
    assert challenge.consumed_at is None
    assert challenge.attempt_count == 0
    assert not client.session.get("_auth_user_id")
    assert not AuditEvent.objects.filter(event_type="auth.otp_login_succeeded").exists()


@pytest.mark.django_db(transaction=True)
def test_otp_attempt_exhaustion_consumes_challenge(client, active_user, settings):
    request_response = client.post(
        "/api/v1/auth/otp/request/",
        {"email": active_user.email},
        content_type="application/json",
    )
    challenge_id = request_response.json()["challenge_id"]
    code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group(0)

    for _ in range(settings.WIO_OTP_MAX_ATTEMPTS):
        response = client.post(
            "/api/v1/auth/otp/verify/",
            {"email": active_user.email, "challenge_id": challenge_id, "code": "000000"},
            content_type="application/json",
        )
        assert response.status_code == 400

    replay = client.post(
        "/api/v1/auth/otp/verify/",
        {"email": active_user.email, "challenge_id": challenge_id, "code": code},
        content_type="application/json",
    )
    challenge = EmailOTPChallenge.objects.get(pk=challenge_id)

    assert replay.status_code == 400
    assert challenge.consumed_at is not None
    assert not client.session.get("_auth_user_id")
    assert not AuditEvent.objects.filter(event_type="auth.otp_login_succeeded").exists()


@pytest.mark.django_db(transaction=True)
def test_otp_challenge_email_mismatch_cannot_create_session(client, active_user):
    request_response = client.post(
        "/api/v1/auth/otp/request/",
        {"email": active_user.email},
        content_type="application/json",
    )
    code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group(0)

    response = client.post(
        "/api/v1/auth/otp/verify/",
        {
            "email": "other@example.com",
            "challenge_id": request_response.json()["challenge_id"],
            "code": code,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired code."}
    assert not client.session.get("_auth_user_id")
    assert not AuditEvent.objects.filter(event_type="auth.otp_login_succeeded").exists()


@pytest.mark.django_db(transaction=True)
def test_otp_is_reused_during_resend_cooldown(client, active_user):
    first = client.post(
        "/api/v1/auth/otp/request/",
        {"email": active_user.email},
        content_type="application/json",
    )
    second = client.post(
        "/api/v1/auth/otp/request/",
        {"email": active_user.email},
        content_type="application/json",
    )

    assert first.json()["challenge_id"] == second.json()["challenge_id"]
    assert EmailOTPChallenge.objects.filter(email=active_user.email).count() == 1
    assert len(mail.outbox) == 1


@pytest.mark.django_db(transaction=True)
def test_otp_is_reissued_after_resend_cooldown(client, active_user, settings):
    settings.WIO_OTP_RESEND_SECONDS = 0
    first = client.post(
        "/api/v1/auth/otp/request/",
        {"email": active_user.email},
        content_type="application/json",
    )
    second = client.post(
        "/api/v1/auth/otp/request/",
        {"email": active_user.email},
        content_type="application/json",
    )

    assert first.json()["challenge_id"] != second.json()["challenge_id"]
    assert EmailOTPChallenge.objects.filter(email=active_user.email).count() == 2
    assert len(mail.outbox) == 2


@pytest.mark.django_db(transaction=True)
def test_otp_email_is_sent_after_challenge_transaction_commits(client, active_user, monkeypatch):
    send_mail = MagicMock(return_value=1)
    monkeypatch.setattr("apps.accounts.services.send_mail", send_mail)

    with transaction.atomic():
        response = client.post(
            "/api/v1/auth/otp/request/",
            {"email": active_user.email},
            content_type="application/json",
        )
        assert response.status_code == 202
        assert send_mail.call_count == 0

    assert send_mail.call_count == 1


def test_otp_email_failure_log_omits_recipient_and_code(monkeypatch, caplog):
    recipient = "employee@example.com"
    code = "123456"
    monkeypatch.setattr(
        "apps.accounts.services.send_mail",
        MagicMock(side_effect=RuntimeError(f"smtp rejected {recipient} {code}")),
    )
    caplog.set_level(logging.ERROR, logger="wio.auth")

    send_otp_email(recipient=recipient, code=code)

    assert caplog.messages == ["otp_email_delivery_failed"]
    assert recipient not in caplog.text
    assert code not in caplog.text


def test_approval_email_failure_log_omits_recipient(monkeypatch, caplog):
    recipient = "employee@example.com"
    monkeypatch.setattr(
        "apps.accounts.services.send_mail",
        MagicMock(side_effect=RuntimeError(f"smtp rejected {recipient}")),
    )
    caplog.set_level(logging.ERROR, logger="wio.auth")

    send_approval_email(recipient=recipient)

    assert caplog.messages == ["approval_email_delivery_failed"]
    assert recipient not in caplog.text


def test_otp_and_session_policy_defaults(settings):
    assert settings.WIO_OTP_TTL_SECONDS == 600
    assert settings.WIO_OTP_MAX_ATTEMPTS == 5
    assert settings.WIO_OTP_RESEND_SECONDS == 60
    assert settings.EMAIL_TIMEOUT == 10
    assert settings.WIO_OTP_REQUESTS_PER_HOUR == 5
    assert settings.WIO_OTP_IP_REQUESTS_PER_HOUR == 100
    assert settings.SESSION_COOKIE_AGE == 14 * 24 * 60 * 60
    assert settings.SESSION_SAVE_EVERY_REQUEST is False


def _load_valid_production_settings(monkeypatch):
    required_settings = {
        "DJANGO_SECRET_KEY": "production-secret",
        "DJANGO_ALLOWED_HOSTS": "api.example.com",
        "DJANGO_EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "DJANGO_EMAIL_HOST": "smtp.gmail.com",
        "DJANGO_EMAIL_PORT": "587",
        "DJANGO_EMAIL_HOST_USER": "yawn@example.com",
        "DJANGO_EMAIL_HOST_PASSWORD": "app-password",
        "DJANGO_EMAIL_USE_TLS": "true",
        "DJANGO_DEFAULT_FROM_EMAIL": "yawn@example.com",
        "WIO_APP_URL": "https://app.example.com",
    }
    for name, value in required_settings.items():
        monkeypatch.setenv(name, value)

    base = import_module("config.settings.base")
    monkeypatch.setattr(base, "SECRET_KEY", required_settings["DJANGO_SECRET_KEY"])
    production = import_module("config.settings.production")
    monkeypatch.setattr(production, "EMAIL_BACKEND", required_settings["DJANGO_EMAIL_BACKEND"])
    monkeypatch.setattr(production, "EMAIL_HOST", required_settings["DJANGO_EMAIL_HOST"])
    monkeypatch.setattr(production, "EMAIL_PORT", int(required_settings["DJANGO_EMAIL_PORT"]))
    monkeypatch.setattr(production, "EMAIL_HOST_USER", required_settings["DJANGO_EMAIL_HOST_USER"])
    monkeypatch.setattr(
        production,
        "EMAIL_HOST_PASSWORD",
        required_settings["DJANGO_EMAIL_HOST_PASSWORD"],
    )
    monkeypatch.setattr(production, "EMAIL_USE_TLS", True)
    monkeypatch.setattr(
        production,
        "DEFAULT_FROM_EMAIL",
        required_settings["DJANGO_DEFAULT_FROM_EMAIL"],
    )
    monkeypatch.setattr(production, "WIO_APP_URL", required_settings["WIO_APP_URL"])
    return production


def test_production_requires_valid_smtp_and_https_app_url(monkeypatch):
    production = _load_valid_production_settings(monkeypatch)
    production._validate_production_email_and_app_url()

    for invalid_url in ("http://app.example.com", "https://bad host"):
        monkeypatch.setattr(production, "WIO_APP_URL", invalid_url)
        with pytest.raises(Exception, match="HTTPS frontend homepage"):
            production._validate_production_email_and_app_url()


@pytest.mark.parametrize("timeout", [0, 31])
def test_production_rejects_out_of_range_smtp_timeout(monkeypatch, timeout):
    production = _load_valid_production_settings(monkeypatch)
    monkeypatch.setattr(production, "EMAIL_TIMEOUT", timeout)

    with pytest.raises(Exception, match="DJANGO_EMAIL_TIMEOUT_SECONDS"):
        production._validate_production_email_and_app_url()


@pytest.mark.parametrize("host", ["smtp.gmail.com:587", "smtp.gmail.com/path"])
def test_production_rejects_smtp_host_with_port_or_path(monkeypatch, host):
    production = _load_valid_production_settings(monkeypatch)
    monkeypatch.setattr(production, "EMAIL_HOST", host)

    with pytest.raises(Exception, match="bare SMTP host"):
        production._validate_production_email_and_app_url()


def test_compose_schedules_daily_otp_and_session_cleanup():
    compose = (Path(__file__).resolve().parents[2] / "compose.yaml").read_text(encoding="utf-8")

    assert "cleanup:" in compose
    assert "purge_expired_otps --hours 24" in compose
    assert "python manage.py clearsessions" in compose
    assert "Cleanup failed; retrying in 24 hours." in compose
    assert "sleep 86400" in compose


def test_compose_bootstraps_configured_signup_company():
    compose = (Path(__file__).resolve().parents[2] / "compose.yaml").read_text(encoding="utf-8")

    assert "slug=settings.WIO_SIGNUP_COMPANY_SLUG" in compose
    assert "Company.objects.get_or_create(slug=slug" in compose


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


def test_rate_locks_use_postgresql_transaction_advisory_locks(monkeypatch):
    connection = MagicMock()
    connection.vendor = "postgresql"
    cursor = connection.cursor.return_value.__enter__.return_value
    monkeypatch.setattr("apps.accounts.views.connection", connection)

    _lock_rate_limits("employee@example.com", "request-fingerprint")

    assert cursor.execute.call_count == 2
    assert all(
        call.args[0] == "SELECT pg_advisory_xact_lock(%s)" for call in cursor.execute.call_args_list
    )
