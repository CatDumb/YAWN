# Backend

Django and Django REST Framework API for WIO Tracker.

## Responsibilities

- Authentication, company membership, roles, and permissions
- Daily work logs, ratio rules, approvals, and endorsements
- Evidence access, floor plans, seats, reports, and audit history
- PostgreSQL persistence and Django migrations

## Setup

```powershell
Copy-Item .env.example .env
uv sync --all-groups --frozen
uv run python manage.py migrate
uv run python manage.py runserver
```

Create initial administrator after PostgreSQL is available:

```powershell
uv run python manage.py createsuperuser
```

Users become OTP-eligible only after an administrator creates an active company membership.

## Authentication and API

- `GET /api/v1/auth/csrf/`: issue CSRF cookie
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

## API documentation

Backend uses `drf-spectacular` to generate an OpenAPI 3 schema. It exposes:

```text
/api/schema/              OpenAPI schema
/api/schema/swagger-ui/   Swagger UI
/api/schema/redoc/        ReDoc
```

Development exposes docs publicly. Production restricts schema views to staff users. CI validates committed `schema.yml` against generated API definitions.

## Layout

```text
config/                   Django settings and URL configuration
apps/accounts/            Users, roles, and manager assignments
apps/work_logs/           Logs, ratios, approvals, and endorsements
apps/office/              Floor plans and seats
apps/evidence/            Private evidence upload and access
apps/audit/               Audit events
```

Settings are split across `config/settings/base.py`, `development.py`, `test.py`, and `production.py`. Production fails closed without a strong secret and allowed hosts.
