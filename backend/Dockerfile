FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements.txt .
RUN python -m pip install --prefix=/install --require-hashes -r requirements.txt

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/wio/.local/bin:$PATH

RUN addgroup --system wio && adduser --system --ingroup wio --home /home/wio wio

WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=wio:wio . .

RUN DJANGO_SETTINGS_MODULE=config.settings.test python manage.py collectstatic --noinput

USER wio
EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
