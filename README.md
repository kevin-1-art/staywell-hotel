# Staywell Hotel Operations

A hotel operations system built with React, TypeScript, Vite, FastAPI, PostgreSQL, Alembic, JWT sessions, and Docker Compose. The demo seed creates 5 room types, 80 rooms, 200 guests, 300 reservations, folios/payments, and housekeeping tasks.

## Run locally

Requirements: Docker Compose, Node.js 22+ (for frontend development), and Python 3.12+ (for backend tests).

```powershell
Copy-Item .env.example .env
```

Before starting, replace the placeholder values in `.env`. Production requires unique `POSTGRES_PASSWORD`, `JWT_SECRET` (32+ characters), `SEED_USER_PASSWORD` (16+ characters with mixed case, a number, and a symbol), `PUBLIC_DOMAIN`, and a JSON `TRUSTED_HOSTS` list. Never publish `.env`.

```powershell
docker compose up --build
```

Open `https://<PUBLIC_DOMAIN>` after DNS for that domain points to the Docker host and ports 80/443 are reachable. Caddy obtains the TLS certificate. FastAPI OpenAPI docs are at `https://<PUBLIC_DOMAIN>/docs` and the health check is at `/health`.

In non-production local development, the seeded demo login is `admin@staywell.demo` / `Staywell-Demo-2026!`. Production seed accounts use `SEED_USER_PASSWORD`; all six initial roles share that bootstrap password. Sign in as Admin, set individual staff passwords, then rotate/remove the bootstrap secret. Do not reuse the demo password in production.

## Tests

Backend tests use an isolated SQLite database:

```powershell
python -m pip install -r backend/requirements.txt
python -m pytest -q -p no:cacheprovider
```

Frontend tests/build:

```powershell
cd frontend
npm ci
npm test
npm run build
```

## GitHub Pages

Pages serves only the static React frontend; FastAPI/PostgreSQL must be hosted separately. Configure the Pages site and API under the same custom domain family, for example `https://hotel.example.com` and `https://api.hotel.example.com`, so secure refresh cookies remain same-site.

Set the repository Actions variable `VITE_API_URL` to the HTTPS API origin. Set the API's `CORS_ORIGINS` to the exact Pages origin and `TRUSTED_HOSTS` to the API host. The workflow `.github/workflows/deploy-pages.yml` skips deployment if `VITE_API_URL` is missing. Full setup details are in [docs/github-pages.md](docs/github-pages.md).

## Security notes

The backend enforces role checks, request validation, hashed passwords, short-lived access JWTs, rotating/revocable refresh sessions, rate limits, audit records, trusted hosts, and API no-store/security headers. Inventory and staff deletion are audited archives, not destructive row deletion. See [SECURITY.md](SECURITY.md) for production requirements and remaining security limitations.

Security hardening is not a substitute for a deployment security review. This project does not include MFA/SSO, centralized alerting, managed WAF, or a tested backup/restore runbook. Docker runtime startup and public TLS were not verified in the development environment.
