from datetime import UTC, datetime
from pathlib import Path

from .test import *  # noqa: F403

# Keep artifacts in the path bootstrap and Playwright teardown can safely remove.
E2E_ARTIFACT_DIR = Path(BASE_DIR / ".e2e")  # noqa: F405
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": E2E_ARTIFACT_DIR / "db.sqlite3",
    }
}
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = E2E_ARTIFACT_DIR / "mail"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
CORS_ALLOWED_ORIGINS = ["http://127.0.0.1:3100"]
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:3100"]
WIO_APP_URL = "http://127.0.0.1:3100"
WIO_FIXED_NOW = datetime(2026, 7, 29, 12, tzinfo=UTC)
