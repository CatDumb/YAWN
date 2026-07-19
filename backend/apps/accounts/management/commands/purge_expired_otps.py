from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import EmailOTPChallenge


class Command(BaseCommand):
    help = "Delete OTP challenges older than the configured retention window."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **options):
        hours = options["hours"]
        if hours < 0:
            raise CommandError("--hours must be zero or greater.")

        cutoff = timezone.now() - timedelta(hours=hours)
        deleted, _ = EmailOTPChallenge.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired OTP records."))
