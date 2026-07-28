from datetime import date

from django.db import migrations


def ambiguous_employee_ids(rows):
    ambiguous = set()
    current_employee_id = None
    covered_through = None
    for employee_id, effective_from, effective_to in rows:
        if employee_id != current_employee_id:
            current_employee_id = employee_id
            covered_through = None
        if covered_through is not None and effective_from <= covered_through:
            ambiguous.add(employee_id)
        candidate_end = effective_to or date.max
        if covered_through is None or candidate_end > covered_through:
            covered_through = candidate_end
    return sorted(ambiguous)


def reject_ambiguous_active_assignments(apps, schema_editor):
    ManagerAssignment = apps.get_model("accounts", "ManagerAssignment")
    rows = (
        ManagerAssignment.objects.filter(is_active=True)
        .order_by("employee_id", "effective_from", "pk")
        .values_list("employee_id", "effective_from", "effective_to")
    )
    employee_ids = ambiguous_employee_ids(rows)
    if employee_ids:
        joined_ids = ", ".join(str(employee_id) for employee_id in employee_ids)
        raise RuntimeError(
            "Cannot migrate ambiguous active manager assignments. "
            f"Repair employee membership IDs first: {joined_ids}"
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_userpreference_version")]

    operations = [
        migrations.RunPython(
            reject_ambiguous_active_assignments,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="managerassignment",
            name="accounts_manager_employee_unique",
        ),
    ]
