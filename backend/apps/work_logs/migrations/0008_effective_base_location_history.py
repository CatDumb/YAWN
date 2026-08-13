from datetime import date

import django.db.models.deletion
from django.db import migrations, models


def backfill_base_location_history(apps, schema_editor):
    CompanyMembership = apps.get_model("accounts", "CompanyMembership")
    FiscalPeriod = apps.get_model("work_logs", "FiscalPeriod")
    Project = apps.get_model("work_logs", "Project")
    EmployeeHistory = apps.get_model("work_logs", "EmployeeBaseLocationAssignment")
    ProjectHistory = apps.get_model("work_logs", "ProjectBaseLocationAssignment")

    company_starts = {}
    for row in FiscalPeriod.objects.order_by("company_id", "start_date").values(
        "company_id", "start_date"
    ):
        company_starts.setdefault(row["company_id"], row["start_date"])
    employee_rows = [
        EmployeeHistory(
            employee_id=membership.pk,
            base_location_id=membership.base_location_id,
            effective_from=company_starts.get(membership.company_id, date(1970, 1, 1)),
        )
        for membership in CompanyMembership.objects.exclude(base_location__isnull=True)
    ]
    project_rows = [
        ProjectHistory(
            project_id=project.pk,
            base_location_id=project.base_location_id,
            effective_from=company_starts.get(project.company_id, date(1970, 1, 1)),
        )
        for project in Project.objects.all()
    ]
    EmployeeHistory.objects.bulk_create(employee_rows)
    ProjectHistory.objects.bulk_create(project_rows)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_manager_assignment_history_integrity"),
        ("work_logs", "0006_workinofficerecord_approval_method"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmployeeBaseLocationAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "base_location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="employee_assignments",
                        to="work_logs.baselocation",
                    ),
                ),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="base_location_assignments",
                        to="accounts.companymembership",
                    ),
                ),
            ],
            options={"ordering": ["-effective_from"]},
        ),
        migrations.CreateModel(
            name="ProjectBaseLocationAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "base_location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="project_assignments",
                        to="work_logs.baselocation",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="base_location_assignments",
                        to="work_logs.project",
                    ),
                ),
            ],
            options={"ordering": ["-effective_from"]},
        ),
        migrations.RunPython(
            backfill_base_location_history,
            migrations.RunPython.noop,
        ),
    ]
