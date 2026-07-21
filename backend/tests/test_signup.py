import pytest

from apps.accounts.models import AccessRequest, Company, CompanyMembership, EmailOTPChallenge, User


@pytest.fixture
def signup_company(settings, db):
    company = Company.objects.create(name="Signup Company", slug="signup")
    settings.WIO_SIGNUP_COMPANY_SLUG = company.slug
    return company


def sign_up(client, email="new.user@example.com", first_name="New", last_name="User"):
    return client.post(
        "/api/v1/auth/sign-up/",
        {"email": email, "first_name": first_name, "last_name": last_name},
        content_type="application/json",
    )


@pytest.mark.django_db
def test_sign_up_creates_only_pending_access_request(client, signup_company):
    response = sign_up(client, email="New.User@Example.COM")

    assert response.status_code == 202
    assert response.json() == {"detail": "If access can be requested, it is pending review."}
    access_request = AccessRequest.objects.get()
    assert access_request.company == signup_company
    assert access_request.email == "new.user@example.com"
    assert access_request.first_name == "New"
    assert access_request.last_name == "User"
    assert access_request.status == AccessRequest.Status.PENDING
    assert len(access_request.request_fingerprint) == 64
    assert not User.objects.filter(email=access_request.email).exists()
    assert not CompanyMembership.objects.exists()
    assert not EmailOTPChallenge.objects.exists()
    assert not client.session.get("_auth_user_id")


@pytest.mark.django_db
def test_sign_up_coalesces_duplicate_pending_request_without_enumeration(client, signup_company):
    first = sign_up(client, email="New.User@Example.COM", first_name="First", last_name="Name")
    second = sign_up(client, email="new.user@example.com", first_name="Other", last_name="Person")

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert AccessRequest.objects.count() == 1
    access_request = AccessRequest.objects.get()
    assert access_request.first_name == "First"
    assert access_request.last_name == "Name"


@pytest.mark.django_db
def test_sign_up_email_rate_limit_has_generic_response(client, settings, signup_company):
    settings.WIO_SIGNUP_REQUESTS_PER_HOUR = 1
    AccessRequest.objects.create(
        company=signup_company,
        email="limited@example.com",
        first_name="Prior",
        last_name="Request",
        request_fingerprint="a" * 64,
        status=AccessRequest.Status.REJECTED,
    )

    response = sign_up(client, email="limited@example.com")

    assert response.status_code == 202
    assert response.json() == {"detail": "If access can be requested, it is pending review."}
    assert AccessRequest.objects.filter(email="limited@example.com").count() == 1


@pytest.mark.django_db
def test_sign_up_fingerprint_rate_limit_has_generic_response(client, settings, signup_company):
    settings.WIO_SIGNUP_FINGERPRINT_REQUESTS_PER_HOUR = 1
    first = sign_up(client, email="first@example.com")
    AccessRequest.objects.update(status=AccessRequest.Status.REJECTED)

    second = sign_up(client, email="second@example.com")

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert AccessRequest.objects.count() == 1


@pytest.mark.django_db
def test_sign_up_targets_only_active_configured_company(client, settings, signup_company):
    other_company = Company.objects.create(name="Other Company", slug="other")

    response = sign_up(client)

    assert response.status_code == 202
    assert AccessRequest.objects.get().company == signup_company
    assert AccessRequest.objects.filter(company=other_company).count() == 0

    signup_company.is_active = False
    signup_company.save(update_fields=["is_active"])
    blocked = sign_up(client, email="inactive-company@example.com")

    assert blocked.status_code == 202
    assert blocked.json() == response.json()
    assert AccessRequest.objects.count() == 1
