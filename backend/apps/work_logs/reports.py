import csv
from datetime import date
from io import StringIO

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone

from apps.work_logs.models import FinalizedLedgerRevision, FiscalPeriod, WorkInOfficeRecord
from apps.work_logs.ratio import calculate_ratio, ratio_ledger

CSV_COPY = {
    "en": {
        "headers": ["Date", "Eligible", "Reason", "Expected fraction", "Approved credit"],
        "period": "Fiscal period",
        "period_id": "Fiscal period ID",
        "period_state": "Period state",
        "range": "Range",
        "range_separator": "to",
        "revision": "Revision",
        "live": "live",
        "true": "Yes",
        "false": "No",
        "states": {
            FiscalPeriod.State.UPCOMING: "Upcoming",
            FiscalPeriod.State.ACTIVE: "Active",
            FiscalPeriod.State.RECONCILIATION: "Reconciliation",
            FiscalPeriod.State.FINAL: "Final",
        },
    },
    "vi": {
        "headers": ["Ngày", "Đủ điều kiện", "Lý do", "Phần kỳ vọng", "Tín dụng đã duyệt"],
        "period": "Kỳ tài chính",
        "period_id": "ID kỳ tài chính",
        "period_state": "Trạng thái kỳ",
        "range": "Khoảng ngày",
        "range_separator": "đến",
        "revision": "Bản chốt",
        "live": "đang tính",
        "true": "Có",
        "false": "Không",
        "states": {
            FiscalPeriod.State.UPCOMING: "Sắp tới",
            FiscalPeriod.State.ACTIVE: "Đang hoạt động",
            FiscalPeriod.State.RECONCILIATION: "Đang đối soát",
            FiscalPeriod.State.FINAL: "Đã chốt",
        },
    },
}


def period_for(company, day: date):
    period = FiscalPeriod.objects.filter(
        company=company, start_date__lte=day, end_date__gte=day
    ).first()
    if period is None:
        raise ValidationError("Selected range must be inside one fiscal period.")
    return period


def _as_json_day(day, record=None):
    return {
        "date": day.date.isoformat(),
        "eligible": day.eligible,
        "reason": day.reason,
        "assignment_status": day.assignment_status,
        "rule_version": day.rule_version,
        "expected_fraction": str(day.expected_fraction),
        "approval_credit": str(day.approval_credit),
        "review_state": record.review_state if record else None,
        "location_choice": record.location_choice if record else None,
    }


def report_for(*, employee, start_date, end_date):
    if start_date > end_date:
        raise ValidationError("Start date must not be after end date.")
    period = period_for(employee.company, start_date)
    if end_date > period.end_date:
        raise ValidationError("Cross-period calculations are not supported.")
    revision = None
    frozen_rows_by_date = None
    if period.state == FiscalPeriod.State.FINAL:
        revision = (
            FinalizedLedgerRevision.objects.filter(period=period, employee=employee)
            .order_by("-revision")
            .first()
        )
        if revision is None:
            raise ValidationError("Finalized report revision is unavailable.")
        rows = [
            row
            for row in revision.ledger
            if start_date.isoformat() <= row["date"] <= end_date.isoformat()
        ]
        frozen_rows_by_date = {date.fromisoformat(row["date"]): row for row in rows}
        from decimal import Decimal

        from apps.work_logs.ratio import LedgerDay

        result = calculate_ratio(
            [
                LedgerDay(
                    date=date.fromisoformat(row["date"]),
                    eligible=row["eligible"],
                    reason=row["reason"],
                    assignment_status=row["assignment_status"],
                    rule_version=row["rule_version"],
                    expected_fraction=Decimal(row["expected_fraction"]),
                    approval_credit=Decimal(row["approval_credit"]),
                )
                for row in rows
            ]
        )
    else:
        result = ratio_ledger(
            employee=employee,
            start_date=start_date,
            end_date=end_date,
            as_of_date=min(timezone.localdate(), end_date),
        )
    pending = WorkInOfficeRecord.objects.filter(
        employee=employee,
        work_date__range=(start_date, end_date),
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
    ).count()
    pending_assignment = WorkInOfficeRecord.objects.filter(
        employee=employee,
        work_date__range=(start_date, end_date),
        review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
    ).count()
    records = {}
    if frozen_rows_by_date is None:
        records = {
            item.work_date: item
            for item in WorkInOfficeRecord.objects.filter(
                employee=employee, work_date__range=(start_date, end_date)
            )
        }
    ledger = []
    for day in result["days"]:
        row = (
            dict(frozen_rows_by_date[day.date])
            if frozen_rows_by_date is not None
            else _as_json_day(day, records.get(day.date))
        )
        ledger.append(row)
    return {
        **result,
        "period": period,
        "revision": revision,
        "pending_count": pending,
        "pending_assignment_count": pending_assignment,
        "ledger": ledger,
    }


