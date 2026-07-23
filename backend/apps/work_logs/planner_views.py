import logging
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.work_logs.models import WorkIntentionOccurrence, WorkIntentionSeries
from apps.work_logs.planner import edit_intention, preview, projection, save_intentions
from apps.work_logs.services import company_today
from apps.work_logs.views import membership_for

logger = logging.getLogger("wio.planner")


def parse_payload(data):
    return {
        "start": date.fromisoformat(data["start_date"]),
        "end": date.fromisoformat(data.get("end_date", data["start_date"])),
        "location": data["location"],
        "commitment": data["commitment"],
        "note": data.get("note", ""),
        "weekdays": data.get("weekdays"),
    }


def safe_failure_response(message, *, event_type, error):
    logger.error(
        event_type,
        extra={
            "error_class": error.__class__.__name__,
        },
    )
    return Response({"detail": message}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class PlannerPreviewView(APIView):
    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        try:
            values = parse_payload(request.data)
            items = preview(
                employee=membership_for(request.user),
                **{k: values[k] for k in ["start", "end", "weekdays"]},
            )
        except (KeyError, ValueError, ValidationError) as error:
            return Response({"detail": str(error)}, status=400)
        return Response([{**item, "date": item["date"].isoformat()} for item in items])


class PlannerProjectionView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            result = projection(employee=membership_for(request.user))
        except ValidationError as error:
            return Response({"detail": error.messages[0]}, status=400)
        except Exception as error:
            return safe_failure_response(
                "Planner projection is temporarily unavailable. Try again later.",
                event_type="planner_projection_failed",
                error=error,
            )
        return Response(
            {
                **{key: value for key, value in result.items() if key != "period"},
                "period_name": result["period"].name,
            }
        )


class PlannerIntentionsView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        employee = membership_for(request.user)
        records = WorkIntentionOccurrence.objects.filter(employee=employee).order_by("date")
        return Response(
            [
                {
                    "id": item.pk,
                    "date": item.date,
                    "location": item.location,
                    "commitment": item.commitment,
                    "note": item.note,
                    "excluded_reason": item.excluded_reason,
                    "series_id": item.series_id,
                    "version": item.version,
                }
                for item in records
            ]
        )

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        try:
            values = parse_payload(request.data)
            records = save_intentions(
                employee=membership_for(request.user),
                replace=bool(request.data.get("replace", False)),
                **values,
            )
        except (KeyError, ValueError, ValidationError) as error:
            return Response({"detail": str(error)}, status=400)
        except Exception as error:
            return safe_failure_response(
                "Planner save is temporarily unavailable. Try again later.",
                event_type="planner_save_failed",
                error=error,
            )
        return Response({"created": len(records)}, status=201)


class PlannerIntentionDetailView(APIView):
    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def patch(self, request, pk):
        try:
            record = edit_intention(
                employee=membership_for(request.user),
                record_id=pk,
                version=request.data.get("version"),
                scope=request.data.get("scope", "one"),
                location=request.data.get("location"),
                commitment=request.data.get("commitment"),
                note=request.data.get("note"),
            )
        except RuntimeError:
            return Response(
                {"detail": "Intention changed. Reload latest state and retry."},
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as error:
            return Response({"detail": error.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"updated": len(record)})

    @transaction.atomic
    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        employee = membership_for(request.user)
        record = (
            WorkIntentionOccurrence.objects.select_for_update()
            .filter(employee=employee, pk=pk)
            .first()
        )
        if record is None:
            return Response({"detail": "Intention not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            version = int(request.query_params["version"])
        except (KeyError, TypeError, ValueError):
            return Response(
                {"detail": "Version is required for every delete."},
                status=status.HTTP_409_CONFLICT,
            )
        if record.version != version:
            return Response(
                {"detail": "Intention changed. Reload latest state and retry."},
                status=status.HTTP_409_CONFLICT,
            )
        if request.query_params.get("scope") == "series":
            if request.query_params.get("confirm") != "true":
                return Response(
                    {"detail": "Series deletion requires confirmation."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if record.series_id is None:
                return Response(
                    {"detail": "This intention is not part of a series."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with transaction.atomic():
                series = WorkIntentionSeries.objects.select_for_update().get(pk=record.series_id)
                today = company_today()
                series.occurrences.filter(date__gte=today).delete()
                if series.starts_on >= today:
                    series.delete()
                else:
                    series.ends_on = today - timedelta(days=1)
                    series.version += 1
                    series.save(update_fields=["ends_on", "version"])
            return Response(status=status.HTTP_204_NO_CONTENT)
        record.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
