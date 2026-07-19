import logging
import re
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from config.logging import request_id_context

logger = logging.getLogger("wio.request")
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestLogMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_request_id
            if VALID_REQUEST_ID.fullmatch(supplied_request_id)
            else uuid.uuid4().hex
        )
        token = request_id_context.set(request_id)
        started_at = time.perf_counter()

        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            logger.info(
                "request_completed",
                extra={
                    "http_method": request.method,
                    "http_path": request.path,
                    "http_status": response.status_code,
                    "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "user_id": str(request.user.pk) if request.user.is_authenticated else None,
                },
            )
            return response
        finally:
            request_id_context.reset(token)
