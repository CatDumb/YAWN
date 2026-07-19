# Infrastructure

Infrastructure and deployment support for WIO Tracker.

## Responsibilities

- Docker and Docker Compose configuration
- Local PostgreSQL and optional Redis services
- Deployment configuration for frontend and backend hosting
- Environment and operational configuration

Persistent production data will remain in managed PostgreSQL and private S3-compatible object storage, not container filesystems.

## Local Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Optional Redis:

```powershell
docker compose --profile redis up --build
```

## Deployment setup

GitHub variable `DEPLOYMENTS_ENABLED=true` enables deploy jobs. Configure staging and production GitHub Environments with:

- Secrets: `RENDER_DEPLOY_HOOK_URL`, `VERCEL_DEPLOY_HOOK_URL`
- Staging variables: `STAGING_API_URL`, `STAGING_FRONTEND_URL`
- Production variables: `PRODUCTION_API_URL`, `PRODUCTION_FRONTEND_URL`
- Monitoring variables: `STAGING_SENTRY_DSN`, `PRODUCTION_SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`

Production Environment must require reviewer approval. Render service must run `python manage.py migrate --noinput` as pre-deploy command before new image starts.

Set `WIO_TRUST_PROXY_HEADERS=true` only when hosting proxy strips client-supplied forwarding headers and supplies its own trusted `X-Forwarded-For` value.

Use same-site custom domains, such as `app.example.com` and `api.example.com`, for session cookies. If provider domains remain cross-site, set cookie SameSite to `None`, keep secure cookies enabled, and test CSRF/CORS explicitly.
