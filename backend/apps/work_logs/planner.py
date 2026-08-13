import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils.html import strip_tags

from apps.accounts.models import CompanyMembership, UserPreference
from apps.work_logs.models import FiscalPeriod, WorkIntentionOccurrence, WorkIntentionSeries
from apps.work_logs.ratio import ratio_ledger
from apps.work_logs.services import company_today, eligibility_reason

logger = logging.getLogger("wio.planner")


class PlannerPurgeNotificationDeliveryError(Exception):
    """Raised when a Planner purge notification cannot be delivered."""


PLANNER_PURGE_EMAIL = {
    UserPreference.Language.ENGLISH: {
        "subject": "Your private Planner intentions will be purged",
        "message": (
            "Private Planner intentions for {period} ({start} through {end}) will be purged "
            "after cutoff {cutoff}. Open {url} if you want to review or change them before then."
        ),
    },
    UserPreference.Language.VIETNAMESE: {
        "subject": "Ý định riêng tư trong Planner sẽ được xóa",
        "message": (
            "Ý định riêng tư trong Planner cho {period} ({start} đến {end}) sẽ được xóa sau "
            "thời điểm chốt {cutoff}. Mở {url} nếu bạn muốn xem lại hoặc thay đổi "
            "trước thời điểm đó."
        ),
    },
}


