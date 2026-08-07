import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Case, Exists, IntegerField, OuterRef, Value, When
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import CompanyMembership
from apps.audit.models import AuditEvent
from apps.work_logs.approvals import (
    approve_record,
    assign_pending_record,
    hr_membership,
    manager_membership,
    reject_scoped_record,
    scoped_pending,
    undo_approval,
)
from apps.work_logs.models import FiscalPeriod, WorkInOfficeRecord
from apps.work_logs.serializers import (
    ApprovalAssigneeSerializer,
    ApprovalDecisionAssignSerializer,
    ApprovalDecisionReasonSerializer,
    ApprovalDecisionRequestSerializer,
    ApprovalDecisionVersionSerializer,
    ApprovalWorkInOfficeRecordDetailSerializer,
    ApprovalWorkInOfficeRecordSerializer,
    AuditEventSerializer,
    AuditTimelinePageSerializer,
    ErrorDetailSerializer,
    ManagerAuditTimelinePageSerializer,
    VersionRequestSerializer,
    WorkInOfficeCreateSerializer,
    WorkInOfficeDetailSerializer,
    WorkInOfficeListQuerySerializer,
    WorkInOfficeRecordSerializer,
    WorkInOfficeUpdateSerializer,
)
from apps.work_logs.services import company_today, save_record, undo_self_approval

logger = logging.getLogger("wio.work_logs")
AUDIT_PAGE_SIZE = 50
APPROVAL_PAGE_PARAMETER = OpenApiParameter(
    name="page",
    type={"type": "integer", "minimum": 1},
    location=OpenApiParameter.QUERY,
)
OWNERSHIP_HAS_NEXT_HEADER = OpenApiParameter(
    name="X-Has-Next",
    type=OpenApiTypes.BOOL,
    location=OpenApiParameter.HEADER,
    response=[200],
)


def membership_for(user):
    memberships = list(
        CompanyMembership.objects.filter(user=user, is_active=True, company__is_active=True)[:2]
    )
    if len(memberships) != 1:
        raise Http404("Active company scope is ambiguous. Contact HR/admin.")
    return memberships[0]


def ordered_approval_queue(manager):
    reconciliation_period = FiscalPeriod.objects.filter(
        company=manager.company,
        state=FiscalPeriod.State.RECONCILIATION,
        start_date__lte=OuterRef("work_date"),
        end_date__gte=OuterRef("work_date"),
    )
    return (
        scoped_pending(manager)
        .select_related("employee__base_location", "employee__user")
        .annotate(is_reconciliation=Exists(reconciliation_period))
        .order_by("-is_reconciliation", "submitted_at", "pk")
    )


def positive_page_number(raw_page):
    try:
        page = int(raw_page or 1)
    except (TypeError, ValueError) as error:
        raise DjangoValidationError("page must be a positive integer.") from error
    if page < 1:
        raise DjangoValidationError("page must be a positive integer.")
    return page


