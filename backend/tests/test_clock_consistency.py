from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership, User
from apps.work_logs.models import BaseLocation, EmployeeBaseLocationAssignment, FiscalPeriod
from apps.work_logs.planner import preview
from apps.work_logs.services import company_date, company_today


@override_settings(TIME_ZONE="Asia/Ho_Chi_Minh")
def test_frozen_clock_agrees_at_company_midnight(db, freeze_business_date):
    company = Company.objects.create(
        name="Clock Company",
        slug="clock-company",
        timezone="Asia/Ho_Chi_Minh",
    )
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="clock@example.com"),
        company=company,
    )
    location = BaseLocation.objects.create(
        company=company,
        name="Midnight Office",
        code="midnight-office",
    )
    company_timezone = ZoneInfo(company.timezone)
    expected_date = date(2026, 7, 24)

    assert timezone.now() == freeze_business_date
    assert timezone.now().astimezone(company_timezone).time() == time(0, 30)
    assert timezone.localdate() == expected_date
    assert company_date(timezone.now(), company) == expected_date
    assert company_today(company) == expected_date

    EmployeeBaseLocationAssignment.objects.create(
        employee=employee,
        base_location=location,
        effective_from=expected_date,
        effective_to=expected_date,
    )

    employee.refresh_from_db()
    assert employee.base_location == location


@override_settings(TIME_ZONE="UTC")
def test_company_local_date_drives_planner_and_dashboard(client, db, monkeypatch):
    fixed_now = datetime(2026, 7, 31, 17, 30, tzinfo=UTC)
    monkeypatch.setattr(timezone, "now", lambda: fixed_now)
    company_date = date(2026, 8, 1)
    company = Company.objects.create(
        name="Company date",
        slug="company-date",
        timezone="Asia/Ho_Chi_Minh",
    )
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="company-date@example.com"),
        company=company,
    )
    FiscalPeriod.objects.create(
        company=company,
        name="August",
        start_date=company_date,
        end_date=date(2026, 8, 31),
        state=FiscalPeriod.State.ACTIVE,
    )

    planned = preview(employee=employee, start=company_date, end=company_date)
    assert planned[0]["date"] == company_date

    client.force_login(employee.user)
    today_response = client.get("/api/v1/dashboard/today/")
    heatmap_response = client.get("/api/v1/dashboard/heatmap/")

    assert today_response.status_code == 200
    assert today_response.json()["date"] == "2026-08-01"
    assert heatmap_response.status_code == 200
    assert heatmap_response.json()[0]["date"] == "2026-08-01"
    assert heatmap_response.json()[-1]["date"] == "2026-08-31"
