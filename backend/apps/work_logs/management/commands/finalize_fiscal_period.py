from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.work_logs.finalization import run_finalization
from apps.work_logs.models import FiscalPeriod


class Command(BaseCommand):
    help = "Run the fixed, retry-safe fiscal finalization sequence for one fiscal period."

    def add_arguments(self, parser):
        parser.add_argument("period_id", type=int)

    def handle(self, *args, **options):
        period_id = options["period_id"]
        if not FiscalPeriod.objects.filter(pk=period_id).exists():
            raise CommandError(f"Fiscal period {period_id} does not exist.")
        try:
            period = run_finalization(period_id)
        except ValidationError as error:
            raise CommandError(error.messages[0]) from error
        self.stdout.write(self.style.SUCCESS(f"Finalized {period.name} ({period.pk})."))
