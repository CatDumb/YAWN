# Backend

Django and Django REST Framework API for YAWN.

## Responsibilities

- Authentication, company membership, roles, and permissions
- Daily work logs, ratio rules, approvals, and endorsements
- Reports and audit history; evidence access, floor plans, and seats remain future scope
- PostgreSQL persistence and Django migrations

## Setup

```powershell
Copy-Item .env.example .env
$env:DJANGO_READ_DOT_ENV_FILE = "true"
uv sync --all-groups --frozen
uv run python manage.py migrate
uv run python manage.py runserver
```

Create initial administrator after PostgreSQL is available:

```powershell
uv run python manage.py createsuperuser
```

Users become OTP-eligible only after an administrator creates an active company membership.

For disposable local development only, set `WIO_ALLOW_INSECURE_DEV_SEED=true` alongside
`DJANGO_DEBUG=true`, then run:

```powershell
uv run python manage.py seed_dev_admin
```

The one-time command creates `admin@wio.local` with password `admin`, an active `wio` company, and
an active HR/admin membership. It refuses to run outside debug mode or without the explicit opt-in,
never runs automatically, and never changes an existing account.

Before accepting public access requests, set `WIO_SIGNUP_COMPANY_SLUG` in `.env` to an active
`Company.slug`. For a new local database, create one after migration:

```powershell
uv run python manage.py shell -c "from apps.accounts.models import Company; Company.objects.get_or_create(slug='wio', defaults={'name': 'WIO'})"
```

Then set `WIO_SIGNUP_COMPANY_SLUG=wio` in `.env` and restart `runserver`.

## Authentication and API

- `GET /api/v1/auth/csrf/`: issue CSRF cookie
- `POST /api/v1/auth/sign-up/`: submit generic, rate-limited access request for configured company
- `POST /api/v1/auth/otp/request/`: request generic, rate-limited OTP challenge
- `POST /api/v1/auth/otp/verify/`: consume OTP and create session
- `POST /api/v1/auth/logout/`: end session
- `GET /api/v1/users/me/`: current user and memberships
- `GET /health/`: process liveness
- `GET /ready/`: database readiness

OTP codes are hashed, single-use, short-lived, attempt-limited, and never logged. Expired challenge records can be removed with:

```powershell
uv run python manage.py purge_expired_otps --hours 24
```

Direct Django development reads mail settings from ignored `backend/.env`; Docker Compose reads them
from root ignored `.env`. Both use console email unless their own environment file contains SMTP
values. For local Gmail testing, enable Google 2-Step Verification on YAWN's dedicated Gmail account,
create an App Password, and put these values in the environment file for the process you start:

```text
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DJANGO_EMAIL_HOST=smtp.gmail.com
DJANGO_EMAIL_PORT=587
DJANGO_EMAIL_HOST_USER=yawn@example.com
DJANGO_EMAIL_HOST_PASSWORD=google-app-password
DJANGO_EMAIL_USE_TLS=true
DJANGO_DEFAULT_FROM_EMAIL=yawn@example.com
DJANGO_EMAIL_TIMEOUT_SECONDS=10
WIO_APP_URL=http://localhost:3000
```

Production requires the same SMTP settings and an HTTPS homepage `WIO_APP_URL`; store every secret
in deployment secret storage, never Git. `DJANGO_DEFAULT_FROM_EMAIL` must exactly match the SMTP
username. OTP delivery is scheduled after its challenge transaction commits; delivery failures are
logged without email addresses or codes and do not change the generic request response. Access
approval sends one post-commit plain-text notification; its delivery failure never rolls back
approval and is logged without recipient or message content.

Sessions expire exactly 14 days after login and do not refresh on activity. OTP lifetime is 10
minutes, verification allows five attempts, resend cooldown is 60 seconds, and limits are five
requests per email and 100 per request fingerprint per hour. The Compose `cleanup` service runs
`purge_expired_otps --hours 24` and `clearsessions` every 24 hours.

## API documentation

Backend uses `drf-spectacular` to generate an OpenAPI 3 schema. It exposes:

```text
/api/schema/              OpenAPI schema
/api/schema/swagger-ui/   Swagger UI
/api/schema/redoc/        ReDoc
```

Development exposes docs publicly. Production restricts schema views to staff users. CI generates and validates the OpenAPI schema from current Django configuration.

## Layout

```text
config/                   Django settings and URL configuration
apps/accounts/            Users, roles, and manager assignments
apps/work_logs/           Logs, ratios, approvals, and endorsements
apps/audit/               Audit events
```

Settings are split across `config/settings/base.py`, `development.py`, `test.py`, and `production.py`. Production fails closed without a strong secret and allowed hosts.
Office and evidence apps will be created with their first implemented model or endpoint.
