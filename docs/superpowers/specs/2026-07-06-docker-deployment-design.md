# Docker Deployment Design — E-Voting App

Date: 2026-07-06

## Context

The e-voting Django app currently has no working deployment path:
- `SECRET_KEY` is hardcoded and committed to git.
- `DEBUG = True` is hardcoded.
- `ALLOWED_HOSTS = ["*"]` is wide open.
- The database is hardcoded to SQLite even though `dj-database-url` and a
  commented-out `DATABASE_URL` block already exist in `settings.py`.
- `script/create_superuser.py` hardcodes a real admin email + password in
  source, and `build.sh` runs it on every deploy.
- `build.sh` targets a Render-style build command flow; `.vscode/settings.json`
  points at an Azure App Service; neither has a real, working entrypoint
  config. No Dockerfile exists despite a comment in `build.sh` claiming to
  "build the Docker image."

The user is deploying to a self-managed VPS (VPSDime) with a domain from
DNSExit, and intends to host **other apps on the same server** going forward.
This design covers making the app deployable via Docker on that VPS in a way
that scales to multiple apps without per-app proxy reconfiguration.

## Goals

- Containerize the Django app (gunicorn) and move all secrets/environment
  differences (secret key, debug, hosts, DB, superuser, SMS creds, OTP
  enforcement) to environment variables.
- Use PostgreSQL (containerized) instead of SQLite for correct concurrent
  write behavior under real voter load.
- Set up HTTPS + routing via a **shared** reverse-proxy stack
  (`nginx-proxy` + `acme-companion`) so future apps on this VPS only need to
  join a Docker network and set two env vars — no proxy config edits.
- Make initial admin account creation idempotent and env-driven, never
  hardcoded in source again.
- Keep local (non-Docker) development working exactly as it does today —
  `DATABASE_URL` unset should fall back to the existing SQLite path.

## Non-goals

- No CI/CD pipeline (deploys are manual `git pull && docker compose up -d --build` on the VPS).
- Not rewriting git history to purge the old hardcoded superuser
  credentials — that password should simply be treated as burned and
  rotated. Rewriting shared git history is out of scope unless explicitly
  requested later.
