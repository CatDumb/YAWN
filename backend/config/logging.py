import contextvars
import logging
import os

request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id",
    default="-",
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        record.deployment_version = os.getenv("DEPLOYMENT_VERSION", "development")
        return True
