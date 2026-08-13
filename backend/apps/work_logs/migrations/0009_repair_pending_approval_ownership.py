from django.db import migrations
from django.db.models import Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime


def flush_changes(Record, AuditEvent, records, events, fields):
    if not records:
        return
    Record.objects.bulk_update(records, fields, batch_size=500)
    AuditEvent.objects.bulk_create(events, batch_size=500)
    records.clear()
    events.clear()


def repair_pending_approval_ownership(apps, schema_editor):
    AuditEvent = apps.get_model("audit", "AuditEvent")
    Membership = apps.get_model("accounts", "CompanyMembership")
    Record = apps.get_model("work_logs", "WorkInOfficeRecord")

    event_cursor = 0
    while True:
        source_events = list(
            AuditEvent.objects.filter(
                event_type="work_logs.self_approval_migrated",
                target_type="work_logs.WorkInOfficeRecord",
                pk__gt=event_cursor,
            ).order_by("pk")[:500]
        )
        if not source_events:
            break
        event_cursor = source_events[-1].pk
        event_by_target = {
            int(event.target_id): event for event in source_events if str(event.target_id).isdigit()
        }
        target_ids = [str(target_id) for target_id in event_by_target]
        latest_event_pks = dict(
            AuditEvent.objects.filter(
                target_type="work_logs.WorkInOfficeRecord",
                target_id__in=target_ids,
            )
            .values("target_id")
            .annotate(latest_pk=Max("pk"))
            .values_list("target_id", "latest_pk")
        )
        records = {
            record.pk: record
            for record in Record.objects.filter(
                pk__in=event_by_target,
                review_state="approved",
                approval_method="self_approved",
            ).select_related("employee")
        }
        repaired = []
        reversal_events = []
        for record_id, event in event_by_target.items():
            record = records.get(record_id)
            if record is None:
                continue
            metadata = event.metadata or {}
            untouched_migration_output = (
                latest_event_pks.get(str(record.pk)) == event.pk
                and record.updated_at <= event.created_at
                and record.approved_by_snapshot.get("membership_id") == record.employee_id
                and metadata.get("membership_id") == record.employee_id
                and record.approval_owner_snapshot == {}
            )
            if not untouched_migration_output:
                continue
            original_state = metadata.get("original_state")
            previous = {
                "previous_approval_method": record.approval_method,
                "previous_approved_at": (
                    record.approved_at.isoformat() if record.approved_at else None
                ),
                "previous_approved_by_snapshot": record.approved_by_snapshot,
                "previous_approval_owner_snapshot": record.approval_owner_snapshot,
                "previous_version": record.version,
                "previous_updated_at": record.updated_at.isoformat(),
            }
            record.review_state = (
                original_state
                if original_state in {"pending", "pending_assignment"}
                else "pending_assignment"
            )
            record.approval_method = None
            record.approved_at = None
            record.approved_by_snapshot = {}
            record.approval_owner_snapshot = {}
            record.version += 1
            record.updated_at = timezone.now()
            repaired.append(record)
            reversal_events.append(
                AuditEvent(
                    event_type="work_logs.self_approval_migration_reverted",
                    target_type="work_logs.WorkInOfficeRecord",
                    target_id=str(record.pk),
                    metadata={
                        "original_state": original_state,
                        "work_date": record.work_date.isoformat(),
                        "actor_role": "system",
                        "actor_company_id": record.employee.company_id,
                        "revision": record.version,
                        "reason": "Current role cannot prove historical self-approval eligibility",
                        "from_state": "approved",
                        "to_state": record.review_state,
                        **previous,
                    },
                )
            )
        flush_changes(
            Record,
            AuditEvent,
            repaired,
            reversal_events,
            [
                "review_state",
                "approval_method",
                "approved_at",
                "approved_by_snapshot",
                "approval_owner_snapshot",
                "version",
                "updated_at",
            ],
        )

    record_cursor = 0
    while True:
        pending_records = list(
            Record.objects.filter(
                review_state="pending",
                pk__gt=record_cursor,
            )
            .select_related("employee")
            .order_by("pk")[:500]
        )
        if not pending_records:
            break
        record_cursor = pending_records[-1].pk
        target_ids = [str(record.pk) for record in pending_records]
        assignment_event_pks = (
            AuditEvent.objects.filter(
                event_type__in=(
                    "work_logs.record_pending_assignment_resolved",
                    "work_logs.record_pending_reassigned",
                ),
                target_type="work_logs.WorkInOfficeRecord",
                target_id__in=target_ids,
            )
            .values("target_id")
            .annotate(latest_pk=Max("pk"))
            .values_list("latest_pk", flat=True)
        )
        assignment_events = {
            event.target_id: event
            for event in AuditEvent.objects.filter(pk__in=assignment_event_pks)
        }
        explicit_owner_ids = {
            record.approval_owner_snapshot.get("membership_id")
            for record in pending_records
            if record.approval_owner_snapshot.get("assigned_by_membership_id")
            and record.approval_owner_snapshot.get("assigned_reason")
        }
        authorized_explicit_owners = dict(
            Membership.objects.filter(
                pk__in=explicit_owner_ids,
                is_active=True,
                user__is_active=True,
                role="manager",
            ).values_list("pk", "company_id")
        )
        changed = []
        audit_events = []
        for record in pending_records:
            owner_snapshot = record.approval_owner_snapshot
            owner_id = owner_snapshot.get("membership_id")
            assignment_event = assignment_events.get(str(record.pk))
            assignment_metadata = assignment_event.metadata if assignment_event else {}
            assignment_revision = assignment_metadata.get("revision")
            if (
                owner_snapshot.get("assigned_by_membership_id")
                and owner_snapshot.get("assigned_reason")
                and authorized_explicit_owners.get(owner_id) == record.employee.company_id
                and assignment_metadata.get("assigned_manager_membership_id") == owner_id
                and assignment_metadata.get("reason") == owner_snapshot.get("assigned_reason")
                and isinstance(assignment_revision, int)
                and assignment_revision <= record.version
            ):
                continue
            previous_state = record.review_state
            previous_version = record.version
            previous_updated_at = record.updated_at
            previous_owner_snapshot = record.approval_owner_snapshot
            desired_state = "pending_assignment"
            desired_owner_snapshot = {}
            event_type = "work_logs.pending_assignment_migrated"
            if (
                record.review_state == desired_state
                and record.approval_owner_snapshot == desired_owner_snapshot
            ):
                continue
            record.review_state = desired_state
            record.approval_owner_snapshot = desired_owner_snapshot
            record.version += 1
            record.updated_at = timezone.now()
            changed.append(record)
            audit_events.append(
                AuditEvent(
                    event_type=event_type,
                    target_type="work_logs.WorkInOfficeRecord",
                    target_id=str(record.pk),
                    metadata={
                        "work_date": record.work_date.isoformat(),
                        "actor_role": "system",
                        "actor_company_id": record.employee.company_id,
                        "revision": record.version,
                        "reason": (
                            "Repair deterministic approval ownership for legacy pending record"
                        ),
                        "from_state": previous_state,
                        "to_state": record.review_state,
                        "previous_approval_owner_snapshot": previous_owner_snapshot,
                        "previous_version": previous_version,
                        "previous_updated_at": previous_updated_at.isoformat(),
                    },
                )
            )
        flush_changes(
            Record,
            AuditEvent,
            changed,
            audit_events,
            ["review_state", "approval_owner_snapshot", "version", "updated_at"],
        )


