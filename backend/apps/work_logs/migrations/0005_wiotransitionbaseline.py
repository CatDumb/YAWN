from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_userpreference_version"),
        ("work_logs", "0004_remediation_foundations"),
    ]

    operations = [
        migrations.CreateModel(
            name="WioTransitionBaseline",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cutoff_date", models.DateField()),
                ("target_days", models.DecimalField(decimal_places=2, max_digits=10)),
                ("achieved_days", models.DecimalField(decimal_places=2, max_digits=10)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "employee",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transition_baseline",
                        to="accounts.companymembership",
                    ),
                ),
                (
                    "period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transition_baselines",
                        to="work_logs.fiscalperiod",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="wiotransitionbaseline",
            constraint=models.CheckConstraint(
                condition=models.Q(("target_days__gte", 0)),
                name="work_logs_transition_target_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="wiotransitionbaseline",
            constraint=models.CheckConstraint(
                condition=models.Q(("achieved_days__gte", 0)),
                name="work_logs_transition_achieved_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="wiotransitionbaseline",
            constraint=models.CheckConstraint(
                condition=models.Q(("target_days__gt", 0), ("achieved_days", 0), _connector="OR"),
                name="work_logs_transition_zero_target_zero_achieved",
            ),
        ),
    ]
