# Frontend

Next.js App Router frontend for WIO Tracker.

## Responsibilities

- Email OTP login and authenticated user experience
- Daily work-log entry and status views
- Manager approval workflow
- Dashboards, reports, evidence, and seat selection

The frontend will use TypeScript, Tailwind CSS, daisyUI, React Hook Form, and Zod as described in [TECHSTACK.md](../TECHSTACK.md).

## Setup

```powershell
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Quality checks:

```powershell
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

Frontend uses credentialed requests to Django. Shared API helper gets a CSRF token from `/api/v1/auth/csrf/` before unsafe browser requests, then sends token and cookies. This supports separate frontend and API subdomains.

Tailwind CSS 4 and daisyUI 5 are configured in `src/app/globals.css`. UI must use daisyUI components and semantic colors before custom CSS.

Sentry captures unhandled browser, server, and edge exceptions when DSN variables are configured. Personal data collection remains disabled.
