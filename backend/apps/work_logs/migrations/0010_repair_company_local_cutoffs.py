from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import migrations
from django.utils import timezone
from django.utils.dateparse import parse_datetime

EVENT_TYPE = "work_logs.fiscal_cutoff_timezone_repaired"
TARGET_TYPE = "work_logs.FiscalPeriod"
BATCH_SIZE = 500
# Migration 0004 ran while the Phase 3 deployment contract and settings default
# fixed the application timezone to Asia/Ho_Chi_Minh. Keep that provenance
# immutable here so later environment changes cannot alter data classification.
LEGACY_DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"


def default_cutoff(end_date, timezone_name):
    cutoff_day = end_date + timedelta(days=14)
    return timezone.make_aware(
        datetime.combine(cutoff_day, time.max),
        ZoneInfo(timezone_name),
    )


def repair_company_local_cutoffs(apps, schema_editor):
    AuditEvent = apps.get_model("audit", "AuditEvent")
    FiscalPeriod = apps.get_model("work_logs", "FiscalPeriod")

    cursor = 0
    while True:
        periods = list(
            FiscalPeriod.objects.filter(pk__gt=cursor)
            .select_related("company")
            .order_by("pk")[:BATCH_SIZE]
        )
        if not periods:
            break
        cursor = periods[-1].pk
        changed = []
        events = []
        for period in periods:
            legacy_cutoff = default_cutoff(period.end_date, LEGACY_DEFAULT_TIMEZONE)
            desired_cutoff = default_cutoff(period.end_date, period.company.timezone)
            if period.reconciliation_cutoff != legacy_cutoff or legacy_cutoff == desired_cutoff:
                continue
            previous_cutoff = period.reconciliation_cutoff
            period.reconciliation_cutoff = desired_cutoff
            changed.append(period)
            events.append(
                AuditEvent(
                    event_type=EVENT_TYPE,
                    target_type=TARGET_TYPE,
                    target_id=str(period.pk),
                    metadata={
                        "actor_role": "system",
                        "actor_company_id": period.company_id,
                        "reason": "Repair legacy default cutoff to company-local day end",
                        "previous_cutoff": previous_cutoff.isoformat(),
                        "new_cutoff": desired_cutoff.isoformat(),
                    },
                )
            )
        if changed:
            FiscalPeriod.objects.bulk_update(
                changed,
                ["reconciliation_cutoff"],
                batch_size=BATCH_SIZE,
            )
            AuditEvent.objects.bulk_create(events, batch_size=BATCH_SIZE)


def reverse_company_local_cutoffs(apps, schema_editor):
    AuditEvent = apps.get_model("audit", "AuditEvent")
    FiscalPeriod = apps.get_model("work_logs", "FiscalPeriod")

    periods = []
    event_ids = []
    events = AuditEvent.objects.filter(
        event_type=EVENT_TYPE,
        target_type=TARGET_TYPE,
    ).order_by("-pk")
    for event in events.iterator(chunk_size=BATCH_SIZE):
        period = FiscalPeriod.objects.filter(pk=event.target_id).first()
        if period is None:
            raise RuntimeError(
                f"Cannot reverse fiscal cutoff repair for missing period {event.target_id}."
            )
        expected_cutoff = parse_datetime(event.metadata["new_cutoff"])
        if period.reconciliation_cutoff != expected_cutoff:
            raise RuntimeError(
                f"Cannot reverse fiscal cutoff repair after period {event.target_id} changed."
            )
        period.reconciliation_cutoff = parse_datetime(event.metadata["previous_cutoff"])
        periods.append(period)
        event_ids.append(event.pk)
        if len(event_ids) >= BATCH_SIZE:
            FiscalPeriod.objects.bulk_update(
                periods,
                ["reconciliation_cutoff"],
                batch_size=BATCH_SIZE,
            )
            AuditEvent.objects.filter(pk__in=event_ids).delete()
            periods.clear()
            event_ids.clear()
    if event_ids:
        FiscalPeriod.objects.bulk_update(
            periods,
            ["reconciliation_cutoff"],
            batch_size=BATCH_SIZE,
        )
        AuditEvent.objects.filter(pk__in=event_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("work_logs", "0009_repair_pending_approval_ownership"),
    ]

    operations = [
        migrations.RunPython(
            repair_company_local_cutoffs,
            reverse_company_local_cutoffs,
        ),
    ]
