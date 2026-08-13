from django.core.management.base import BaseCommand

from apps.work_logs.lifecycle import advance_fiscal_period_states


class Command(BaseCommand):
    help = "Persist and audit all fiscal-period state transitions due by company date."

    def handle(self, *args, **options):
        changed = advance_fiscal_period_states()
        self.stdout.write(self.style.SUCCESS(f"Advanced {changed} fiscal period(s)."))
