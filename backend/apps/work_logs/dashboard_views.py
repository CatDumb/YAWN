import logging
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.work_logs.models import (
    ApprovedLeave,
    CompanyHoliday,
    FiscalPeriod,
    RemoteWorkException,
    WorkInOfficeRecord,
    WorkIntentionOccurrence,
)
from apps.work_logs.ratio import ratio_ledger
from apps.work_logs.reports import report_for
from apps.work_logs.services import company_today, eligibility_reason
from apps.work_logs.views import membership_for

logger = logging.getLogger("wio.dashboard")


def unavailable_reason(employee, current, today):
    if reason := eligibility_reason(employee, current):
        return reason
    if current < today - timedelta(days=1):
        return "This work date is closed. Ask HR/admin for an audited override."
    if current > today:
        return "Future dates belong in Planner."
    return None


def eligibility_reason_map(employee, dates):
    if not dates:
        return {}
    start = min(dates)
    end = max(dates)
    reasons = {}
    weekday_dates = {current for current in dates if current.weekday() < 5}
    for current in dates:
        if current.weekday() >= 5:
            reasons[current] = ["Weekend"]

    holidays = set(
        CompanyHoliday.objects.filter(
            company=employee.company,
            date__range=(start, end),
        ).values_list("date", flat=True)
    )
    for current in weekday_dates & holidays:
        reasons[current] = ["Public holiday"]

    def overlapping_dates(model):
        rows = model.objects.filter(employee=employee, effective_from__lte=end).filter(
            effective_to__isnull=True
        ) | model.objects.filter(
            employee=employee,
            effective_from__lte=end,
            effective_to__gte=start,
        )
        affected = set()
        for row in rows:
            current = max(row.effective_from, start)
            row_end = min(row.effective_to or end, end)
            while current <= row_end:
                affected.add(current)
                current += timedelta(days=1)
        return affected

    leave_dates = overlapping_dates(ApprovedLeave)
    remote_dates = overlapping_dates(RemoteWorkException)
    for current in weekday_dates - holidays:
        day_reasons = []
        if current in leave_dates:
            day_reasons.append("Approved leave")
        if current in remote_dates:
            day_reasons.append("Approved remote-work exception")
        if day_reasons:
            reasons[current] = day_reasons
    return {current: "; ".join(day_reasons) for current, day_reasons in reasons.items()}


def unavailable_reason_from_eligibility(eligibility, current, today):
    if eligibility:
        return eligibility
    if current < today - timedelta(days=1):
        return "This work date is closed. Ask HR/admin for an audited override."
    if current > today:
        return "Future dates belong in Planner."
    return None


class DashboardTodayView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        employee = membership_for(request.user)
        today = company_today()
        record = WorkInOfficeRecord.objects.filter(employee=employee, work_date=today).first()
        attention = WorkInOfficeRecord.objects.filter(
            employee=employee,
            review_state__in=[
                WorkInOfficeRecord.ReviewState.DRAFT,
                WorkInOfficeRecord.ReviewState.REJECTED,
            ],
        ).order_by("-work_date")[:5]
        return Response(
            {
                "date": today,
                "record_id": record.pk if record else None,
                "review_state": record.review_state if record else None,
                "eligibility_reason": eligibility_reason(employee, today),
                "attention": [
                    {"id": item.pk, "date": item.work_date, "state": item.review_state}
                    for item in attention
                ],
            }
        )


