# GitHub Pages Deployment

GitHub Pages can host the React frontend only. It cannot run FastAPI or PostgreSQL. The public Pages UI is functional only when `VITE_API_URL` points to a separately deployed HTTPS API.

## Recommended secure layout

Use a custom domain for both hosts under the same registrable domain:

- Pages: `https://hotel.example.com`
- API: `https://api.hotel.example.com`

The shared HTTPS site makes the API's `Secure; SameSite=Strict` refresh cookie first-party/same-site. A default `*.github.io` Pages hostname calling an unrelated API host can be treated as a third-party cookie and break refresh login. Do not weaken cookie security to work around that browser policy.

## Configure GitHub

1. Create/select the target GitHub repository and push this source to its `main` branch.
2. In repository **Settings → Pages**, select **GitHub Actions** as the build/deploy source. Configure the custom Pages domain and its DNS records there.
3. In **Settings → Secrets and variables → Actions → Variables**, add `VITE_API_URL` with the API origin only, for example `https://api.hotel.example.com`. This is a public URL, not a secret.
4. The `Deploy frontend to GitHub Pages` workflow runs on pushes to `main` or can be started with `workflow_dispatch`. It skips deployment when `VITE_API_URL` is missing, instead of publishing a login screen that cannot reach an API. After configuring the variable, run the workflow from the Actions tab.

## Configure the API host

Deploy the backend with Docker Compose on a public host whose DNS name matches `VITE_API_URL`. Set the host `.env` values:

- `PUBLIC_DOMAIN=api.hotel.example.com`
- `TRUSTED_HOSTS=["api.hotel.example.com"]`
- `CORS_ORIGINS=["https://hotel.example.com"]`
- `APP_ENV=production`
- `JWT_SECRET` to a unique random value of at least 32 characters
- `SEED_USER_PASSWORD` to a unique strong bootstrap password
- `POSTGRES_PASSWORD` to a unique database password

Keep `.env` out of Git. Set DNS for the API host to the Docker server; Caddy obtains and renews its HTTPS certificate. Confirm the API `/health` and `/docs` endpoints work before setting `VITE_API_URL`.

## Important

Do not publish the seeded demo password as production credentials. All seeded roles initially share `SEED_USER_PASSWORD`; sign in as Admin after first deployment, set individual staff passwords, and rotate/remove the bootstrap secret. Back up PostgreSQL before real hotel data is entered.
