FROM ghcr.io/astral-sh/uv:0.12.10 AS uv

FROM python:3.12-slim AS builder

COPY --from=uv /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim AS runtime

ARG DEPLOYMENT_VERSION=development

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEPLOYMENT_VERSION=$DEPLOYMENT_VERSION \
    PATH=/app/.venv/bin:$PATH

RUN addgroup --system wio && adduser --system --ingroup wio --home /home/wio wio

WORKDIR /app
COPY --from=builder --chown=wio:wio /app/.venv .venv
COPY --chown=wio:wio . .

RUN DJANGO_SETTINGS_MODULE=config.settings.test python manage.py collectstatic --noinput

USER wio
EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
