import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import CompanyMembership, UserPreference
from apps.work_logs.models import WorkInOfficeRecord
from apps.work_logs.services import audit_record, reject_record

logger = logging.getLogger("wio.approvals")


class RejectionEmailDeliveryError(Exception):
    """Raised when rejection notification cannot be delivered."""


REJECTION_EMAIL = {
    UserPreference.Language.ENGLISH: {
        "subject": "Your work-in-office record needs correction",
        "message": ("Your {date} work-in-office record is Rejected. Open {url} to correct it."),
    },
    UserPreference.Language.VIETNAMESE: {
        "subject": "Bản ghi làm việc tại văn phòng cần sửa",
        "message": (
            "Bản ghi làm việc tại văn phòng ngày {date} của bạn bị từ chối. Mở {url} để sửa."
        ),
    },
}


def employee_language(user):
    preference = UserPreference.objects.filter(user=user).first()
    return preference.language if preference else UserPreference.Language.ENGLISH


def rejection_email_content(record):
    language = employee_language(record.employee.user)
    copy = REJECTION_EMAIL.get(language, REJECTION_EMAIL[UserPreference.Language.ENGLISH])
    url = f"{settings.WIO_APP_URL}/work-in-office/{record.pk}"
    return {
        "subject": copy["subject"],
        "message": copy["message"].format(date=record.work_date.isoformat(), url=url),
    }


def send_rejection_email(record):
    email = rejection_email_content(record)
    try:
        send_mail(
            subject=email["subject"],
            message=email["message"],
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[record.employee.user.email],
            fail_silently=False,
        )
    except Exception as error:
        logger.error(
            "approval_rejection_email_failed",
            extra={"error_class": type(error).__name__},
        )
        raise RejectionEmailDeliveryError from error


def manager_membership(user):
    membership = (
        CompanyMembership.objects.filter(
            user=user,
            is_active=True,
            company__is_active=True,
            role__in=[CompanyMembership.Role.MANAGER, CompanyMembership.Role.HR_ADMIN],
        )
        .select_related("company")
        .first()
    )
    if membership is None:
        raise ValidationError("An active manager membership is required.")
    return membership


def hr_membership(user):
    membership = CompanyMembership.objects.filter(
        user=user,
        is_active=True,
        company__is_active=True,
        role=CompanyMembership.Role.HR_ADMIN,
    ).first()
    if membership is None:
        raise ValidationError("An active HR/admin membership is required.")
    return membership


def scoped_pending(manager):
    return WorkInOfficeRecord.objects.filter(
        employee__company=manager.company,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot__membership_id=manager.pk,
    )


def _locked_scoped_record(*, manager, record_id):
    record = scoped_pending(manager).select_for_update().filter(pk=record_id).first()
    if record is None:
        raise ValidationError("Claim is unavailable or outside your assignment scope.")
    return record


@transaction.atomic
def approve_record(*, manager, record_id, version):
    record = _locked_scoped_record(manager=manager, record_id=record_id)
    if version is None or record.version != version:
        raise RuntimeError("stale")
    record.review_state = WorkInOfficeRecord.ReviewState.APPROVED
    record.approved_at = timezone.now()
    record.approved_by_snapshot = {"membership_id": manager.pk, "role": manager.role}
    record.approval_method = WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED
    record.version += 1
    record.save(
        update_fields=[
            "review_state",
            "approved_at",
            "approved_by_snapshot",
            "approval_method",
            "version",
            "updated_at",
        ]
    )
    audit_record(actor=manager.user, event_type="work_logs.record_approved", record=record)
    return record


@transaction.atomic
def reject_scoped_record(*, manager, record_id, version, reason):
    if not reason or not reason.strip():
        raise ValidationError("A rejection reason is required.")
    record = _locked_scoped_record(manager=manager, record_id=record_id)
    if version is None or record.version != version:
        raise RuntimeError("stale")
    result = reject_record(record=record, actor=manager.user, reason=reason.strip())
    send_rejection_email(result)
    return result


@transaction.atomic
def undo_approval(*, manager, record_id, version):
    record = WorkInOfficeRecord.objects.select_for_update().filter(pk=record_id).first()
    if (
        record is None
        or record.employee.company_id != manager.company_id
        or record.approved_by_snapshot.get("membership_id") != manager.pk
        or record.review_state != WorkInOfficeRecord.ReviewState.APPROVED
        or record.approval_method
        != WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED
    ):
        raise ValidationError("Approval is unavailable for undo.")
    if version is None or record.version != version:
        raise RuntimeError("stale")
    if record.approved_at is None or timezone.now() > record.approved_at + timedelta(seconds=10):
        raise ValidationError("The 10-second undo window has expired.")
    record.review_state = WorkInOfficeRecord.ReviewState.PENDING
    record.approved_at = None
    record.approval_method = None
    record.version += 1
    record.save(
        update_fields=["review_state", "approved_at", "approval_method", "version", "updated_at"]
    )
    audit_record(actor=manager.user, event_type="work_logs.approval_undone", record=record)
    return record


@transaction.atomic
def assign_pending_record(*, hr, record_id, manager_id, version, reason):
    if not reason or not reason.strip():
        raise ValidationError("An assignment reason is required.")
    record = (
        WorkInOfficeRecord.objects.select_for_update()
        .filter(
            pk=record_id,
            employee__company=hr.company,
            review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
        )
        .first()
    )
    if record is None:
        raise ValidationError("Claim is unavailable for assignment.")
    if version is None or record.version != version:
        raise RuntimeError("stale")
    manager = CompanyMembership.objects.filter(
        pk=manager_id,
        company=hr.company,
        is_active=True,
        role__in=[CompanyMembership.Role.MANAGER, CompanyMembership.Role.HR_ADMIN],
    ).first()
    if manager is None:
        raise ValidationError("Choose an active manager in the same company.")
    record.review_state = WorkInOfficeRecord.ReviewState.PENDING
    record.approval_owner_snapshot = {
        "membership_id": manager.pk,
        "assigned_by_membership_id": hr.pk,
        "assigned_reason": reason.strip(),
    }
    record.version += 1
    record.save(update_fields=["review_state", "approval_owner_snapshot", "version", "updated_at"])
    audit_record(
        actor=hr.user,
        event_type="work_logs.record_pending_assignment_resolved",
        record=record,
        reason=reason.strip(),
        assigned_manager_membership_id=manager.pk,
    )
    return record


@transaction.atomic
def expire_pending_for_period(period):
    records = list(
        WorkInOfficeRecord.objects.select_for_update().filter(
            employee__company=period.company,
            work_date__range=(period.start_date, period.end_date),
            review_state__in=[
                WorkInOfficeRecord.ReviewState.PENDING,
                WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
            ],
        )
    )
    for record in records:
        record.review_state = WorkInOfficeRecord.ReviewState.EXPIRED_PENDING
        record.version += 1
        record.save(update_fields=["review_state", "version", "updated_at"])
        audit_record(actor=None, event_type="work_logs.record_expired_pending", record=record)
    return len(records)