def notify_planner_purge(period):
    """Notify affected users before purge without exposing private intention content."""
    employees = (
        CompanyMembership.objects.filter(
            company=period.company,
            intentions__date__range=(period.start_date, period.end_date),
        )
        .select_related("user")
        .distinct()
        .order_by("pk")
    )
    sent = 0
    for employee in employees:
        preference = UserPreference.objects.filter(user=employee.user).first()
        language = preference.language if preference else UserPreference.Language.ENGLISH
        copy = PLANNER_PURGE_EMAIL.get(
            language,
            PLANNER_PURGE_EMAIL[UserPreference.Language.ENGLISH],
        )
        try:
            send_mail(
                subject=copy["subject"],
                message=copy["message"].format(
                    period=period.name,
                    start=period.start_date.isoformat(),
                    end=period.end_date.isoformat(),
                    cutoff=period.reconciliation_cutoff.isoformat(),
                    url=f"{settings.WIO_APP_URL}/planner",
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[employee.user.email],
                fail_silently=False,
            )
        except Exception as error:
            logger.error(
                "planner_purge_notification_failed",
                extra={"error_class": error.__class__.__name__},
            )
            raise PlannerPurgeNotificationDeliveryError from error
        sent += 1
    return {"notifications_sent": sent}


def active_period(employee):
    today = company_today(employee.company)
    period = FiscalPeriod.objects.filter(
        company=employee.company,
        state=FiscalPeriod.State.ACTIVE,
        start_date__lte=today,
        end_date__gte=today,
    ).first()
    if period is None:
        raise ValidationError("Planner is available only in the current active fiscal period.")
    return period


def preview(*, employee, start, end, weekdays=None):
    period = active_period(employee)
    if start > end:
        raise ValidationError("Start date must not be after end date.")
    if start < company_today(employee.company) or end > period.end_date:
        raise ValidationError("Intentions must be today or later inside the active fiscal period.")
    allowed = set(weekdays or range(7))
    result = []
    existing = set(
        WorkIntentionOccurrence.objects.filter(
            employee=employee, date__range=(start, end)
        ).values_list("date", flat=True)
    )
    for day in [
        start + timedelta(days=index)
        for index in range((end - start).days + 1)
        if (start + timedelta(days=index)).weekday() in allowed
    ]:
        reason = eligibility_reason(employee, day)
        result.append(
            {
                "date": day,
                "reason": reason,
                "existing": day in existing,
                "eligible": reason is None,
            }
        )
    return result


def projection(*, employee):
    """Return private plan coverage. This never contributes verified WIO credit."""
    period = active_period(employee)
    ledger = ratio_ledger(
        employee=employee,
        start_date=period.start_date,
        end_date=period.end_date,
        as_of_date=period.end_date,
    )
    expected_by_date = {day.date: day.expected_fraction for day in ledger["days"]}
    intentions = WorkIntentionOccurrence.objects.filter(
        employee=employee,
        date__range=(period.start_date, period.end_date),
        location="office",
    ).values_list("date", "commitment")
    firm = {date for date, commitment in intentions if commitment == "firm"}
    flexible = {date for date, commitment in intentions if commitment == "flexible"} - firm
    eligible = {day for day, fraction in expected_by_date.items() if fraction > 0}
    expected_total = sum(expected_by_date.values(), start=Decimal("0"))
    minimum = sum((expected_by_date[day] for day in firm & eligible), start=Decimal("0"))
    optimistic = sum((expected_by_date[day] for day in flexible & eligible), start=Decimal("0"))
    return {
        "period": period,
        "expected_fraction_sum": str(expected_total),
        "minimum_planned_fraction": str(minimum),
        "maximum_planned_fraction": str(minimum + optimistic),
        "gap_after_maximum": str(max(expected_total - minimum - optimistic, Decimal("0"))),
        "firm_office_days": len(firm & eligible),
        "flexible_office_days": len(flexible & eligible),
        "unplanned_eligible_days": len(eligible - firm - flexible),
    }


def _intention_values(*, record, location=None, commitment=None, note=None):
    values = {
        "location": location if location is not None else record.location,
        "commitment": commitment if commitment is not None else record.commitment,
        "note": note if note is not None else record.note,
    }
    return _validated_intention_values(**values)


def _validated_intention_values(*, location, commitment, note):
    if location not in WorkIntentionSeries.LocationChoice.values:
        raise ValidationError("Planner location must be Office or Home.")
    if commitment not in WorkIntentionSeries.CommitmentChoice.values:
        raise ValidationError("Planner commitment must be Firm or Flexible.")
    if strip_tags(note) != note:
        raise ValidationError("Planner note must be plain text.")
    if len(note) > 300:
        raise ValidationError("Planner note must be 300 characters or fewer.")
    return {"location": location, "commitment": commitment, "note": note}


@transaction.atomic
def edit_intention(
    *, employee, record_id, version, scope, location=None, commitment=None, note=None
):
    record = (
        WorkIntentionOccurrence.objects.select_for_update()
        .filter(employee=employee, pk=record_id)
        .first()
    )
    if record is None:
        raise ValidationError("Intention not found.")
    if version is None or record.version != version:
        raise RuntimeError("stale")
    if eligibility_reason(employee, record.date):
        raise ValidationError("Excluded intentions are read-only. Delete it instead.")
    values = _intention_values(record=record, location=location, commitment=commitment, note=note)
    today = company_today(employee.company)
    if scope == "one":
        series_id = record.series_id
        record.location = values["location"]
        record.commitment = values["commitment"]
        record.note = values["note"]
        record.series = None
        record.version += 1
        record.save(update_fields=[*values, "series", "version", "updated_at"])
        if series_id is not None:
            WorkIntentionSeries.objects.filter(pk=series_id, occurrences__isnull=True).delete()
        return [record]
    if record.date < today:
        raise ValidationError("Elapsed intentions cannot be bulk-rewritten.")
    if record.series_id is None:
        raise ValidationError("This intention is not part of a series.")
    series = WorkIntentionSeries.objects.select_for_update().get(pk=record.series_id)
    if scope == "future":
        new_series = WorkIntentionSeries.objects.create(
            employee=employee,
            location=values["location"],
            commitment=values["commitment"],
            note=values["note"],
            weekdays=series.weekdays,
            starts_on=record.date,
            ends_on=series.ends_on,
        )
        if series.starts_on < record.date:
            series.ends_on = record.date - timedelta(days=1)
            series.version += 1
            series.save(update_fields=["ends_on", "version"])
        records = list(
            WorkIntentionOccurrence.objects.select_for_update().filter(
                series=series, date__gte=record.date
            )
        )
        for item in records:
            item.series = new_series
            if eligibility_reason(employee, item.date):
                item.version += 1
                item.save(update_fields=["series", "version", "updated_at"])
                continue
            item.location = values["location"]
            item.commitment = values["commitment"]
            item.note = values["note"]
            item.version += 1
            item.save(update_fields=["series", *values, "version", "updated_at"])
        if series.starts_on == record.date:
            series.delete()
        return records
    if scope == "series":
        series.location = values["location"]
        series.commitment = values["commitment"]
        series.note = values["note"]
        series.version += 1
        series.save(update_fields=[*values, "version"])
        records = list(
            WorkIntentionOccurrence.objects.select_for_update().filter(
                series=series, date__gte=today
            )
        )
        for item in records:
            if eligibility_reason(employee, item.date):
                continue
            item.location = values["location"]
            item.commitment = values["commitment"]
            item.note = values["note"]
            item.version += 1
            item.save(update_fields=[*values, "version", "updated_at"])
        return records
    raise ValidationError("Edit scope must be one, future, or series.")


@transaction.atomic
def save_intentions(
    *, employee, start, end, location, commitment, note="", weekdays=None, replace=False
):
    values = _validated_intention_values(
        location=location,
        commitment=commitment,
        note=note,
    )
    location = values["location"]
    commitment = values["commitment"]
    note = values["note"]
    planned = preview(employee=employee, start=start, end=end, weekdays=weekdays)
    series = None

    def materialize_series():
        nonlocal series
        if series is None:
            series = WorkIntentionSeries.objects.create(
                employee=employee,
                location=location,
                commitment=commitment,
                note=note,
                weekdays=list(weekdays or []),
                starts_on=start,
                ends_on=end,
            )
        return series

    created = []
    for item in planned:
        if not item["eligible"]:
            continue
        occurrence = WorkIntentionOccurrence.objects.filter(
            employee=employee, date=item["date"]
        ).first()
        if occurrence and not replace:
            continue
        if occurrence:
            occurrence.location = location
            occurrence.commitment = commitment
            occurrence.note = note
            occurrence.series = materialize_series()
            occurrence.excluded_reason = ""
            occurrence.version += 1
            occurrence.save()
        else:
            occurrence = WorkIntentionOccurrence.objects.create(
                employee=employee,
                date=item["date"],
                location=location,
                commitment=commitment,
                note=note,
                series=materialize_series(),
            )
        created.append(occurrence)
    return created


@transaction.atomic
def purge_intentions_for_period(period):
    """Remove private contents only after all fiscal finalization steps can commit."""
    occurrences = WorkIntentionOccurrence.objects.filter(
        employee__company=period.company,
        date__range=(period.start_date, period.end_date),
    )
    count = occurrences.count()
    series_ids = list(
        occurrences.exclude(series__isnull=True).values_list("series_id", flat=True).distinct()
    )
    occurrences.delete()
    series_count, _ = WorkIntentionSeries.objects.filter(
        employee__company=period.company, pk__in=series_ids
    ).delete()
    return {"occurrences_purged": count, "series_purged": series_count}
