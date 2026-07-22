from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Company, CompanyMembership, User

SEED_EMAIL = "admin@wio.local"
SEED_PASSWORD = "admin"
DEFAULT_COMPANY_SLUG = "wio"


class Command(BaseCommand):
    help = "Create the one-time local development administrator when explicitly enabled."

    def handle(self, *args, **options):
        if not settings.DEBUG or not settings.WIO_ALLOW_INSECURE_DEV_SEED:
            raise CommandError(
                "seed_dev_admin requires DJANGO_DEBUG=true and WIO_ALLOW_INSECURE_DEV_SEED=true."
            )

        company_slug = settings.WIO_SIGNUP_COMPANY_SLUG or DEFAULT_COMPANY_SLUG
        with transaction.atomic():
            company, _ = Company.objects.get_or_create(
                slug=company_slug,
                defaults={"name": "WIO"},
            )
            existing_user = User.objects.filter(email__iexact=SEED_EMAIL).first()
            if existing_user is not None:
                self.stdout.write("Development administrator already exists; no changes made.")
                return

            user = User.objects.create_superuser(
                email=SEED_EMAIL,
                password=SEED_PASSWORD,
                is_active=True,
            )
            CompanyMembership.objects.create(
                user=user,
                company=company,
                role=CompanyMembership.Role.HR_ADMIN,
                is_active=True,
            )

        self.stdout.write(self.style.SUCCESS("Created one-time local development administrator."))