def safe_failure_response(message, *, event_type, error):
    logger.error(
        event_type,
        extra={
            "error_class": error.__class__.__name__,
        },
    )
    return Response({"detail": message}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


def audit_timeline_page(record_id, page):
    start = (page - 1) * AUDIT_PAGE_SIZE
    events = list(
        AuditEvent.objects.filter(
            target_type="work_logs.WorkInOfficeRecord",
            target_id=str(record_id),
        ).order_by("-created_at", "-pk")[start : start + AUDIT_PAGE_SIZE + 1]
    )
    return {
        "results": events[:AUDIT_PAGE_SIZE],
        "next_page": page + 1 if len(events) > AUDIT_PAGE_SIZE else None,
    }


class WorkInOfficeListCreateView(APIView):
    @extend_schema(
        parameters=[WorkInOfficeListQuerySerializer],
        responses=WorkInOfficeRecordSerializer(many=True),
    )
    def get(self, request):
        membership = membership_for(request.user)
        query = WorkInOfficeListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        records = WorkInOfficeRecord.objects.filter(employee=membership).select_related(
            "employee__base_location",
            "employee__user",
        )
        if filters["attention"]:
            records = records.filter(
                review_state__in=(
                    WorkInOfficeRecord.ReviewState.DRAFT,
                    WorkInOfficeRecord.ReviewState.REJECTED,
                )
            ).order_by("-updated_at", "-pk")[:50]
            return Response(WorkInOfficeRecordSerializer(records, many=True).data)
        if start := filters.get("start_date"):
            records = records.filter(work_date__gte=start)
        if end := filters.get("end_date"):
            records = records.filter(work_date__lte=end)
        if month := filters.get("month"):
            year, number = month.split("-", 1)
            records = records.filter(work_date__year=int(year), work_date__month=int(number))
        elif not filters.get("work_date") and not start and not end:
            today = company_today(membership.company)
            records = records.filter(work_date__year=today.year, work_date__month=today.month)
        for field in ("work_date", "location_choice", "review_state"):
            if value := filters.get(field):
                records = records.filter(**{field: value})
        return Response(WorkInOfficeRecordSerializer(records, many=True).data)

    @extend_schema(
        request=WorkInOfficeCreateSerializer,
        responses={201: WorkInOfficeRecordSerializer},
    )
    def post(self, request):
        serializer = WorkInOfficeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership = membership_for(request.user)
        if WorkInOfficeRecord.objects.filter(
            employee=membership, work_date=data["work_date"]
        ).exists():
            return Response(
                {"detail": "A record already exists for this date."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            record = save_record(employee=membership, actor=request.user, **data)
        except RuntimeError as error:
            return Response(
                {
                    "detail": "Version is required for an existing record."
                    if str(error) == "version_required"
                    else "Record changed. Reload latest state and retry."
                },
                status=409,
            )
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            return Response(
                {"detail": "A record already exists for this date."},
                status=status.HTTP_409_CONFLICT,
            )
        except Exception as error:
            return safe_failure_response(
                "Work-in-office record is temporarily unavailable. Try again later.",
                event_type="wio_record_create_failed",
                error=error,
            )
        return Response(WorkInOfficeRecordSerializer(record).data, status=status.HTTP_201_CREATED)


class WorkInOfficeMetadataView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        membership = membership_for(request.user)
        today = company_today(membership.company)
        period = FiscalPeriod.objects.filter(
            company=membership.company, start_date__lte=today, end_date__gte=today
        ).first()
        return Response(
            {
                "company_date": today.isoformat(),
                "timezone": membership.company.timezone,
                "fiscal_period": (
                    {
                        "name": period.name,
                        "state": period.state,
                        "start_date": period.start_date,
                        "end_date": period.end_date,
                    }
                    if period
                    else None
                ),
            }
        )


class WorkInOfficeDetailView(APIView):
    def _record(self, request, pk):
        return get_object_or_404(WorkInOfficeRecord, pk=pk, employee=membership_for(request.user))

    @extend_schema(responses=WorkInOfficeDetailSerializer)
    def get(self, request, pk):
        record = self._record(request, pk)
        data = WorkInOfficeRecordSerializer(record).data
        timeline = audit_timeline_page(record.pk, 1)
        data["audit_timeline"] = AuditEventSerializer(timeline["results"], many=True).data
        data["audit_timeline_next_page"] = timeline["next_page"]
        return Response(data)

    @extend_schema(
        request=WorkInOfficeUpdateSerializer,
        responses={
            200: WorkInOfficeRecordSerializer,
            409: ErrorDetailSerializer,
        },
    )
    def put(self, request, pk):
        current = self._record(request, pk)
        if "version" not in request.data:
            return Response(
                {"detail": "Version is required for every update."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = WorkInOfficeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        version = data.pop("version")
        data["work_date"] = current.work_date
        try:
            record = save_record(
                employee=current.employee,
                version=version,
                expected_record_id=current.pk,
                actor=request.user,
                **data,
            )
        except RuntimeError as error:
            return Response(
                {
                    "detail": "Version is required for every update."
                    if str(error) == "version_required"
                    else "Record changed. Reload latest state and retry."
                },
                status=409,
            )
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            return safe_failure_response(
                "Work-in-office record is temporarily unavailable. Try again later.",
                event_type="wio_record_update_failed",
                error=error,
            )
        return Response(WorkInOfficeRecordSerializer(record).data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="version",
                type={"type": "integer", "minimum": 1},
                location=OpenApiParameter.QUERY,
                required=True,
            )
        ],
        responses={204: None, 409: ErrorDetailSerializer},
    )
    def delete(self, request, pk):
        current = self._record(request, pk)
        if request.query_params.get("version") is None:
            return Response({"detail": "Version is required for every delete."}, status=409)
        try:
            version = int(request.query_params["version"])
        except (TypeError, ValueError):
            return Response({"detail": "Version must be an integer."}, status=400)
        if version < 1:
            return Response({"detail": "Version must be at least 1."}, status=400)
        try:
            save_record(
                employee=current.employee,
                work_date=current.work_date,
                location_choice=None,
                note="",
                version=version,
                expected_record_id=current.pk,
                delete_draft=True,
                actor=request.user,
            )
        except RuntimeError:
            return Response(
                {"detail": "Record changed. Reload latest state and retry."}, status=409
            )
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            return safe_failure_response(
                "Work-in-office record is temporarily unavailable. Try again later.",
                event_type="wio_record_delete_failed",
                error=error,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SelfApprovalUndoView(APIView):
    @extend_schema(
        request=VersionRequestSerializer,
        responses={
            200: WorkInOfficeRecordSerializer,
            409: ErrorDetailSerializer,
        },
    )
    def post(self, request, pk):
        membership = membership_for(request.user)
        if "version" not in request.data:
            return Response(
                {"detail": "Version is required for every update."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = VersionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = undo_self_approval(
                employee=membership,
                record_id=pk,
                version=serializer.validated_data["version"],
                actor=request.user,
            )
        except RuntimeError:
            return Response(
                {"detail": "Record changed. Reload latest state and retry."}, status=409
            )
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WorkInOfficeRecordSerializer(record).data)


class WorkInOfficeTimelineView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="page",
                type={"type": "integer", "minimum": 1},
                location=OpenApiParameter.QUERY,
            )
        ],
        responses=AuditTimelinePageSerializer,
    )
    def get(self, request, pk):
        get_object_or_404(
            WorkInOfficeRecord,
            pk=pk,
            employee=membership_for(request.user),
        )
        try:
            page = positive_page_number(request.query_params.get("page"))
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=400)
        return Response(AuditTimelinePageSerializer(audit_timeline_page(pk, page)).data)


class ApprovalQueueView(APIView):
    @extend_schema(
        parameters=[APPROVAL_PAGE_PARAMETER],
        responses=ApprovalWorkInOfficeRecordSerializer(many=True),
    )
    def get(self, request):
        try:
            manager = manager_membership(request.user)
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=403)
        records = ordered_approval_queue(manager)
        try:
            page = positive_page_number(request.query_params.get("page"))
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=400)
        start = (page - 1) * 50
        records = records[start : start + 50]
        return Response(ApprovalWorkInOfficeRecordSerializer(records, many=True).data)


