# Infrastructure

Infrastructure and deployment support for YAWN.

## Responsibilities

- Docker and Docker Compose configuration
- Local PostgreSQL and optional Redis services
- Deployment configuration for frontend and backend hosting
- Environment and operational configuration

Persistent production data will remain in managed PostgreSQL and private S3-compatible object storage, not container filesystems.

## Local Compose

Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-app.ps1
```

Optional Redis:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-app.ps1 -WithRedis
```

## Deployment setup

Configure backend deployment secrets with Gmail SMTP values from YAWN's dedicated Gmail account:

- Enable Google 2-Step Verification and create an App Password. Never commit App Password.
- `DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `DJANGO_EMAIL_HOST=smtp.gmail.com`, `DJANGO_EMAIL_PORT=587`, and `DJANGO_EMAIL_USE_TLS=true`
- `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`, and matching `DJANGO_DEFAULT_FROM_EMAIL`
- HTTPS frontend homepage `WIO_APP_URL`, for example `https://app.example.com`

Production fails startup if SMTP host, port, credentials, TLS, sender, or `WIO_APP_URL` is absent
or invalid. Compose reads root ignored `.env`, using console mail unless its SMTP values replace the
defaults in `.env.example`; `backend/.env` affects only direct Django processes. Recreate `backend`
and `cleanup` after changing Compose mail values. Deploy the Compose stack with production settings
and host secrets. Its `cleanup` service waits for database/backend health, then runs
`purge_expired_otps --hours 24` and `clearsessions` every 24 hours.

Release test: submit public request, approve in Admin, receive approval email, open homepage,
request Gmail OTP, verify frontend session, wait 30 seconds, resend, then confirm logout and login
behavior.

GitHub variable `DEPLOYMENTS_ENABLED=true` enables deploy jobs. Configure staging and production GitHub Environments with:

- Secrets: `RENDER_DEPLOY_HOOK_URL`, `VERCEL_DEPLOY_HOOK_URL`
- Staging variables: `STAGING_API_URL`, `STAGING_FRONTEND_URL`
- Production variables: `PRODUCTION_API_URL`, `PRODUCTION_FRONTEND_URL`
- Monitoring variables: `STAGING_SENTRY_DSN`, `PRODUCTION_SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`

Production Environment must require reviewer approval. Render service must run `python manage.py migrate --noinput` as pre-deploy command before new image starts.

Set `WIO_TRUST_PROXY_HEADERS=true` only when hosting proxy strips client-supplied forwarding headers and supplies its own trusted `X-Forwarded-For` value.

Use same-site custom domains, such as `app.example.com` and `api.example.com`, for session cookies. If provider domains remain cross-site, set cookie SameSite to `None`, keep secure cookies enabled, and test CSRF/CORS explicitly.
