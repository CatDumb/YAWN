import logging
import math

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

logger = logging.getLogger("wio.auth")


def send_otp_email(*, recipient: str, code: str) -> None:
    """Send one OTP email without exposing delivery details in logs."""
    expiry_minutes = max(1, math.ceil(settings.WIO_OTP_TTL_SECONDS / 60))
    try:
        sent = send_mail(
            subject="Your YAWN sign-in code",
            message=(f"Your YAWN sign-in code is {code}. It expires in {expiry_minutes} minutes."),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:  # Email backends raise provider-specific exceptions.
        logger.error("otp_email_delivery_failed")
        return

    if sent != 1:
        logger.error("otp_email_delivery_failed")


def schedule_otp_email_delivery(*, recipient: str, code: str) -> None:
    """Schedule OTP delivery only after its challenge transaction commits."""
    transaction.on_commit(lambda: send_otp_email(recipient=recipient, code=code))


def send_approval_email(*, recipient: str) -> None:
    """Send a post-approval notification without leaking delivery details to logs."""
    # TODO: Add branded HTML approval email in a future release.
    try:
        sent = send_mail(
            subject="Your YAWN access has been approved",
            message=(
                "Your YAWN access request has been approved.\n\n"
                f"Open {settings.WIO_APP_URL} and choose Already approved? Sign in "
                "to request your sign-in code."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:  # Email backends raise provider-specific exceptions.
        logger.error("approval_email_delivery_failed")
        return

    if sent != 1:
        logger.error("approval_email_delivery_failed")


def schedule_approval_email_delivery(*, recipient: str) -> None:
    """Schedule approval notification only after the approval transaction commits."""
    transaction.on_commit(lambda: send_approval_email(recipient=recipient))
