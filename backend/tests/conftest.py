from datetime import date

import pytest
from django.utils import timezone


@pytest.fixture(autouse=True)
def freeze_business_date(monkeypatch):
    fixed_date = date(2026, 7, 24)
    original_localdate = timezone.localdate

    def fixed_localdate(value=None, timezone=None):
        return fixed_date if value is None else original_localdate(value, timezone)

    monkeypatch.setattr(timezone, "localdate", fixed_localdate)
    for module in (
        "apps.work_logs.dashboard_views",
        "apps.work_logs.planner",
        "apps.work_logs.planner_views",
        "apps.work_logs.profile_views",
        "apps.work_logs.report_views",
        "apps.work_logs.services",
        "apps.work_logs.views",
    ):
        monkeypatch.setattr(f"{module}.company_today", lambda: fixed_date)


@pytest.fixture(autouse=True)
def use_plain_staticfiles_storage(settings):
    settings.MIDDLEWARE = [
        middleware
        for middleware in settings.MIDDLEWARE
        if middleware != "whitenoise.middleware.WhiteNoiseMiddleware"
    ]
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