class ApprovalDetailView(APIView):
    @extend_schema(responses=ApprovalWorkInOfficeRecordDetailSerializer)
    def get(self, request, pk):
        try:
            manager = manager_membership(request.user)
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=403)
        record = get_object_or_404(
            scoped_pending(manager).select_related("employee__base_location", "employee__user"),
            pk=pk,
        )
        return Response(ApprovalWorkInOfficeRecordDetailSerializer(record).data)


class ApprovalOwnershipQueueView(APIView):
    @extend_schema(
        parameters=[APPROVAL_PAGE_PARAMETER, OWNERSHIP_HAS_NEXT_HEADER],
        responses=ApprovalWorkInOfficeRecordSerializer(many=True),
    )
    def get(self, request):
        try:
            hr = hr_membership(request.user)
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=403)
        try:
            page = positive_page_number(request.query_params.get("page"))
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=400)
        start = (page - 1) * 50
        records = list(
            WorkInOfficeRecord.objects.filter(
                employee__company=hr.company,
                review_state__in=(
                    WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
                    WorkInOfficeRecord.ReviewState.PENDING,
                ),
            )
            .annotate(
                ownership_priority=Case(
                    When(
                        review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
                        then=Value(0),
                    ),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            .select_related("employee__base_location", "employee__user")
            .order_by("ownership_priority", "submitted_at", "pk")[start : start + 51]
        )
        return Response(
            ApprovalWorkInOfficeRecordSerializer(records[:50], many=True).data,
            headers={"X-Has-Next": "true" if len(records) > 50 else "false"},
        )


class ApprovalTimelineView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="page",
                type={"type": "integer", "minimum": 1},
                location=OpenApiParameter.QUERY,
            )
        ],
        responses=ManagerAuditTimelinePageSerializer,
    )
    def get(self, request, pk):
        try:
            manager = manager_membership(request.user)
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=403)
        try:
            page = positive_page_number(request.query_params.get("page"))
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=400)
        record = get_object_or_404(
            WorkInOfficeRecord,
            pk=pk,
            employee__company=manager.company,
            approval_owner_snapshot__membership_id=manager.pk,
        )
        return Response(
            ManagerAuditTimelinePageSerializer(audit_timeline_page(record.pk, page)).data
        )


