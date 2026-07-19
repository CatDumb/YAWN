from unittest.mock import patch

import pytest
from django.db import DatabaseError


def test_health_is_live(client):
    response = client.get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


@pytest.mark.django_db
def test_readiness_checks_database(client):
    response = client.get("/ready/")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_reports_database_failure(client):
    with patch("config.views.connection.cursor", side_effect=DatabaseError):
        response = client.get("/ready/")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