class DashboardRatioView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        employee = membership_for(request.user)
        today = company_today()
        period = FiscalPeriod.objects.filter(
            company=employee.company, start_date__lte=today, end_date__gte=today
        ).first()
        if period is None:
            return Response(
                {
                    "available": False,
                    "message": "No active fiscal period covers today.",
                }
            )
        try:
            report = report_for(employee=employee, start_date=period.start_date, end_date=today)
        except ValidationError as error:
            return Response({"detail": error.messages[0]}, status=400)
        except Exception as error:
            logger.error(
                "dashboard_ratio_failed",
                extra={
                    "error_class": error.__class__.__name__,
                },
            )
            return Response(
                {"detail": "Dashboard ratio is temporarily unavailable. Try again later."},
                status=503,
            )
        remaining = None
        if today < period.end_date:
            try:
                future = ratio_ledger(
                    employee=employee,
                    start_date=today + timedelta(days=1),
                    end_date=period.end_date,
                    as_of_date=period.end_date,
                )
                remaining = sum(1 for day in future["days"] if day.expected_fraction > 0)
            except ValidationError:
                # A future policy gap must not make verified progress unusable.
                remaining = None
            except Exception as error:
                logger.error(
                    "dashboard_future_projection_failed",
                    extra={
                        "error_class": error.__class__.__name__,
                    },
                )
                remaining = None
        balance = report["approved_days"] - report["expected_fraction_sum"]
        return Response(
            {
                "available": True,
                "approved_days": str(report["approved_days"]),
                "self_submitted_days": str(report["self_submitted_days"]),
                "expected_display": report["expected_display"],
                "ratio_display": report["ratio_display"],
                "balance": str(balance.quantize(Decimal("0.01"))),
                "self_submitted_ratio_display": report["self_submitted_ratio_display"],
                "self_submitted_percentage": str(report["self_submitted_percentage"])
                if report["self_submitted_percentage"] is not None
                else None,
                "self_submitted_balance": str(
                    (report["self_submitted_days"] - report["expected_fraction_sum"]).quantize(
                        Decimal("0.01")
                    )
                ),
                "self_approval_applies": False,
                "remaining_eligible_days": remaining,
                "pending_count": report["pending_count"],
                "pending_assignment_count": report["pending_assignment_count"],
                "period_state": period.derived_state,
                "reconciliation_cutoff": period.reconciliation_cutoff,
                "revision": report["revision"].revision if report["revision"] else None,
                "baseline_included": report["baseline_included"],
            }
        )


class DashboardActivityView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        employee = membership_for(request.user)
        today = company_today()
        try:
            year = int(request.query_params.get("year", today.year))
            month = int(request.query_params.get("month", today.month))
            _, days_in_month = monthrange(year, month)
        except ValueError:
            return Response({"detail": "year and month must be valid numbers."}, status=400)
        month_start = date(year, month, 1)
        month_end = date(year, month, days_in_month)
        records = WorkInOfficeRecord.objects.filter(
            employee=employee, work_date__range=(month_start, month_end)
        ).order_by("-work_date")[:5]
        intentions = WorkIntentionOccurrence.objects.filter(
            employee=employee, date__gte=today
        ).order_by("date")[:5]
        return Response(
            {
                "records": [
                    {"id": item.pk, "date": item.work_date, "state": item.review_state}
                    for item in records
                ],
                "intentions": [
                    {
                        "id": item.pk,
                        "date": item.date,
                        "location": item.location,
                        "commitment": item.commitment,
                    }
                    for item in intentions
                ],
            }
        )


class DashboardHeatmapView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        employee = membership_for(request.user)
        today = company_today()
        try:
            year = int(request.query_params.get("year", today.year))
            month = int(request.query_params.get("month", today.month))
            _, days_in_month = monthrange(year, month)
        except ValueError:
            return Response({"detail": "year and month must be valid numbers."}, status=400)
        dates = [date(year, month, day) for day in range(1, days_in_month + 1)]
        records = {
            item.work_date: item
            for item in WorkInOfficeRecord.objects.filter(employee=employee, work_date__in=dates)
        }
        intentions = {
            item.date: item
            for item in WorkIntentionOccurrence.objects.filter(employee=employee, date__in=dates)
        }
        ineligible = eligibility_reason_map(employee, dates)
        return Response(
            [
                {
                    "date": current,
                    "record_id": records[current].pk if current in records else None,
                    "review_state": records[current].review_state if current in records else None,
                    "intention": intentions[current].location if current in intentions else None,
                    "commitment": intentions[current].commitment if current in intentions else None,
                    "ineligible_reason": ineligible.get(current),
                    "unavailable_reason": unavailable_reason_from_eligibility(
                        ineligible.get(current), current, today
                    ),
                    "action": (
                        "open"
                        if current in records
                        else "create"
                        if current >= today - timedelta(days=1)
                        and current <= today
                        and current not in ineligible
                        else None
                    ),
                }
                for current in dates
            ]
        )
