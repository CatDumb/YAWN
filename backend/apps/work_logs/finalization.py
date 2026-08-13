"""Shared, retry-safe fiscal finalization coordinator."""

import logging
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Company
from apps.audit.models import AuditEvent
from apps.work_logs.approvals import expire_pending_for_period
from apps.work_logs.models import FiscalFinalizationStep, FiscalPeriod
from apps.work_logs.planner import purge_intentions_for_period
from apps.work_logs.reports import freeze_period_ledgers

logger = logging.getLogger("wio.finalization")


def _step_current(period: FiscalPeriod, checkpoint: FiscalFinalizationStep) -> bool:
    if checkpoint.completed_at is None:
        return False
    return period.reopened_at is None or checkpoint.completed_at >= period.reopened_at


@transaction.atomic
def run_finalization(period_id: int):
    company_id = FiscalPeriod.objects.values_list("company_id", flat=True).get(pk=period_id)
    Company.objects.select_for_update().get(pk=company_id)
    period = FiscalPeriod.objects.select_for_update().get(pk=period_id)
    if period.company_id != company_id:
        raise RuntimeError("Fiscal period changed while acquiring its company lock.")
    if period.state == FiscalPeriod.State.FINAL:
        return period
    if timezone.now() < period.reconciliation_cutoff:
        raise ValidationError("Fiscal period cutoff has not passed.")
    steps = (
        (
            "expire_unresolved_claims",
            lambda current_period: {"expired_claims": expire_pending_for_period(current_period)},
        ),
        ("freeze_ledgers", freeze_period_ledgers),
        ("purge_private_intentions", purge_intentions_for_period),
    )
    for key, effect in steps:
        checkpoint, _ = FiscalFinalizationStep.objects.select_for_update().get_or_create(
            period=period, key=key
        )
        if _step_current(period, checkpoint):
            continue
        try:
            metadata = effect(period) or {}
        except Exception as error:
            logger.error(
                "finalization_step_failed",
                extra={
                    "period_id": str(period.pk),
                    "step": key,
                    "error_class": error.__class__.__name__,
                },
            )
            raise
        checkpoint.effect_token = uuid4()
        checkpoint.completed_at = timezone.now()
        checkpoint.metadata = metadata
        checkpoint.save(update_fields=["effect_token", "completed_at", "metadata"])
        AuditEvent.objects.create(
            event_type="work_logs.finalization_step_completed",
            target_type="work_logs.FiscalPeriod",
            target_id=str(period.pk),
            metadata={"step": key, "effect_token": str(checkpoint.effect_token)},
        )
    if any(not _step_current(period, checkpoint) for checkpoint in period.finalization_steps.all()):
        raise ValidationError("Fixed expire/freeze/purge checkpoints are incomplete.")
    if set(period.finalization_steps.values_list("key", flat=True)) != {key for key, _ in steps}:
        raise ValidationError(
            "Fixed expire/freeze/purge checkpoint sequence changed during execution."
        )
    period.state = FiscalPeriod.State.FINAL
    period.save(update_fields=["state", "updated_at"])
    AuditEvent.objects.create(
        event_type="work_logs.period_finalized",
        target_type="work_logs.FiscalPeriod",
        target_id=str(period.pk),
    )
    return period
