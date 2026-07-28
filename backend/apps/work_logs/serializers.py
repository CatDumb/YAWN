from django.utils.html import strip_tags
from rest_framework import serializers

from apps.audit.models import AuditEvent
from apps.work_logs.models import WorkInOfficeRecord


class TransitionBaselineInputSerializer(serializers.Serializer):
    cutoff_month = serializers.DateField(input_formats=["%Y-%m"], format="%Y-%m")
    target_days = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    achieved_days = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    version = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if attrs["target_days"] == 0 and attrs["achieved_days"] != 0:
            raise serializers.ValidationError(
                {"achieved_days": "Achieved days must be zero when target days are zero."}
            )
        return attrs


class WorkInOfficeRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_email = serializers.EmailField(source="employee.user.email", read_only=True)
    base_location_name = serializers.CharField(
        source="employee.base_location.name", read_only=True, allow_null=True
    )

    def get_employee_name(self, obj):
        return obj.employee.user.get_full_name() or obj.employee.user.email

    def validate_note(self, value):
        if strip_tags(value) != value:
            raise serializers.ValidationError("Note must be plain text.")
        return value

    class Meta:
        model = WorkInOfficeRecord
        fields = [
            "id",
            "employee_name",
            "employee_email",
            "base_location_name",
            "work_date",
            "location_choice",
            "review_state",
            "note",
            "approver_note",
            "version",
            "assignment_snapshot",
            "policy_snapshot",
            "approval_owner_snapshot",
            "approved_at",
            "approved_by_snapshot",
            "created_at",
            "updated_at",
            "submitted_at",
            "rejected_at",
            "correction_deadline",
        ]
        read_only_fields = [
            "id",
            "employee_name",
            "employee_email",
            "base_location_name",
            "review_state",
            "approver_note",
            "version",
            "assignment_snapshot",
            "policy_snapshot",
            "approval_owner_snapshot",
            "approved_at",
            "approved_by_snapshot",
            "created_at",
            "updated_at",
            "submitted_at",
            "rejected_at",
            "correction_deadline",
        ]


class ApprovalWorkInOfficeRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_email = serializers.EmailField(source="employee.user.email", read_only=True)
    base_location_name = serializers.CharField(
        source="employee.base_location.name", read_only=True, allow_null=True
    )
    note_present = serializers.SerializerMethodField()

    def get_employee_name(self, obj):
        return obj.employee.user.get_full_name() or obj.employee.user.email

    def get_note_present(self, obj):
        return bool(obj.note)

    class Meta:
        model = WorkInOfficeRecord
        fields = [
            "id",
            "employee_name",
            "employee_email",
            "base_location_name",
            "work_date",
            "location_choice",
            "review_state",
            "note_present",
            "version",
            "approved_at",
            "submitted_at",
            "rejected_at",
            "correction_deadline",
        ]


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["event_type", "metadata", "created_at"]
