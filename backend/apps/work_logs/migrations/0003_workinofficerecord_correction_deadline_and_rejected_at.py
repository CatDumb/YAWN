from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("work_logs", "0002_alter_fiscalperiod_reconciliation_cutoff")]

    operations = [
        migrations.AddField(
            model_name="workinofficerecord",
            name="correction_deadline",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workinofficerecord",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