def reverse_pending_approval_ownership(apps, schema_editor):
    AuditEvent = apps.get_model("audit", "AuditEvent")
    Record = apps.get_model("work_logs", "WorkInOfficeRecord")

    event_groups = [
        ["work_logs.pending_owner_migrated", "work_logs.pending_assignment_migrated"],
        ["work_logs.self_approval_migration_reverted"],
    ]
    for event_types in event_groups:
        records = []
        event_ids = []
        fields = ["review_state", "approval_owner_snapshot", "version", "updated_at"]
        if event_types == ["work_logs.self_approval_migration_reverted"]:
            fields.extend(["approval_method", "approved_at", "approved_by_snapshot"])
        events = AuditEvent.objects.filter(
            event_type__in=event_types,
            target_type="work_logs.WorkInOfficeRecord",
        ).order_by("-pk")
        for event in events.iterator():
            metadata = event.metadata
            record = Record.objects.filter(pk=event.target_id).first()
            if record is None:
                raise RuntimeError(
                    f"Cannot reverse WIO repair for missing record {event.target_id}."
                )
            if record.version != metadata.get("revision"):
                raise RuntimeError(
                    f"Cannot reverse WIO repair after record {event.target_id} changed."
                )
            record.review_state = metadata["from_state"]
            record.approval_owner_snapshot = metadata.get("previous_approval_owner_snapshot", {})
            record.version = metadata["previous_version"]
            record.updated_at = parse_datetime(metadata["previous_updated_at"])
            if event.event_type == "work_logs.self_approval_migration_reverted":
                record.approval_method = metadata["previous_approval_method"]
                record.approved_at = (
                    parse_datetime(metadata["previous_approved_at"])
                    if metadata["previous_approved_at"]
                    else None
                )
                record.approved_by_snapshot = metadata["previous_approved_by_snapshot"]
            records.append(record)
            event_ids.append(event.pk)
            if len(event_ids) >= 500:
                Record.objects.bulk_update(records, fields, batch_size=500)
                AuditEvent.objects.filter(pk__in=event_ids).delete()
                records.clear()
                event_ids.clear()
        if event_ids:
            Record.objects.bulk_update(records, fields, batch_size=500)
            AuditEvent.objects.filter(pk__in=event_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_manager_assignment_history_integrity"),
        ("work_logs", "0008_effective_base_location_history"),
    ]

    operations = [
        migrations.RunPython(
            repair_pending_approval_ownership,
            reverse_pending_approval_ownership,
        ),
    ]
