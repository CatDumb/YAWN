import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction

from apps.accounts.models import CompanyMembership, User, UserPreference
from apps.work_logs.models import FiscalPeriod, WorkInOfficeRecord
from apps.work_logs.services import (
    audit_record,
    current_time,
    lock_wio_period,
    reject_record,
)

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


def send_rejection_email(record):
    preference = UserPreference.objects.filter(user=record.employee.user).first()
    language = preference.language if preference else UserPreference.Language.ENGLISH
    copy = REJECTION_EMAIL.get(language, REJECTION_EMAIL[UserPreference.Language.ENGLISH])
    url = f"{settings.WIO_APP_URL}/work-in-office/{record.pk}"
    try:
        send_mail(
            subject=copy["subject"],
            message=copy["message"].format(date=record.work_date.isoformat(), url=url),
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


def role_membership(user, role, label):
    memberships = list(
        CompanyMembership.objects.filter(
            user=user,
            user__is_active=True,
            is_active=True,
            company__is_active=True,
        )
        .select_related("company")
        .order_by("pk")[:2]
    )
    if not memberships:
        raise ValidationError(f"An active {label} membership is required.")
    if len(memberships) != 1:
        raise ValidationError(f"Active {label} membership scope is ambiguous.")
    membership = memberships[0]
    if membership.role != role:
        raise ValidationError(f"An active {label} membership is required.")
    return membership


def scoped_pending(manager):
    return WorkInOfficeRecord.objects.filter(
        employee__company=manager.company,
        review_state=WorkInOfficeRecord.ReviewState.PENDING,
        approval_owner_snapshot__membership_id=manager.pk,
    )


def _locked_actor_scope(*, membership, role, label):
    User.objects.select_for_update().get(pk=membership.user_id)
    memberships = list(
        CompanyMembership.objects.select_for_update()
        .filter(
            user_id=membership.user_id,
            user__is_active=True,
            is_active=True,
            company__is_active=True,
        )
        .select_related("company", "user")
        .order_by("pk")[:2]
    )
    if (
        len(memberships) != 1
        or memberships[0].pk != membership.pk
        or memberships[0].company_id != membership.company_id
        or memberships[0].role != role
    ):
        raise ValidationError(f"An active {label} membership is required.")
    return memberships[0]


def _locked_scoped_record(*, manager, record_id):
    identity = scoped_pending(manager).select_related("employee").filter(pk=record_id).first()
    if identity is None:
        raise ValidationError("Claim is unavailable or outside your assignment scope.")
    period = lock_wio_period(
        company_id=identity.employee.company_id,
        work_date=identity.work_date,
    )
    manager = _locked_actor_scope(
        membership=manager,
        role=CompanyMembership.Role.MANAGER,
        label="manager",
    )
    record = scoped_pending(manager).select_for_update().filter(pk=record_id).first()
    if record is None:
        raise ValidationError("Claim is unavailable or outside your assignment scope.")
    return record, period, manager


@transaction.atomic
def approve_record(*, manager, record_id, version):
    record, _, manager = _locked_scoped_record(manager=manager, record_id=record_id)
    if version is None or record.version != version:
        raise RuntimeError("stale")
    record.review_state = WorkInOfficeRecord.ReviewState.APPROVED
    record.approved_at = current_time()
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
    record, period, manager = _locked_scoped_record(manager=manager, record_id=record_id)
    if version is None or record.version != version:
        raise RuntimeError("stale")
    result = reject_record(
        record=record,
        actor=manager.user,
        reason=reason.strip(),
        period=period,
    )
    send_rejection_email(result)
    return result


@transaction.atomic
def undo_approval(*, manager, record_id, version):
    identity = (
        WorkInOfficeRecord.objects.select_related("employee")
        .filter(
            pk=record_id,
            employee__company=manager.company,
            approved_by_snapshot__membership_id=manager.pk,
            review_state=WorkInOfficeRecord.ReviewState.APPROVED,
            approval_method=WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED,
        )
        .first()
    )
    if identity is None:
        raise ValidationError("Approval is unavailable for undo.")
    lock_wio_period(
        company_id=identity.employee.company_id,
        work_date=identity.work_date,
    )
    manager = _locked_actor_scope(
        membership=manager,
        role=CompanyMembership.Role.MANAGER,
        label="manager",
    )
    record = WorkInOfficeRecord.objects.select_for_update().filter(pk=record_id).first()
    if (
        record is None
        or record.employee.company_id != manager.company_id
        or record.approved_by_snapshot.get("membership_id") != manager.pk
        or record.review_state != WorkInOfficeRecord.ReviewState.APPROVED
        or record.approval_method != WorkInOfficeRecord.ApprovalMethod.MANAGER_APPROVED
    ):
        raise ValidationError("Approval is unavailable for undo.")
    if version is None or record.version != version:
        raise RuntimeError("stale")
    if record.approved_at is None or current_time() > record.approved_at + timedelta(seconds=10):
        raise ValidationError("The 10-second undo window has expired.")
    record.review_state = WorkInOfficeRecord.ReviewState.PENDING
    record.approved_at = None
    record.approved_by_snapshot = {}
    record.approval_method = None
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
    audit_record(actor=manager.user, event_type="work_logs.approval_undone", record=record)
    return record


@transaction.atomic
def assign_pending_record(*, hr, record_id, manager_id, version, reason):
    if not reason or not reason.strip():
        raise ValidationError("An assignment reason is required.")
    identity = (
        WorkInOfficeRecord.objects.select_related("employee")
        .filter(
            pk=record_id,
            employee__company=hr.company,
            review_state__in=(
                WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
                WorkInOfficeRecord.ReviewState.PENDING,
            ),
        )
        .first()
    )
    if identity is None:
        raise ValidationError("Claim is unavailable for assignment.")
    lock_wio_period(
        company_id=identity.employee.company_id,
        work_date=identity.work_date,
    )
    hr = _locked_actor_scope(
        membership=hr,
        role=CompanyMembership.Role.HR_ADMIN,
        label="HR/admin",
    )
    record = (
        WorkInOfficeRecord.objects.select_for_update()
        .filter(
            pk=record_id,
            employee__company=hr.company,
            review_state__in=(
                WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
                WorkInOfficeRecord.ReviewState.PENDING,
            ),
        )
        .first()
    )
    if record is None:
        raise ValidationError("Claim is unavailable for assignment.")
    if version is None or record.version != version:
        raise RuntimeError("stale")
    manager_identity = (
        CompanyMembership.objects.filter(pk=manager_id).values("user_id", "company_id").first()
    )
    manager = None
    if manager_identity and manager_identity["company_id"] == hr.company_id:
        User.objects.select_for_update().get(pk=manager_identity["user_id"])
        manager = (
            CompanyMembership.objects.select_for_update()
            .filter(
                pk=manager_id,
                company_id=hr.company_id,
                is_active=True,
                user__is_active=True,
                role=CompanyMembership.Role.MANAGER,
            )
            .first()
        )
    if manager is None:
        raise ValidationError("Choose an active manager in the same company.")
    previous_state = record.review_state
    previous_manager_id = record.approval_owner_snapshot.get("membership_id")
    if (
        previous_state == WorkInOfficeRecord.ReviewState.PENDING
        and previous_manager_id == manager.pk
    ):
        raise ValidationError("Choose a different manager for reassignment.")
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
        event_type=(
            "work_logs.record_pending_reassigned"
            if previous_state == WorkInOfficeRecord.ReviewState.PENDING
            else "work_logs.record_pending_assignment_resolved"
        ),
        record=record,
        reason=reason.strip(),
        from_state=previous_state,
        to_state=record.review_state,
        previous_manager_membership_id=previous_manager_id,
        assigned_manager_membership_id=manager.pk,
    )
    return record


@transaction.atomic
def expire_pending_for_period(period):
    period = FiscalPeriod.objects.select_for_update().get(pk=period.pk)
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
