import re
from datetime import timedelta

import pytest
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccessRequest, Company, CompanyMembership, EmailOTPChallenge, User
from apps.audit.models import AuditEvent


@pytest.fixture
def company(db):
    return Company.objects.create(name="Example Company", slug="example")


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(email="root@example.com", password="secret")


def run_admin_action(client, url, action, object_id):
    response = client.post(
        url,
        {"action": action, "_selected_action": [str(object_id)]},
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_anonymous_user_can_render_admin_login(client):
    response = client.get(
        reverse("admin:login"),
        {"next": reverse("admin:accounts_company_changelist")},
    )

    assert response.status_code == 200
    assert "Log in" in response.content.decode()


@pytest.mark.django_db
def test_only_superusers_or_active_staff_hr_admins_can_view_access_requests(
    client,
    company,
):
    access_request = AccessRequest.objects.create(
        company=company,
        email="requester@example.com",
        first_name="Request",
        last_name="Er",
        request_fingerprint="a" * 64,
    )
    hr_admin = User.objects.create_user(email="hr@example.com", is_staff=True)
    CompanyMembership.objects.create(
        user=hr_admin,
        company=company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    staff_without_role = User.objects.create_user(email="staff@example.com", is_staff=True)
    url = reverse("admin:accounts_accessrequest_changelist")

    client.force_login(hr_admin)
    approved = client.get(url)

    assert approved.status_code == 200
    assert access_request.email in approved.content.decode()

    client.force_login(staff_without_role)
    forbidden = client.get(url)

    assert forbidden.status_code == 403


@pytest.mark.django_db
def test_access_request_admin_approval_creates_membership_and_audit(client, company, superuser):
    access_request = AccessRequest.objects.create(
        company=company,
        email="requester@example.com",
        first_name="Request",
        last_name="Er",
        request_fingerprint="a" * 64,
    )
    client.force_login(superuser)

    run_admin_action(
        client,
        reverse("admin:accounts_accessrequest_changelist"),
        "approve_access_requests",
        access_request.pk,
    )

    access_request.refresh_from_db()
    user = User.objects.get(email=access_request.email)
    membership = CompanyMembership.objects.get(user=user, company=company)
    audit_event = AuditEvent.objects.get(event_type="accounts.access_request_approved")
    assert access_request.status == AccessRequest.Status.APPROVED
    assert access_request.reviewer == superuser
    assert user.has_usable_password() is False
    assert membership.role == CompanyMembership.Role.EMPLOYEE
    assert membership.is_active is True
    assert audit_event.actor == superuser
    assert audit_event.metadata == {"company_id": company.pk, "user_id": user.pk}


@pytest.mark.django_db(transaction=True)
def test_approval_sends_one_post_commit_notification(client, company, superuser, settings):
    settings.WIO_APP_URL = "http://testserver:3000"
    access_request = AccessRequest.objects.create(
        company=company,
        email="requester@example.com",
        first_name="Request",
        last_name="Er",
        request_fingerprint="a" * 64,
    )
    client.force_login(superuser)
    url = reverse("admin:accounts_accessrequest_changelist")

    run_admin_action(client, url, "approve_access_requests", access_request.pk)
    run_admin_action(client, url, "approve_access_requests", access_request.pk)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [access_request.email]
    assert "http://testserver:3000" in mail.outbox[0].body
    assert "Already approved? Sign in" in mail.outbox[0].body
    assert not re.search(r"\b\d{6}\b", mail.outbox[0].body)


@pytest.mark.django_db
def test_access_request_admin_rejection_has_no_identity_side_effects(client, company, superuser):
    access_request = AccessRequest.objects.create(
        company=company,
        email="reject@example.com",
        first_name="Reject",
        last_name="Me",
        request_fingerprint="a" * 64,
    )
    client.force_login(superuser)

    run_admin_action(
        client,
        reverse("admin:accounts_accessrequest_changelist"),
        "reject_access_requests",
        access_request.pk,
    )

    access_request.refresh_from_db()
    assert access_request.status == AccessRequest.Status.REJECTED
    assert not User.objects.filter(email=access_request.email).exists()
    assert not CompanyMembership.objects.exists()
    assert AuditEvent.objects.filter(
        actor=superuser,
        event_type="accounts.access_request_rejected",
    ).exists()


@pytest.mark.django_db
def test_non_hr_staff_cannot_run_access_request_actions(client, company):
    access_request = AccessRequest.objects.create(
        company=company,
        email="requester@example.com",
        first_name="Request",
        last_name="Er",
        request_fingerprint="a" * 64,
    )
    staff_without_role = User.objects.create_user(email="staff@example.com", is_staff=True)
    client.force_login(staff_without_role)

    response = client.post(
        reverse("admin:accounts_accessrequest_changelist"),
        {"action": "approve_access_requests", "_selected_action": [str(access_request.pk)]},
    )

    assert response.status_code == 403
    access_request.refresh_from_db()
    assert access_request.status == AccessRequest.Status.PENDING


@pytest.mark.django_db
def test_hr_admin_cannot_view_or_change_same_company_superuser(client, company, superuser):
    hr_admin = User.objects.create_user(email="hr@example.com", is_staff=True)
    CompanyMembership.objects.create(
        user=hr_admin,
        company=company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    CompanyMembership.objects.create(user=superuser, company=company)
    user_url = reverse("admin:accounts_user_changelist")
    client.force_login(hr_admin)

    response = client.get(user_url)

    assert response.status_code == 200
    assert superuser.email not in response.content.decode()

    run_admin_action(client, user_url, "disable_selected_users", superuser.pk)

    superuser.refresh_from_db()
    assert superuser.is_active is True
    assert not AuditEvent.objects.filter(
        actor=hr_admin,
        event_type="accounts.user_disabled",
        target_id=str(superuser.pk),
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_disable_and_enable_actions_enforce_active_user_and_membership(
    client,
    company,
    superuser,
    settings,
):
    settings.WIO_OTP_RESEND_SECONDS = 0
    user = User.objects.create_user(email="employee@example.com")
    membership = CompanyMembership.objects.create(user=user, company=company)
    challenge = EmailOTPChallenge.objects.create(
        user=user,
        email=user.email,
        code_hash=make_password("123456"),
        request_fingerprint="a" * 64,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    user_url = reverse("admin:accounts_user_changelist")
    client.force_login(superuser)

    run_admin_action(client, user_url, "disable_selected_users", user.pk)

    user.refresh_from_db()
    assert user.is_active is False
    assert membership.is_active is True
    assert AuditEvent.objects.filter(
        actor=superuser,
        event_type="accounts.user_disabled",
        target_id=str(user.pk),
    ).exists()

    signed_in_client = Client()
    signed_in_client.force_login(user)
    assert signed_in_client.get("/api/v1/users/me/").status_code in {401, 403}
    otp_request = Client().post(
        "/api/v1/auth/otp/request/",
        {"email": user.email},
        content_type="application/json",
    )
    otp_verify = Client().post(
        "/api/v1/auth/otp/verify/",
        {"email": user.email, "challenge_id": challenge.pk, "code": "123456"},
        content_type="application/json",
    )
    assert otp_request.status_code == 202
    assert otp_verify.status_code == 400
    assert len(mail.outbox) == 0

    run_admin_action(client, user_url, "enable_selected_users", user.pk)

    user.refresh_from_db()
    assert user.is_active is True
    assert AuditEvent.objects.filter(
        actor=superuser,
        event_type="accounts.user_enabled",
        target_id=str(user.pk),
    ).exists()
    eligible_request = Client().post(
        "/api/v1/auth/otp/request/",
        {"email": user.email},
        content_type="application/json",
    )
    assert eligible_request.status_code == 202
    assert len(mail.outbox) == 1

    membership.is_active = False
    membership.save(update_fields=["is_active"])
    run_admin_action(client, user_url, "disable_selected_users", user.pk)
    run_admin_action(client, user_url, "enable_selected_users", user.pk)
    ineligible_request = Client().post(
        "/api/v1/auth/otp/request/",
        {"email": user.email},
        content_type="application/json",
    )
    assert ineligible_request.status_code == 202
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    [
        CompanyMembership.Role.EMPLOYEE,
        CompanyMembership.Role.MANAGER,
        CompanyMembership.Role.HR_ADMIN,
    ],
)
def test_approval_requires_explicit_reactivation_for_inactive_membership(
    client,
    company,
    superuser,
    role,
):
    user = User.objects.create_user(email="disabled@example.com", is_active=False)
    CompanyMembership.objects.create(user=user, company=company, role=role, is_active=False)
    access_request = AccessRequest.objects.create(
        company=company,
        email=user.email,
        first_name="Disabled",
        last_name="User",
        request_fingerprint="a" * 64,
    )
    client.force_login(superuser)

    run_admin_action(
        client,
        reverse("admin:accounts_accessrequest_changelist"),
        "approve_access_requests",
        access_request.pk,
    )

    user.refresh_from_db()
    membership = user.memberships.get(company=company)
    assert user.is_active is False
    assert membership.role == role
    assert membership.is_active is False
    access_request.refresh_from_db()
    assert access_request.status == AccessRequest.Status.PENDING
    assert not AuditEvent.objects.filter(
        event_type="accounts.access_request_approved",
        target_id=str(access_request.pk),
    ).exists()
    assert len(mail.outbox) == 0
    assert not AuditEvent.objects.filter(
        event_type="accounts.user_enabled",
        target_id=str(user.pk),
    ).exists()


@pytest.mark.django_db
def test_hr_admin_can_reactivate_membership_only_in_managed_company(client, company):
    CompanyMembership.objects.create(
        user=User.objects.create_user(email="existing@example.com"),
        company=company,
    )
    hr_admin = User.objects.create_user(email="hr@example.com", is_staff=True)
    CompanyMembership.objects.create(
        user=hr_admin,
        company=company,
        role=CompanyMembership.Role.HR_ADMIN,
    )
    member = CompanyMembership.objects.create(
        user=User.objects.create_user(email="employee@example.com"),
        company=company,
        is_active=False,
    )
    other_company = Company.objects.create(name="Other Company", slug="other")
    other_member = CompanyMembership.objects.create(
        user=User.objects.create_user(email="other@example.com"),
        company=other_company,
        is_active=False,
    )
    client.force_login(hr_admin)
    membership_url = reverse("admin:accounts_companymembership_changelist")
    membership_change_url = reverse("admin:accounts_companymembership_change", args=[member.pk])

    assert client.get(membership_url).status_code == 200
    direct_change = client.post(membership_change_url, {"is_active": "on", "_save": "Save"})

    assert direct_change.status_code == 302
    member.refresh_from_db()
    assert member.is_active is False
    assert not AuditEvent.objects.filter(
        actor=hr_admin,
        event_type="accounts.membership_reactivated",
        target_id=str(member.pk),
    ).exists()

    run_admin_action(
        client,
        membership_url,
        "reactivate_selected_memberships",
        member.pk,
    )
    run_admin_action(
        client,
        membership_url,
        "reactivate_selected_memberships",
        other_member.pk,
    )

    member.refresh_from_db()
    other_member.refresh_from_db()
    assert member.is_active is True
    assert other_member.is_active is False
    assert AuditEvent.objects.filter(
        actor=hr_admin,
        event_type="accounts.membership_reactivated",
        target_id=str(member.pk),
        metadata={"company_id": company.pk, "user_id": member.user_id},
    ).exists()
