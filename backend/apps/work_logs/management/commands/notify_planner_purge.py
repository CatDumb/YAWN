from django.core.management.base import BaseCommand, CommandError

from apps.work_logs.models import FiscalPeriod
from apps.work_logs.planner import PlannerPurgeNotificationDeliveryError, notify_planner_purge


class Command(BaseCommand):
    help = "Send private Planner purge notifications for a fiscal period."

    def add_arguments(self, parser):
        parser.add_argument("period_id", type=int)

    def handle(self, *args, **options):
        try:
            period = FiscalPeriod.objects.get(pk=options["period_id"])
        except FiscalPeriod.DoesNotExist as error:
            raise CommandError("Fiscal period not found.") from error
        try:
            result = notify_planner_purge(period)
        except PlannerPurgeNotificationDeliveryError as error:
            raise CommandError("Planner purge notification delivery failed.") from error
        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {result['notifications_sent']} Planner purge notification(s)."
            )
        )
