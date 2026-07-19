import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger("wio.health")


@require_GET
def health(_request):
    return JsonResponse({"status": "ok"})


@require_GET
def ready(_request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("readiness_check_failed")
        return JsonResponse({"status": "not_ready"}, status=503)
    return JsonResponse({"status": "ready"})
