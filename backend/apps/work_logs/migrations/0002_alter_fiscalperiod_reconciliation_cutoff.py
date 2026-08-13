from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("work_logs", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="fiscalperiod",
            name="reconciliation_cutoff",
            field=models.DateField(blank=True),
        ),
    ]
