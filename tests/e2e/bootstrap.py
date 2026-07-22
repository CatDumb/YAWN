import os
import shutil
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
ARTIFACT_ROOT = (BACKEND_ROOT / ".e2e").resolve()


def reset_artifacts() -> None:
    if ARTIFACT_ROOT.parent != BACKEND_ROOT.resolve():
        raise RuntimeError("Refusing to clean E2E artifacts outside backend directory.")
    shutil.rmtree(ARTIFACT_ROOT, ignore_errors=True)
    (ARTIFACT_ROOT / "mail").mkdir(parents=True)


def bootstrap() -> None:
    reset_artifacts()
    sys.path.insert(0, str(BACKEND_ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.e2e"

    import django

    django.setup()

    from django.core.management import call_command

    from apps.accounts.models import Company, CompanyMembership, User

    call_command("migrate", interactive=False, verbosity=0)
    company = Company.objects.create(
        name="E2E Company",
        slug="e2e-company",
        email_domain="example.com",
    )
    user = User.objects.create_user(
        email="e2e.employee@example.com",
        first_name="E2E",
        last_name="Employee",
    )
    CompanyMembership.objects.create(
        company=company,
        is_active=True,
        role=CompanyMembership.Role.EMPLOYEE,
        user=user,
    )


if __name__ == "__main__":
    bootstrap()