def csv_response(report, *, start_date, end_date, language="en"):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = "attachment; filename=work-in-office-report.csv"
    output = StringIO()
    writer = csv.writer(output)
    copy = CSV_COPY.get(language, CSV_COPY["en"])

    def safe(value):
        text = str(value or "")
        return f"'{text}" if text[:1] in {"=", "+", "-", "@"} else text

    state = copy["states"].get(report["period"].state, report["period"].state)
    writer.writerow([copy["period"], safe(report["period"].name)])
    writer.writerow([copy["period_id"], report["period"].pk])
    writer.writerow([copy["period_state"], safe(state)])
    writer.writerow(
        [
            copy["range"],
            f"{start_date.isoformat()} {copy['range_separator']} {end_date.isoformat()}",
        ]
    )
    revision = report["revision"].revision if report["revision"] else copy["live"]
    writer.writerow([copy["revision"], safe(revision)])
    writer.writerow(copy["headers"])
    for row in report["ledger"]:
        writer.writerow(
            [
                safe(row["date"]),
                copy["true"] if row["eligible"] else copy["false"],
                safe(row["reason"]),
                safe(row["expected_fraction"]),
                safe(row["approval_credit"]),
            ]
        )
    response.write("\ufeff" + output.getvalue())
    return response


def freeze_period_ledgers(period):
    """Finalization step: freeze one complete, reproducible ledger per employee."""
    employees = period.company.memberships.filter(is_active=True)
    created = 0
    correction_token = period.reopened_at.isoformat() if period.reopened_at else None
    for employee in employees:
        latest = (
            FinalizedLedgerRevision.objects.filter(period=period, employee=employee)
            .order_by("-revision")
            .first()
        )
        if latest and correction_token is None:
            continue
        if latest and latest.input_versions.get("correction_reopened_at") == correction_token:
            continue
        records = {
            item.work_date: item
            for item in WorkInOfficeRecord.objects.filter(
                employee=employee,
                work_date__range=(period.start_date, period.end_date),
            )
        }
        result = ratio_ledger(
            employee=employee,
            start_date=period.start_date,
            end_date=period.end_date,
            as_of_date=period.end_date,
        )
        input_versions = {"frozen_at": timezone.now().isoformat()}
        if correction_token:
            input_versions["correction_reopened_at"] = correction_token
            if latest:
                input_versions["predecessor_revision"] = latest.revision
        FinalizedLedgerRevision.objects.create(
            period=period,
            employee=employee,
            revision=latest.revision + 1 if latest else 1,
            predecessor=latest if correction_token else None,
            summary={
                "approved_days": str(result["approved_days"]),
                "expected_fraction_sum": str(result["expected_fraction_sum"]),
                "percentage": str(result["percentage"])
                if result["percentage"] is not None
                else None,
            },
            ledger=[_as_json_day(day, records.get(day.date)) for day in result["days"]],
            input_versions=input_versions,
        )
        created += 1
    return {"revisions_created": created}
