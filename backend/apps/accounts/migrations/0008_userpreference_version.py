from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_user_preference")]

    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
