from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.work_logs.ratio import percentage_up
from apps.work_logs.serializers import TransitionBaselineInputSerializer
from apps.work_logs.services import save_transition_baseline, transition_baseline_state
from apps.work_logs.views import membership_for


def baseline_payload(state):
    baseline = state["baseline"]
    if baseline is None:
        return {
            "eligible": state["eligible"],
            "lock_reason": state["lock_reason"],
            "latest_cutoff_month": state["latest_cutoff_month"],
            "baseline": None,
        }
    ratio_display = "N/A"
    if baseline.target_days:
        ratio_display = f"{percentage_up(baseline.achieved_days / baseline.target_days):.2f}%"
    return {
        "eligible": False,
        "lock_reason": state["lock_reason"],
        "latest_cutoff_month": state.get("latest_cutoff_month"),
        "baseline": {
            "cutoff_month": baseline.cutoff_date.strftime("%Y-%m"),
            "cutoff_date": baseline.cutoff_date.isoformat(),
            "target_days": str(baseline.target_days),
            "achieved_days": str(baseline.achieved_days),
            "ratio_display": ratio_display,
            "version": baseline.version,
            "can_edit": not state["locked"],
        },
    }


class TransitionBaselineView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        employee = membership_for(request.user)
        return Response(baseline_payload(transition_baseline_state(employee)))

    @extend_schema(request=TransitionBaselineInputSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = TransitionBaselineInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = membership_for(request.user)
        try:
            save_transition_baseline(
                employee=employee,
                actor=request.user,
                **serializer.validated_data,
            )
        except RuntimeError:
            return Response(
                {"detail": "Transition baseline already exists. Reload it before editing."},
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as error:
            return Response({"detail": error.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            baseline_payload(transition_baseline_state(employee)),
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=TransitionBaselineInputSerializer, responses=OpenApiTypes.OBJECT)
    def put(self, request):
        serializer = TransitionBaselineInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if "version" not in serializer.validated_data:
            return Response(
                {"detail": "Version is required for transition baseline updates."},
                status=status.HTTP_409_CONFLICT,
            )
        employee = membership_for(request.user)
        try:
            save_transition_baseline(
                employee=employee,
                actor=request.user,
                **serializer.validated_data,
            )
        except RuntimeError:
            return Response(
                {"detail": "Transition baseline changed. Reload latest state and retry."},
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as error:
            return Response({"detail": error.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(baseline_payload(transition_baseline_state(employee)))
