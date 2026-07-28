from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def backfill_approval_methods(apps, schema_editor):
    Membership = apps.get_model("accounts", "CompanyMembership")
    AuditEvent = apps.get_model("audit", "AuditEvent")
    Record = apps.get_model("work_logs", "WorkInOfficeRecord")

    Record.objects.filter(review_state="approved").update(approval_method="manager_approved")
    privileged_ids = Membership.objects.filter(role__in=["manager", "hr_admin"]).values_list(
        "pk", flat=True
    )
    records = Record.objects.filter(
        employee_id__in=privileged_ids,
        location_choice="in_office",
        review_state__in=["pending", "pending_assignment"],
    ).select_related("employee", "employee__user")
    audit_events = []
    for record in records.iterator():
        original_state = record.review_state
        record.review_state = "approved"
        record.approval_method = "self_approved"
        record.approved_at = record.submitted_at or record.created_at or timezone.now()
        record.approved_by_snapshot = {
            "membership_id": record.employee_id,
            "role": record.employee.role,
        }
        record.approval_owner_snapshot = {}
        record.version += 1
        record.save(
            update_fields=[
                "review_state",
                "approval_method",
                "approved_at",
                "approved_by_snapshot",
                "approval_owner_snapshot",
                "version",
                "updated_at",
            ]
        )
        audit_events.append(
            AuditEvent(
                actor_id=record.employee.user_id,
                event_type="work_logs.self_approval_migrated",
                target_type="work_logs.WorkInOfficeRecord",
                target_id=str(record.pk),
                metadata={
                    "original_state": original_state,
                    "reason": "privileged self-approval migration",
                    "membership_id": record.employee_id,
                },
            )
        )
    AuditEvent.objects.bulk_create(audit_events, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("work_logs", "0005_wiotransitionbaseline")]

    operations = [
        migrations.AddField(
            model_name="workinofficerecord",
            name="approval_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("manager_approved", "Manager approved"),
                    ("self_approved", "Self approved"),
                ],
                max_length=24,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_approval_methods, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="workinofficerecord",
            constraint=models.CheckConstraint(
                condition=(
                    Q(review_state="approved", approval_method__isnull=False)
                    | (~Q(review_state="approved") & Q(approval_method__isnull=True))
                ),
                name="work_logs_approval_method_matches_state",
            ),
        ),
    ]
