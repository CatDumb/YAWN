import logging
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import EmailOTPChallenge, OTPRequestRateLimit, User
from apps.accounts.serializers import (
    CurrentUserSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
)
from apps.audit.models import AuditEvent

logger = logging.getLogger("wio.auth")
GENERIC_OTP_MESSAGE = "If the account is eligible, a sign-in code has been sent."


def _client_fingerprint(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    remote_address = request.META.get("REMOTE_ADDR", "unknown")
    address = remote_address
    if settings.WIO_TRUST_PROXY_HEADERS and forwarded_for:
        address = forwarded_for.split(",", 1)[0].strip() or remote_address
    return salted_hmac("wio.otp.request", address).hexdigest()


def _eligible_user(email):
    return (
        User.objects.filter(
            email__iexact=email,
            is_active=True,
            memberships__is_active=True,
            memberships__company__is_active=True,
        )
        .distinct()
        .first()
    )


def _rate_limit_keys(email, fingerprint):
    return sorted(
        {
            salted_hmac("wio.otp.request.email", email).hexdigest(),
            salted_hmac("wio.otp.request.fingerprint", fingerprint).hexdigest(),
        }
    )


def _lock_rate_limits(email, fingerprint):
    for key in _rate_limit_keys(email, fingerprint):
        OTPRequestRateLimit.objects.get_or_create(key=key)
        OTPRequestRateLimit.objects.select_for_update().get(key=key)


class OTPRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=OTPRequestSerializer, responses={202: None})
    @transaction.atomic
    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        fingerprint = _client_fingerprint(request)
        _lock_rate_limits(email, fingerprint)
        now = timezone.now()
        hour_ago = now - timedelta(hours=1)

        latest = EmailOTPChallenge.objects.filter(email=email).order_by("-created_at").first()
        email_limited = (
            EmailOTPChallenge.objects.filter(email=email, created_at__gte=hour_ago).count()
            >= settings.WIO_OTP_REQUESTS_PER_HOUR
        )
        ip_limited = (
            EmailOTPChallenge.objects.filter(
                request_fingerprint=fingerprint,
                created_at__gte=hour_ago,
            ).count()
            >= settings.WIO_OTP_IP_REQUESTS_PER_HOUR
        )
        live_challenge = (
            latest is not None and latest.consumed_at is None and latest.expires_at > now
        )

        if live_challenge or email_limited or ip_limited:
            challenge_id = latest.pk if latest else uuid.uuid4()
            return Response(
                {"detail": GENERIC_OTP_MESSAGE, "challenge_id": challenge_id},
                status=status.HTTP_202_ACCEPTED,
            )

        user = _eligible_user(email)
        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge = EmailOTPChallenge.objects.create(
            user=user,
            email=email,
            code_hash=make_password(code),
            request_fingerprint=fingerprint,
            expires_at=now + timedelta(seconds=settings.WIO_OTP_TTL_SECONDS),
        )

        if user:
            expiry_minutes = max(1, settings.WIO_OTP_TTL_SECONDS // 60)
            sent = send_mail(
                subject="Your WIO Tracker sign-in code",
                message=(f"Your sign-in code is {code}. It expires in {expiry_minutes} minutes."),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
            if sent != 1:
                logger.error("otp_email_delivery_failed")

        return Response(
            {"detail": GENERIC_OTP_MESSAGE, "challenge_id": challenge.pk},
            status=status.HTTP_202_ACCEPTED,
        )


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CSRFTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: inline_serializer(
                name="CSRFTokenResponse",
                fields={"csrfToken": serializers.CharField()},
            )
        }
    )
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class OTPVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=OTPVerifySerializer, responses={200: CurrentUserSerializer})
    @transaction.atomic
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        now = timezone.now()

        challenge = (
            EmailOTPChallenge.objects.select_for_update()
            .filter(pk=data["challenge_id"], email=data["email"])
            .first()
        )
        if (
            challenge is None
            or challenge.consumed_at is not None
            or challenge.expires_at <= now
            or challenge.attempt_count >= settings.WIO_OTP_MAX_ATTEMPTS
        ):
            return Response(
                {"detail": "Invalid or expired code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        challenge.attempt_count += 1
        if not check_password(data["code"], challenge.code_hash) or challenge.user is None:
            if challenge.attempt_count >= settings.WIO_OTP_MAX_ATTEMPTS:
                challenge.consumed_at = now
            challenge.save(update_fields=["attempt_count", "consumed_at"])
            return Response(
                {"detail": "Invalid or expired code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        challenge.consumed_at = now
        challenge.save(update_fields=["attempt_count", "consumed_at"])
        login(request, challenge.user, backend="django.contrib.auth.backends.ModelBackend")
        AuditEvent.objects.create(actor=challenge.user, event_type="auth.otp_login_succeeded")
        logger.info("otp_login_succeeded", extra={"user_id": str(challenge.user_id)})
        return Response(CurrentUserSerializer(challenge.user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        actor = request.user
        logout(request)
        AuditEvent.objects.create(actor=actor, event_type="auth.logout")
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    @extend_schema(responses=CurrentUserSerializer)
    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)
