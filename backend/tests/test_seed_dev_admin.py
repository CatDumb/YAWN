import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import Company, CompanyMembership, User


@pytest.mark.django_db
def test_seed_dev_admin_creates_expected_identity_once(settings):
    settings.DEBUG = True
    settings.WIO_ALLOW_INSECURE_DEV_SEED = True
    settings.WIO_SIGNUP_COMPANY_SLUG = "seed-company"

    call_command("seed_dev_admin")

    user = User.objects.get(email="admin@wio.local")
    membership = CompanyMembership.objects.get(user=user)
    assert user.is_active is True
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.check_password("admin") is True
    assert membership.company.slug == "seed-company"
    assert membership.role == CompanyMembership.Role.HR_ADMIN
    assert membership.is_active is True

    user.set_password("changed-password")
    user.save(update_fields=["password"])
    call_command("seed_dev_admin")

    user.refresh_from_db()
    assert user.check_password("changed-password") is True
    assert User.objects.filter(email="admin@wio.local").count() == 1
    assert CompanyMembership.objects.filter(user=user).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("debug", "allow_seed"),
    [(False, True), (True, False), (False, False)],
)
def test_seed_dev_admin_refuses_without_both_local_only_guards(settings, debug, allow_seed):
    settings.DEBUG = debug
    settings.WIO_ALLOW_INSECURE_DEV_SEED = allow_seed

    with pytest.raises(CommandError, match="DJANGO_DEBUG=true"):
        call_command("seed_dev_admin")

    assert not User.objects.filter(email="admin@wio.local").exists()
    assert not Company.objects.filter(slug="wio").exists()


@pytest.mark.django_db
def test_seed_dev_admin_never_changes_existing_account(settings):
    settings.DEBUG = True
    settings.WIO_ALLOW_INSECURE_DEV_SEED = True
    existing_user = User.objects.create_user(email="admin@wio.local", password="keep-this")

    call_command("seed_dev_admin")

    existing_user.refresh_from_db()
    assert existing_user.is_staff is False
    assert existing_user.is_superuser is False
    assert existing_user.check_password("keep-this") is True
    assert not CompanyMembership.objects.filter(user=existing_user).exists()
