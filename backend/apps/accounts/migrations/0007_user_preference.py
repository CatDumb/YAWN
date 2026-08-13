from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_manager_assignment_effective_dates")]

    operations = [
        migrations.CreateModel(
            name="UserPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("theme", models.CharField(choices=[("system", "System"), ("light", "Light"), ("dark", "Dark")], default="system", max_length=10)),
                ("language", models.CharField(choices=[("en", "English"), ("vi", "Vietnamese")], default="en", max_length=5)),
                ("reduced_motion", models.BooleanField(default=False)),
                ("planner_location", models.CharField(blank=True, max_length=12)),
                ("planner_commitment", models.CharField(blank=True, max_length=12)),
                ("week_start", models.PositiveSmallIntegerField(default=1)),
                ("display_name", models.CharField(blank=True, max_length=150)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="preference", to="accounts.user")),
            ],
        ),
    ]
