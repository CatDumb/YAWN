import logging
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, transaction
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

from apps.accounts.models import AccessRequest, Company, EmailOTPChallenge, User, UserPreference
from apps.accounts.serializers import (
    AccessRequestResponseSerializer,
    AccessRequestSerializer,
    CurrentUserSerializer,
    OTPRequestResponseSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    UserPreferenceSerializer,
)
from apps.accounts.services import schedule_otp_email_delivery
from apps.audit.models import AuditEvent

logger = logging.getLogger("wio.auth")
GENERIC_OTP_MESSAGE = "If the account is eligible, a sign-in code has been sent."
GENERIC_SIGNUP_MESSAGE = "If access can be requested, it is pending review."


def _client_fingerprint(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    remote_address = request.META.get("REMOTE_ADDR", "unknown")
    address = remote_address
    if settings.WIO_TRUST_PROXY_HEADERS and forwarded_for:
        address = forwarded_for.split(",", 1)[0].strip() or remote_address
    return salted_hmac("wio.otp.request", address).hexdigest()


def _signup_fingerprint(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    remote_address = request.META.get("REMOTE_ADDR", "unknown")
    address = remote_address
    if settings.WIO_TRUST_PROXY_HEADERS and forwarded_for:
        address = forwarded_for.split(",", 1)[0].strip() or remote_address
    return salted_hmac("wio.signup.request", address, algorithm="sha256").hexdigest()


def _eligible_user(email):
    user = (
        User.objects.filter(
            email__iexact=email,
            is_active=True,
            memberships__is_active=True,
            memberships__company__is_active=True,
        )
        .distinct()
        .first()
    )
    if user is None:
        return None
    active_scope_count = user.memberships.filter(
        is_active=True,
        company__is_active=True,
    ).count()
    return user if active_scope_count == 1 else None


def _lock_rate_limits(email, fingerprint):
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        for key in sorted(
            {
                salted_hmac("wio.otp.request.email", email).hexdigest(),
                salted_hmac("wio.otp.request.fingerprint", fingerprint).hexdigest(),
            }
        ):
            lock_id = int(key[:16], 16)
            if lock_id >= 2**63:
                lock_id -= 2**64
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])


class AccessRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=AccessRequestSerializer,
        responses={202: AccessRequestResponseSerializer},
    )
    @transaction.atomic
    def post(self, request):
        serializer = AccessRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        company = Company.objects.filter(
            slug=settings.WIO_SIGNUP_COMPANY_SLUG,
            is_active=True,
        ).first()
        if company is None:
            return Response(
                {"detail": GENERIC_SIGNUP_MESSAGE},
                status=status.HTTP_202_ACCEPTED,
            )

        email = data["email"]
        fingerprint = _signup_fingerprint(request)
        _lock_rate_limits(email, fingerprint)
        hour_ago = timezone.now() - timedelta(hours=1)
        email_limited = (
            AccessRequest.objects.filter(
                company=company,
                email=email,
                created_at__gte=hour_ago,
            ).count()
            >= settings.WIO_SIGNUP_REQUESTS_PER_HOUR
        )
        fingerprint_limited = (
            AccessRequest.objects.filter(
                company=company,
                request_fingerprint=fingerprint,
                created_at__gte=hour_ago,
            ).count()
            >= settings.WIO_SIGNUP_FINGERPRINT_REQUESTS_PER_HOUR
        )
        if not email_limited and not fingerprint_limited:
            AccessRequest.objects.get_or_create(
                company=company,
                email=email,
                status=AccessRequest.Status.PENDING,
                defaults={
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "request_fingerprint": fingerprint,
                },
            )

        return Response(
            {"detail": GENERIC_SIGNUP_MESSAGE},
            status=status.HTTP_202_ACCEPTED,
        )


class OTPRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=OTPRequestSerializer, responses={202: OTPRequestResponseSerializer})
    @transaction.atomic
    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        fingerprint = _client_fingerprint(request)
        _lock_rate_limits(email, fingerprint)
        now = timezone.now()
        hour_ago = now - timedelta(hours=1)
        resend_after = now - timedelta(seconds=settings.WIO_OTP_RESEND_SECONDS)

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
        cooling_down = (
            settings.WIO_OTP_RESEND_SECONDS > 0
            and latest is not None
            and latest.consumed_at is None
            and latest.expires_at > now
            and latest.created_at >= resend_after
        )

        if cooling_down or email_limited or ip_limited:
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
            schedule_otp_email_delivery(recipient=user.email, code=code)

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
        eligible_user = _eligible_user(challenge.email)
        if (
            not check_password(data["code"], challenge.code_hash)
            or challenge.user is None
            or eligible_user is None
            or eligible_user.pk != challenge.user_id
        ):
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
    @extend_schema(
        responses={
            200: CurrentUserSerializer,
            409: inline_serializer(
                name="AmbiguousCompanyScopeError",
                fields={"detail": serializers.CharField()},
            ),
        }
    )
    def get(self, request):
        active_scope_count = request.user.memberships.filter(
            is_active=True,
            company__is_active=True,
        ).count()
        if active_scope_count != 1:
            return Response(
                {
                    "detail": (
                        "Active company scope is missing or ambiguous. "
                        "Contact HR/admin to repair membership."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(CurrentUserSerializer(request.user).data)


class UserPreferenceView(APIView):
    @extend_schema(responses=UserPreferenceSerializer)
    def get(self, request):
        preference, _ = UserPreference.objects.get_or_create(user=request.user)
        return Response(UserPreferenceSerializer(preference).data)

    @extend_schema(request=UserPreferenceSerializer, responses=UserPreferenceSerializer)
    def put(self, request):
        preference, _ = UserPreference.objects.get_or_create(user=request.user)
        submitted_version = request.data.get("version")
        if submitted_version is None:
            return Response(
                {"detail": "Version is required for preferences."},
                status=status.HTTP_409_CONFLICT,
            )
        if submitted_version != preference.version:
            return Response(
                {"detail": "Preferences changed. Reload latest state and retry."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = UserPreferenceSerializer(preference, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = UserPreference.objects.filter(
            pk=preference.pk,
            version=submitted_version,
        ).update(
            **serializer.validated_data,
            version=submitted_version + 1,
            updated_at=timezone.now(),
        )
        if updated == 0:
            return Response(
                {"detail": "Preferences changed. Reload latest state and retry."},
                status=status.HTTP_409_CONFLICT,
            )
        preference.refresh_from_db()
        return Response(UserPreferenceSerializer(preference).data)
