from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(
                fields=["target_type", "target_id", "-created_at", "-id"],
                name="audit_target_recent_idx",
            ),
        ),
    ]
