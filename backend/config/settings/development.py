from .base import *  # noqa: F403

DEBUG = True
EMAIL_BACKEND = env(  # noqa: F405
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] = [  # noqa: F405
    "rest_framework.permissions.AllowAny"
]
