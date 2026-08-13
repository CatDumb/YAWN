from datetime import date

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_companymembership_base_location"),
        ("work_logs", "0004_remediation_foundations"),
    ]

    operations = [
        migrations.AddField(
            model_name="managerassignment",
            name="effective_from",
            field=models.DateField(default=date(1970, 1, 1)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="managerassignment",
            name="effective_to",
            field=models.DateField(blank=True, null=True),
        ),
    ]
