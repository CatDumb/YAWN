import logging
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.work_logs.reports import csv_response, period_for, report_for
from apps.work_logs.services import company_today
from apps.work_logs.views import membership_for

logger = logging.getLogger("wio.reports")


def selected_range(request, membership):
    today = company_today()
    if "start_date" not in request.query_params and "end_date" not in request.query_params:
        period = period_for(membership.company, today)
        return period.start_date, min(today, period.end_date)
    if "start_date" not in request.query_params or "end_date" not in request.query_params:
        raise ValidationError("Report range requires both start_date and end_date.")
    try:
        return (
            date.fromisoformat(request.query_params["start_date"]),
            date.fromisoformat(request.query_params["end_date"]),
        )
    except ValueError as error:
        raise ValidationError("Report dates must use ISO format YYYY-MM-DD.") from error


def error_detail(error):
    return error.messages[0] if hasattr(error, "messages") else str(error)


def safe_failure_response(message, *, event_type, error):
    logger.error(
        event_type,
        extra={
            "error_class": error.__class__.__name__,
        },
    )
    return Response({"detail": message}, status=503)


class ReportView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        membership = membership_for(request.user)
        try:
            start, end = selected_range(request, membership)
            report = report_for(employee=membership, start_date=start, end_date=end)
        except ValidationError as error:
            return Response({"detail": error_detail(error)}, status=400)
        except Exception as error:
            return safe_failure_response(
                "Report is temporarily unavailable. Try again later.",
                event_type="report_generation_failed",
                error=error,
            )
        return Response(
            {
                "approved_days": str(report["approved_days"]),
                "expected_fraction_sum": str(report["expected_fraction_sum"]),
                "expected_display": report["expected_display"],
                "balance": str(
                    (report["approved_days"] - report["expected_fraction_sum"]).quantize(
                        Decimal("0.01")
                    )
                ),
                "percentage": str(report["percentage"])
                if report["percentage"] is not None
                else None,
                "ratio_display": report["ratio_display"],
                "pending_count": report["pending_count"],
                "pending_assignment_count": report["pending_assignment_count"],
                "period_state": report["period"].derived_state,
                "revision": report["revision"].revision if report["revision"] else None,
                "baseline_included": report["baseline_included"],
                "start_date": start,
                "end_date": end,
                "ledger": report["ledger"],
            }
        )


class ReportCSVView(APIView):
    @extend_schema(responses=OpenApiTypes.BINARY)
    def get(self, request):
        membership = membership_for(request.user)
        try:
            start, end = selected_range(request, membership)
            report = report_for(employee=membership, start_date=start, end_date=end)
            return csv_response(
                report,
                start_date=start,
                end_date=end,
                language=request.query_params.get("language", "en"),
            )
        except ValidationError as error:
            return Response({"detail": error_detail(error)}, status=400)
        except Exception as error:
            return safe_failure_response(
                "Report export is temporarily unavailable. Try again later.",
                event_type="report_export_failed",
                error=error,
            )
