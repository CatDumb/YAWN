from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership, User
from apps.work_logs.models import (
    ApprovedLeave,
    CompanyHoliday,
    FiscalPeriod,
    ProjectStatusRule,
    RemoteWorkException,
    WorkIntentionOccurrence,
)
from apps.work_logs.planner import save_intentions


@pytest.mark.parametrize(
    ("exclusion_kind", "expected_reason"),
    [
        ("holiday", "Public holiday"),
        ("leave", "Approved leave"),
        ("remote", "Approved remote-work exception"),
    ],
)
@pytest.mark.django_db
def test_later_eligibility_change_dynamically_excludes_saved_intention(
    client, exclusion_kind, expected_reason
):
    today = timezone.localdate()
    planned_date = today + timedelta(days=(7 - today.weekday()) % 7)
    company = Company.objects.create(name="Yawn", slug="yawn")
    user = User.objects.create_user(email=f"dynamic-{exclusion_kind}@example.com")
    employee = CompanyMembership.objects.create(user=user, company=company)
    FiscalPeriod.objects.create(
        company=company,
        name="Current",
        start_date=today,
        end_date=today + timedelta(days=30),
        state=FiscalPeriod.State.ACTIVE,
    )
    ProjectStatusRule.objects.create(
        company=company,
        assignment_status=ProjectStatusRule.AssignmentStatus.BENCHED,
        effective_from=today,
        expected_fraction=Decimal("0.50"),
    )
    occurrence = save_intentions(
        employee=employee,
        start=planned_date,
        end=planned_date,
        location="office",
        commitment="firm",
        note="Private plan",
    )[0]
    client.force_login(user)

    if exclusion_kind == "holiday":
        CompanyHoliday.objects.create(company=company, date=planned_date, name="New holiday")
    elif exclusion_kind == "leave":
        ApprovedLeave.objects.create(
            employee=employee,
            effective_from=planned_date,
            effective_to=planned_date,
            reason="Private leave reason",
        )
    else:
        RemoteWorkException.objects.create(
            employee=employee,
            effective_from=planned_date,
            effective_to=planned_date,
            reason="Private remote reason",
        )

    intentions = client.get("/api/v1/planner/")
    edit = client.patch(
        f"/api/v1/planner/{occurrence.pk}/",
        {"version": occurrence.version, "scope": "one", "note": "Must not change"},
        content_type="application/json",
    )
    projected = client.get("/api/v1/planner/projection/")

    assert intentions.status_code == 200
    assert intentions.json()[0]["excluded_reason"] == expected_reason
    assert edit.status_code == 400
    assert edit.json() == {"detail": "Excluded intentions are read-only. Delete it instead."}
    assert projected.status_code == 200
    assert projected.json()["minimum_planned_fraction"] == "0"
    assert projected.json()["firm_office_days"] == 0
    occurrence.refresh_from_db()
    assert occurrence.excluded_reason == ""
    assert occurrence.note == "Private plan"
    assert WorkIntentionOccurrence.objects.filter(pk=occurrence.pk).exists()
