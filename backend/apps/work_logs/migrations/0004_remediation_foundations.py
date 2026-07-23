from datetime import datetime, time

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def migrate_cutoffs(apps, schema_editor):
    FiscalPeriod = apps.get_model("work_logs", "FiscalPeriod")
    for period in FiscalPeriod.objects.exclude(reconciliation_cutoff__isnull=True):
        value = period.reconciliation_cutoff
        if not isinstance(value, datetime):
            value = datetime.combine(value, time.max)
        if timezone.is_naive(value):
            value = timezone.make_aware(value)
        FiscalPeriod.objects.filter(pk=period.pk).update(reconciliation_cutoff=value)


class Migration(migrations.Migration):
    dependencies = [("work_logs", "0003_workinofficerecord_correction_deadline_and_rejected_at")]

    operations = [
        migrations.AlterField(
            model_name="fiscalperiod",
            name="reconciliation_cutoff",
            field=models.DateTimeField(blank=True),
        ),
        migrations.RunPython(migrate_cutoffs, migrations.RunPython.noop),
        migrations.AddField(
            model_name="workinofficerecord",
            name="approval_owner_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="workinofficerecord",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workinofficerecord",
            name="approved_by_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="workinofficerecord",
            name="review_state",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("pending", "Pending"),
                    ("pending_assignment", "Pending assignment"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("not_required", "Not required"),
                    ("expired_pending", "Expired pending"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="FiscalFinalizationStep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=80)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("effect_token", models.UUIDField(blank=True, null=True, unique=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="finalization_steps", to="work_logs.fiscalperiod")),
            ],
        ),
        migrations.CreateModel(
            name="FinalizedLedgerRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("revision", models.PositiveIntegerField(default=1)),
                ("summary", models.JSONField(default=dict)),
                ("ledger", models.JSONField(default=list)),
                ("input_versions", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ledger_revisions", to="accounts.companymembership")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ledger_revisions", to="work_logs.fiscalperiod")),
                ("predecessor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="successors", to="work_logs.finalizedledgerrevision")),
            ],
        ),
        migrations.CreateModel(
            name="WorkIntentionSeries",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("location", models.CharField(choices=[("office", "Office"), ("home", "Home")], max_length=12)),
                ("commitment", models.CharField(choices=[("firm", "Firm"), ("flexible", "Flexible")], max_length=12)),
                ("weekdays", models.JSONField(blank=True, default=list)),
                ("starts_on", models.DateField()),
                ("ends_on", models.DateField()),
                ("note", models.CharField(blank=True, max_length=300)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="intention_series", to="accounts.companymembership")),
            ],
        ),
        migrations.CreateModel(
            name="WorkIntentionOccurrence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("location", models.CharField(choices=[("office", "Office"), ("home", "Home")], max_length=12)),
                ("commitment", models.CharField(choices=[("firm", "Firm"), ("flexible", "Flexible")], max_length=12)),
                ("note", models.CharField(blank=True, max_length=300)),
                ("excluded_reason", models.CharField(blank=True, max_length=240)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="intentions", to="accounts.companymembership")),
                ("series", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="occurrences", to="work_logs.workintentionseries")),
            ],
        ),
        migrations.AddConstraint(
            model_name="fiscalfinalizationstep",
            constraint=models.UniqueConstraint(fields=("period", "key"), name="work_logs_finalization_step_unique"),
        ),
        migrations.AddConstraint(
            model_name="finalizedledgerrevision",
            constraint=models.UniqueConstraint(fields=("period", "employee", "revision"), name="work_logs_ledger_revision_unique"),
        ),
        migrations.AddConstraint(
            model_name="workintentionoccurrence",
            constraint=models.UniqueConstraint(fields=("employee", "date"), name="work_logs_one_intention_per_employee_day"),
        ),
    ]
