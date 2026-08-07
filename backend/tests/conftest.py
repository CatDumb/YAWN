from datetime import UTC, datetime

import pytest
from django.utils import timezone


@pytest.fixture(autouse=True)
def freeze_business_date(monkeypatch):
    # 00:30 on July 24 in the default company timezone. Keeping the instant
    # close to midnight makes tests exercise timezone conversion while every
    # business-date consumer still reads one clock.
    fixed_now = datetime(2026, 7, 23, 17, 30, tzinfo=UTC)
    original_localdate = timezone.localdate

    def fixed_localdate(value=None, timezone=None):
        return original_localdate(value or fixed_now, timezone)

    monkeypatch.setattr(timezone, "now", lambda: fixed_now)
    monkeypatch.setattr(timezone, "localdate", fixed_localdate)
    return fixed_now


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