class PendingAssignmentQueueView(APIView):
    @extend_schema(
        parameters=[APPROVAL_PAGE_PARAMETER],
        responses=ApprovalWorkInOfficeRecordSerializer(many=True),
    )
    def get(self, request):
        try:
            hr = hr_membership(request.user)
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=403)
        try:
            page = positive_page_number(request.query_params.get("page"))
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=400)
        start = (page - 1) * 50
        records = (
            WorkInOfficeRecord.objects.filter(
                employee__company=hr.company,
                review_state=WorkInOfficeRecord.ReviewState.PENDING_ASSIGNMENT,
            )
            .select_related("employee__base_location", "employee__user")
            .order_by("submitted_at", "pk")[start : start + 50]
        )
        return Response(ApprovalWorkInOfficeRecordSerializer(records, many=True).data)


class ApprovalAssigneeView(APIView):
    """Active same-company managers an HR/admin user may assign a pending claim to."""

    @extend_schema(responses=ApprovalAssigneeSerializer(many=True))
    def get(self, request):
        try:
            hr = hr_membership(request.user)
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=403)
        managers = (
            CompanyMembership.objects.filter(
                company=hr.company,
                role=CompanyMembership.Role.MANAGER,
                is_active=True,
                user__is_active=True,
            )
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__email", "pk")
        )
        return Response(
            [
                {
                    "id": manager.pk,
                    "name": manager.user.get_full_name() or manager.user.email,
                    "email": manager.user.email,
                }
                for manager in managers
            ]
        )


class ApprovalCountView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            manager = manager_membership(request.user)
        except DjangoValidationError:
            return Response({"count": 0, "oldest_submitted_at": None})
        records = scoped_pending(manager)
        oldest = records.order_by("submitted_at").values_list("submitted_at", flat=True).first()
        return Response({"count": records.count(), "oldest_submitted_at": oldest})


class ApprovalDecisionView(APIView):
    @extend_schema(
        request=ApprovalDecisionRequestSerializer,
        responses={
            200: ApprovalWorkInOfficeRecordSerializer,
            409: ErrorDetailSerializer,
        },
    )
    def post(self, request, pk, action):
        serializer_class = {
            "approve": ApprovalDecisionVersionSerializer,
            "undo": ApprovalDecisionVersionSerializer,
            "reject": ApprovalDecisionReasonSerializer,
            "assign": ApprovalDecisionAssignSerializer,
        }.get(action)
        if serializer_class is None:
            return Response({"detail": "Unknown approval action."}, status=404)
        if "version" not in request.data:
            return Response(
                {"detail": "Version is required for every approval action."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            version = data["version"]
            if action == "assign":
                hr = hr_membership(request.user)
                record = assign_pending_record(
                    hr=hr,
                    record_id=pk,
                    manager_id=data["manager_membership_id"],
                    version=version,
                    reason=data["reason"],
                )
            else:
                manager = manager_membership(request.user)
                if action == "approve":
                    record = approve_record(manager=manager, record_id=pk, version=version)
                elif action == "reject":
                    record = reject_scoped_record(
                        manager=manager,
                        record_id=pk,
                        version=version,
                        reason=data["reason"],
                    )
                elif action == "undo":
                    record = undo_approval(manager=manager, record_id=pk, version=version)
        except RuntimeError:
            return Response({"detail": "Claim changed. Reload latest state and retry."}, status=409)
        except DjangoValidationError as error:
            return Response({"detail": error.messages[0]}, status=400)
        except Exception as error:
            event_type = {
                "assign": "approval_assignment_failed",
                "undo": "approval_undo_failed",
            }.get(action, "approval_decision_failed")
            return safe_failure_response(
                "Approval action is temporarily unavailable. Try again later.",
                event_type=event_type,
                error=error,
            )
        return Response(ApprovalWorkInOfficeRecordSerializer(record).data)
