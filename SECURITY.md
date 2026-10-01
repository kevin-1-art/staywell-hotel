# Security Operations

## Production configuration

Do not use development defaults in a public deployment. Copy `.env.example` to `.env`, then set unique values for `POSTGRES_PASSWORD` and `JWT_SECRET`. Generate a JWT secret with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set `APP_ENV=production`, `COOKIE_SECURE=true`, `PUBLIC_DOMAIN` to the DNS name serving the property, `TRUSTED_HOSTS` to a JSON array containing that host, and `CORS_ORIGINS` to a JSON array of the exact permitted browser origins. Point DNS at the host and allow inbound TCP 80/443 for Caddy certificate provisioning. Production startup rejects missing/placeholder JWT secrets, wildcard trusted hosts, and forces secure refresh cookies.

Set `SEED_USER_PASSWORD` to a unique strong bootstrap password before the first production start. All initial role accounts share this value; sign in as Admin, set individual passwords for staff, and rotate/remove the bootstrap value immediately after initial provisioning. Never reuse the development/demo password in production.

Keep `.env` out of source control. Rotate database and signing secrets if exposed; changing `JWT_SECRET` invalidates all outstanding JWTs. Use a unique secret per environment.

## Application controls

- Passwords are Argon2-hashed; access JWTs are short-lived and refresh JWT identifiers are stored as hashes, rotated on refresh, and revoked on logout or account changes.
- Login requests are rate-limited. API routes enforce role authorization on the server; hiding a UI control is not an authorization boundary.
- Admin staff edits, account archives, checkout overrides, payments/refunds, inventory archives, and operational events write audit records.
- Staff accounts and inventory records are archived rather than hard-deleted so historical foreign keys and audit trails remain intact.
- API inputs use Pydantic validation and SQLAlchemy bound queries. Private API responses use `Cache-Control: no-store`.
- The API validates Host headers, restricts CORS to configured origins, and emits no-sniff, frame, referrer, and permissions headers. Nginx/Caddy add browser security policy headers and TLS.
- The API and database are not published as host ports in Compose. Containers drop unnecessary capabilities, use `no-new-privileges`, and the API/proxy filesystems are read-only where supported.

## Operational limits

This baseline does not include MFA, SSO, automated secret rotation, a managed WAF, centralized alerting, or a tested backup/restore runbook. Configure encrypted off-host backups, monitor audit/security logs, patch base images and dependencies, and perform a deployment review before handling real guest/payment data. Payment-card details are not stored; integrate a PCI-compliant payment provider instead of collecting card numbers in this application.
