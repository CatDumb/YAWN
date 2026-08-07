from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Company, CompanyMembership, User, UserPreference
from apps.accounts.serializers import UserPreferenceSerializer
from apps.accounts.views import UserPreferenceView


@pytest.mark.django_db(transaction=True)
def test_concurrent_preference_updates_allow_one_winner_and_conflict_loser(monkeypatch):
    company = Company.objects.create(name="Yawn", slug="yawn")
    user = User.objects.create_user(email="preference-race@example.com")
    CompanyMembership.objects.create(user=user, company=company)
    preference = UserPreference.objects.create(user=user)
    both_requests_validated = Barrier(2)
    original_is_valid = UserPreferenceSerializer.is_valid

    def synchronize_after_stale_read(serializer, *args, **kwargs):
        result = original_is_valid(serializer, *args, **kwargs)
        both_requests_validated.wait(timeout=5)
        return result

    monkeypatch.setattr(UserPreferenceSerializer, "is_valid", synchronize_after_stale_read)

    payloads = [
        {
            "theme": "dark",
            "language": "en",
            "reduced_motion": False,
            "week_start": 1,
            "version": preference.version,
        },
        {
            "theme": "system",
            "language": "vi",
            "reduced_motion": True,
            "week_start": 1,
            "version": preference.version,
        },
    ]

    def update_preferences(payload):
        close_old_connections()
        try:
            request = APIRequestFactory().put("/api/v1/preferences/", payload, format="json")
            force_authenticate(request, user=user)
            response = UserPreferenceView.as_view()(request)
            return response.status_code, response.data
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(update_preferences, payloads))

    assert sorted(status_code for status_code, _ in responses) == [200, 409]
    conflict = next(data for status_code, data in responses if status_code == 409)
    winner = next(data for status_code, data in responses if status_code == 200)
    assert conflict == {"detail": "Preferences changed. Reload latest state and retry."}

    preference.refresh_from_db()
    assert preference.version == 2
    assert (preference.theme, preference.language, preference.reduced_motion) == (
        winner["theme"],
        winner["language"],
        winner["reduced_motion"],
    )
