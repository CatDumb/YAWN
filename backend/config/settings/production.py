from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import URLValidator, validate_email

from .base import *  # noqa: F403

DEBUG = False

if SECRET_KEY.startswith("django-insecure-"):  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a strong production value.")
if not env("DJANGO_ALLOWED_HOSTS", default=""):  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")

EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND", default="")  # noqa: F405
EMAIL_HOST = env("DJANGO_EMAIL_HOST", default="").strip()  # noqa: F405
_email_port = env("DJANGO_EMAIL_PORT", default="").strip()  # noqa: F405
EMAIL_HOST_USER = env("DJANGO_EMAIL_HOST_USER", default="").strip()  # noqa: F405
EMAIL_HOST_PASSWORD = env("DJANGO_EMAIL_HOST_PASSWORD", default="")  # noqa: F405
_email_use_tls = env("DJANGO_EMAIL_USE_TLS", default="").strip().lower()  # noqa: F405
DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", default="").strip()  # noqa: F405
DJANGO_EMAIL_TIMEOUT_SECONDS = env.int("DJANGO_EMAIL_TIMEOUT_SECONDS", default=10)  # noqa: F405
EMAIL_TIMEOUT = DJANGO_EMAIL_TIMEOUT_SECONDS
WIO_APP_URL = env("WIO_APP_URL", default="").strip()  # noqa: F405

try:
    EMAIL_PORT = int(_email_port)
except ValueError:
    EMAIL_PORT = 0
EMAIL_USE_TLS = _email_use_tls == "true"


def _validate_production_email_and_app_url():
    if EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        raise ImproperlyConfigured("Production requires Django SMTP email backend.")
    try:
        smtp_url = urlparse(f"smtp://{EMAIL_HOST}")
        URLValidator(schemes=["smtp"])(smtp_url.geturl())
        smtp_port = smtp_url.port
    except (ValidationError, ValueError) as exc:
        raise ImproperlyConfigured("Production requires a valid SMTP host.") from exc
    if (
        smtp_url.hostname != EMAIL_HOST.lower()
        or smtp_port is not None
        or smtp_url.username
        or smtp_url.password
        or smtp_url.path
        or smtp_url.params
        or smtp_url.query
        or smtp_url.fragment
    ):
        raise ImproperlyConfigured("Production requires a bare SMTP host without a port or path.")
    if not 1 <= EMAIL_PORT <= 65535:
        raise ImproperlyConfigured("Production requires a valid SMTP port.")
    if not 1 <= EMAIL_TIMEOUT <= 30:
        raise ImproperlyConfigured(
            "DJANGO_EMAIL_TIMEOUT_SECONDS must be between 1 and 30 in production."
        )
    if not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD or not EMAIL_USE_TLS:
        raise ImproperlyConfigured("Production requires SMTP username, password, and TLS.")
    if DEFAULT_FROM_EMAIL != EMAIL_HOST_USER:
        raise ImproperlyConfigured("DJANGO_DEFAULT_FROM_EMAIL must match DJANGO_EMAIL_HOST_USER.")
    try:
        validate_email(DEFAULT_FROM_EMAIL)
    except ValidationError as exc:
        raise ImproperlyConfigured(
            "DJANGO_DEFAULT_FROM_EMAIL must be a valid email address."
        ) from exc

    try:
        URLValidator(schemes=["https"])(WIO_APP_URL)
    except ValidationError as exc:
        raise ImproperlyConfigured("WIO_APP_URL must be an HTTPS frontend homepage URL.") from exc

    parsed_url = urlparse(WIO_APP_URL)
    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
        or parsed_url.path not in {"", "/"}
        or parsed_url.params
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ImproperlyConfigured("WIO_APP_URL must be an HTTPS frontend homepage URL.")
    try:
        _ = parsed_url.port
    except ValueError as exc:
        raise ImproperlyConfigured("WIO_APP_URL must use a valid HTTPS port.") from exc


_validate_production_email_and_app_url()

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