- Not enabling real OTP/SMS enforcement — `SEND_OTP` stays functionally
  bypassed by default (user's explicit choice), but becomes an env var so it
  can be flipped later without a code change.
- Not changing the domain/subdomain now — `.env.example` uses a placeholder
  (`voting.example.com`) that gets swapped in on the VPS before first
  deploy.

## Architecture

Two independent Docker Compose stacks on the VPS:

1. **Shared infra stack** (`infra/proxy-stack/docker-compose.yml`, set up
   once on the VPS, not tied to this app's lifecycle):
   - `nginx-proxy` — watches Docker events, auto-generates nginx config for
     any container with a `VIRTUAL_HOST` env var on the shared network.
   - `acme-companion` — watches for `LETSENCRYPT_HOST`/`LETSENCRYPT_EMAIL`
     env vars and provisions/renews Let's Encrypt certs automatically.
   - Both attach to an external Docker network, `proxy-net`, created once
     (`docker network create proxy-net`).
   - Any future app on this VPS joins `proxy-net` and sets those two env
     vars to get routing + HTTPS with zero proxy-side changes.

2. **This app's stack** (`docker-compose.yml` in the repo root):
   - `web` — built from this repo's `Dockerfile`; runs gunicorn behind the
     shared proxy. Joins `proxy-net` (external) for inbound routing and the
     default compose network to reach `db`. Env vars include
     `VIRTUAL_HOST`/`LETSENCRYPT_HOST`/`LETSENCRYPT_EMAIL` so the shared
     proxy picks it up automatically.
   - `db` — `postgres:16`, named volume `postgres_data`, not exposed to the
     host, only reachable from `web`.
   - Named volume for `media/` (candidate photos, etc.) so uploads survive
     container rebuilds/redeploys.
   - Static files continue to be served by WhiteNoise from inside the `web`
     container (already configured in `settings.py`); the shared proxy just
     forwards all traffic to `web`, it does not need its own static config.

## Application changes

### `e_voting/settings.py`

All previously hardcoded/hedged values become env-driven, with fallbacks
that preserve today's local dev experience when running outside Docker:

- `SECRET_KEY` — `os.environ["SECRET_KEY"]`, no fallback. Fails loudly if
  unset (forces the operator to set it before the container will start).
- `DEBUG` — `os.environ.get("DEBUG", "False") == "True"`.
- `ALLOWED_HOSTS` — `os.environ.get("ALLOWED_HOSTS", "").split(",")`.
- `DATABASES["default"]` — if `DATABASE_URL` is set, use
  `dj_database_url.config(conn_max_age=600)`; otherwise fall back to the
  existing SQLite block. This keeps `python manage.py runserver` working
  untouched for anyone developing without Docker.
- `SEND_OTP` — `os.environ.get("SEND_OTP", "False") == "True"`.
- No changes needed to `voting/views.py`'s `send_sms()` — it already reads
  `SMS_EMAIL`/`SMS_PASSWORD` from env.

### `script/create_superuser.py`

Rewritten to:
- Read `DJANGO_SUPERUSER_EMAIL` and `DJANGO_SUPERUSER_PASSWORD` from env.
- No-op (log and exit 0) if either is unset — never falls back to a
  hardcoded credential.
- Remain idempotent: only creates the account if a user with that email
  doesn't already exist (existing behavior, kept).

### `build.sh`

Removed. Its responsibilities (`pip install`, `collectstatic`, `migrate`,
superuser bootstrap) move into `entrypoint.sh`, run at container start
instead of at a separate "build" step, which is the correct place for them
in a Docker deployment (migrations must run against the actual runtime DB,
not at image-build time).

## New files

- **`Dockerfile`** — `python:3.12-slim` base, installs `requirements.txt`,
  copies the project, creates a non-root user, sets
  `ENTRYPOINT ["./entrypoint.sh"]`.
- **`entrypoint.sh`** — waits for Postgres to accept TCP connections, then
  runs `manage.py migrate`, `manage.py collectstatic --noinput`,
  `script/create_superuser.py`, then `exec gunicorn
  e_voting.wsgi:application --bind 0.0.0.0:8000`.
- **`docker-compose.yml`** — `web` + `db` services as described in
  Architecture above, `env_file: .env`.
- **`.env.example`** — documents every variable needed:
  `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL` (or discrete
  `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD` vars composed into a
  `DATABASE_URL` inside compose), `DJANGO_SUPERUSER_EMAIL`,
  `DJANGO_SUPERUSER_PASSWORD`, `SMS_EMAIL`, `SMS_PASSWORD`, `SEND_OTP`,
  `VIRTUAL_HOST`, `LETSENCRYPT_HOST`, `LETSENCRYPT_EMAIL`.
- **`.dockerignore`** — excludes `.git`, `staticfiles/`, `media/`,
  `__pycache__`, `db.sqlite3`, `.env`.
- **`infra/proxy-stack/docker-compose.yml`** — the one-time shared
  `nginx-proxy` + `acme-companion` stack, plus a short README section
  documenting the one-time `docker network create proxy-net` setup step.

## Security notes carried forward

- The previously-committed hardcoded superuser password is already in git
  history. This design does not purge history; the recommendation is to
  treat that password as compromised and not reuse it as the new
  `DJANGO_SUPERUSER_PASSWORD`.
- `.env` (real secrets) is already covered by the existing `.gitignore`
  entry — verified present, no change needed there.

## Testing / rollout plan

1. Local verification (no VPS needed): `docker compose build`, `docker
   compose up`, confirm `web` waits for `db`, migrates, and serves the login
   page on `localhost` with `DEBUG=True` in a local `.env`.
2. Confirm `DATABASE_URL` unset + no Docker still runs via
   `python manage.py runserver` against SQLite (regression check for
   existing local dev workflow).
3. On the VPS: create `proxy-net`, bring up the shared proxy stack once,
   then bring up this app's stack with the real domain and
   `LETSENCRYPT_EMAIL` set, verify cert issuance in `acme-companion` logs
   and HTTPS access via the real domain.
4. Confirm superuser login works using the new env-driven credentials.
