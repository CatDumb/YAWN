from datetime import date

from django.utils.html import strip_tags
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.audit.models import AuditEvent
from apps.work_logs.models import WorkInOfficeRecord


def validate_plain_text_note(value):
    if strip_tags(value) != value:
        raise serializers.ValidationError("Note must be plain text.")
    return value


class TransitionBaselineInputSerializer(serializers.Serializer):
    cutoff_month = serializers.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$")
    target_days = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    achieved_days = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    version = serializers.IntegerField(min_value=1, required=False)

    def validate_cutoff_month(self, value):
        return date.fromisoformat(f"{value}-01")

    def validate(self, attrs):
        if attrs["target_days"] == 0 and attrs["achieved_days"] != 0:
            raise serializers.ValidationError(
                {"achieved_days": "Achieved days must be zero when target days are zero."}
            )
        return attrs


class WorkInOfficeRecordSerializer(serializers.ModelSerializer):
    save_as_draft = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
    )
    employee_name = serializers.SerializerMethodField()
    employee_email = serializers.EmailField(source="employee.user.email", read_only=True)
    base_location_name = serializers.CharField(
        source="employee.base_location.name", read_only=True, allow_null=True
    )

    def get_employee_name(self, obj) -> str:
        return obj.employee.user.get_full_name() or obj.employee.user.email

    def validate_note(self, value):
        return validate_plain_text_note(value)

    class Meta:
        model = WorkInOfficeRecord
        fields = [
            "id",
            "employee_name",
            "employee_email",
            "base_location_name",
            "work_date",
            "location_choice",
            "save_as_draft",
            "review_state",
            "note",
            "approver_note",
            "version",
            "assignment_snapshot",
            "policy_snapshot",
            "approval_owner_snapshot",
            "approved_at",
            "approved_by_snapshot",
            "approval_method",
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
            "approval_method",
            "created_at",
            "updated_at",
            "submitted_at",
            "rejected_at",
            "correction_deadline",
        ]


class WorkInOfficeListQuerySerializer(serializers.Serializer):
    attention = serializers.BooleanField(required=False, default=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    work_date = serializers.DateField(required=False)
    month = serializers.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$", required=False)
    location_choice = serializers.ChoiceField(
        choices=WorkInOfficeRecord.LocationChoice.choices,
        required=False,
    )
    review_state = serializers.ChoiceField(
        choices=WorkInOfficeRecord.ReviewState.choices,
        required=False,
    )

    def validate(self, attrs):
        if attrs["attention"] and any(
            attrs.get(field)
            for field in (
                "start_date",
                "end_date",
                "work_date",
                "month",
                "location_choice",
                "review_state",
            )
        ):
            raise serializers.ValidationError(
                {"attention": "Attention cannot be combined with other list filters."}
            )
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        date_scopes = sum(
            (
                bool(attrs.get("work_date")),
                bool(attrs.get("month")),
                bool(start or end),
            )
        )
        if date_scopes > 1:
            raise serializers.ValidationError(
                {"date_scope": "Work date, month, and custom range are mutually exclusive."}
            )
        if bool(start) != bool(end):
            raise serializers.ValidationError(
                {"date_range": "Start date and end date must be provided together."}
            )
        if start and end and start > end:
            raise serializers.ValidationError(
                {"end_date": "End date must not be before start date."}
            )
        if start and end and (end - start).days >= 366:
            raise serializers.ValidationError(
                {"date_range": "Custom date ranges cannot exceed 366 days."}
            )
        return attrs


class WorkInOfficeCreateSerializer(serializers.Serializer):
    work_date = serializers.DateField()
    location_choice = serializers.ChoiceField(
        choices=WorkInOfficeRecord.LocationChoice.choices,
        required=False,
        allow_null=True,
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)
    save_as_draft = serializers.BooleanField(required=False, default=False)

    def validate_note(self, value):
        return validate_plain_text_note(value)


class WorkInOfficeUpdateSerializer(WorkInOfficeCreateSerializer):
    version = serializers.IntegerField(min_value=1)


class VersionRequestSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class ApprovalDecisionVersionSerializer(VersionRequestSerializer):
    pass


class ApprovalDecisionReasonSerializer(VersionRequestSerializer):
    reason = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)


class ApprovalDecisionAssignSerializer(ApprovalDecisionReasonSerializer):
    manager_membership_id = serializers.IntegerField(min_value=1)


class ApprovalDecisionRequestSerializer(VersionRequestSerializer):
    reason = serializers.CharField(
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
        required=False,
        help_text="Required for Reject and Assign actions.",
    )
    manager_membership_id = serializers.IntegerField(
        min_value=1,
        required=False,
        help_text="Required for Assign actions.",
    )


class ApprovalAssigneeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()


class ErrorDetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


class ApprovalWorkInOfficeRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_email = serializers.EmailField(source="employee.user.email", read_only=True)
    base_location_name = serializers.CharField(
        source="employee.base_location.name", read_only=True, allow_null=True
    )
    note_present = serializers.SerializerMethodField()

    def get_employee_name(self, obj) -> str:
        return obj.employee.user.get_full_name() or obj.employee.user.email

    def get_note_present(self, obj) -> bool:
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
        fields = ["id", "event_type", "metadata", "created_at"]


class AuditTimelinePageSerializer(serializers.Serializer):
    results = AuditEventSerializer(many=True)
    next_page = serializers.IntegerField(allow_null=True)


class ManagerAuditEventSerializer(serializers.ModelSerializer):
    details = serializers.SerializerMethodField()

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_details(self, obj):
        metadata = obj.metadata or {}
        return {
            field: metadata[field]
            for field in ("actor_role", "reason", "revision", "from_state", "to_state")
            if field in metadata
        }

    class Meta:
        model = AuditEvent
        fields = ["id", "event_type", "details", "created_at"]


class ManagerAuditTimelinePageSerializer(serializers.Serializer):
    results = ManagerAuditEventSerializer(many=True)
    next_page = serializers.IntegerField(allow_null=True)


class WorkInOfficeDetailSerializer(WorkInOfficeRecordSerializer):
    audit_timeline = AuditEventSerializer(many=True, read_only=True)
    audit_timeline_next_page = serializers.IntegerField(allow_null=True, read_only=True)

    class Meta(WorkInOfficeRecordSerializer.Meta):
        fields = [
            *WorkInOfficeRecordSerializer.Meta.fields,
            "audit_timeline",
            "audit_timeline_next_page",
        ]
        read_only_fields = [
            *WorkInOfficeRecordSerializer.Meta.read_only_fields,
            "audit_timeline",
            "audit_timeline_next_page",
        ]
