from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership, User
from apps.work_logs.models import (
    FiscalPeriod,
    WorkIntentionOccurrence,
    WorkIntentionSeries,
)
from apps.work_logs.planner import save_intentions


@pytest.fixture
def planner_employee(db):
    company = Company.objects.create(name="Planner choices", slug="planner-choices")
    employee = CompanyMembership.objects.create(
        user=User.objects.create_user(email="planner-choices@example.com"),
        company=company,
    )
    today = timezone.localdate()
    FiscalPeriod.objects.create(
        company=company,
        name="Active planner period",
        start_date=today,
        end_date=today + timedelta(days=30),
        state=FiscalPeriod.State.ACTIVE,
    )
    return employee


@pytest.mark.parametrize(
    ("location", "commitment", "error"),
    [
        ("somewhere", "firm", "location"),
        ("office", "maybe", "commitment"),
    ],
)
def test_save_intentions_rejects_invalid_choices(
    planner_employee,
    location,
    commitment,
    error,
):
    today = timezone.localdate()

    with pytest.raises(ValidationError, match=error):
        save_intentions(
            employee=planner_employee,
            start=today,
            end=today,
            location=location,
            commitment=commitment,
        )

    assert not WorkIntentionSeries.objects.filter(employee=planner_employee).exists()
    assert not WorkIntentionOccurrence.objects.filter(employee=planner_employee).exists()


@pytest.mark.parametrize(
    ("location", "commitment", "field"),
    [
        ("somewhere", "firm", "location"),
        ("office", "maybe", "commitment"),
    ],
)
def test_planner_api_rejects_invalid_choices(
    client,
    planner_employee,
    location,
    commitment,
    field,
):
    client.force_login(planner_employee.user)

    response = client.post(
        "/api/v1/planner/",
        {
            "start_date": timezone.localdate().isoformat(),
            "location": location,
            "commitment": commitment,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert field in response.json()
    assert not WorkIntentionSeries.objects.filter(employee=planner_employee).exists()
    assert not WorkIntentionOccurrence.objects.filter(employee=planner_employee).exists()
