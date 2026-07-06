# Docker Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the e-voting Django app deployable via Docker on a self-managed VPS, with all secrets/environment differences moved to env vars, Postgres instead of SQLite, and a shared reverse-proxy stack that future apps on the same VPS can reuse.

**Architecture:** A `web` (gunicorn) + `db` (postgres) compose stack for this app joins an externally-created `proxy-net` Docker network; a separate one-time `nginx-proxy` + `acme-companion` stack (also in this repo, under `infra/proxy-stack/`) handles routing and Let's Encrypt certs for any container on `proxy-net` that sets `VIRTUAL_HOST`/`LETSENCRYPT_HOST`.

**Tech Stack:** Django 3.1, gunicorn, whitenoise (already configured), PostgreSQL 16, psycopg2, dj-database-url (already in requirements.txt), Docker Compose, nginx-proxy + acme-companion.

## Global Constraints

- Local, non-Docker development must keep working: with `DATABASE_URL` unset, `settings.py` must fall back to the existing SQLite config exactly as today.
- No hardcoded secrets in source going forward (`SECRET_KEY`, superuser email/password, SMS creds all via env vars).
- `SEND_OTP` stays functionally bypassed by default (per user's explicit choice) but must be an env var, not a hardcoded `False`.
- Do not rewrite git history to purge the old hardcoded superuser password — out of scope; call out in the final summary that it should be treated as burned.
- Domain is not yet decided — use the placeholder `voting.example.com` everywhere a real domain would go (`.env.example`, this plan's verification steps).

---

### Task 1: Env-driven Django settings

**Files:**
- Modify: `e_voting/settings.py:23-32` (SECRET_KEY, DEBUG, ALLOWED_HOSTS)
- Modify: `e_voting/settings.py:90-109` (DATABASES)
- Modify: `e_voting/settings.py:192` (SEND_OTP)

**Interfaces:**
- Produces: `settings.SECRET_KEY`, `settings.DEBUG`, `settings.ALLOWED_HOSTS`, `settings.DATABASES`, `settings.SEND_OTP` — all env-driven, consumed by every later task (entrypoint.sh, docker-compose.yml, .env.example all set these exact env var names: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `SEND_OTP`).

- [ ] **Step 1: Replace the SECRET_KEY/DEBUG/ALLOWED_HOSTS block**

In `e_voting/settings.py`, replace lines 20-32:

```python
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# # SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY = os.environ.get("SECRETKEY")
SECRET_KEY = '%6lp_p!%r$7t-2ql5hc5(r@)8u_fc+6@ugxcnz=h=b(fn#3$p9'


# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG = os.environ.get("DEGUB", "False") == "True"

DEBUG = True
ALLOWED_HOSTS =  ["*"]#os.environ.get("ALLOWED_HOSTS", "").split(" ")
```

with:

```python
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ["SECRET_KEY"]

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]
```

- [ ] **Step 2: Replace the DATABASES block**

Replace lines 87-109 (the `# Database` comment through the closing `}` of the commented-out mysql block, and the two commented-out `database_url` lines that follow):

```python
# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    #   You can use this :
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }


    # 'default': {
    #     'ENGINE': 'django.db.backends.mysql',
    #     'NAME': 'e_votinßg',
    #     'HOST': '127.0.0.1',
    #     'USER': 'root',
    #     'PASSWORD': ''
    # }
}


# database_url = os.environ.get("DATABASE_URL")
# DATABASES['default'] = dj_database_url.parse(database_url)
```

with:

```python
# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(default=DATABASE_URL, conn_max_age=600)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
```

- [ ] **Step 3: Make SEND_OTP env-driven**

Replace line 192:

```python
SEND_OTP = False  # If you toggle this to False, Kindly use 0000 as your OTP
```

with:

```python
SEND_OTP = os.environ.get("SEND_OTP", "False") == "True"  # Default bypassed (fixed 0000 OTP); set SEND_OTP=True + SMS_EMAIL/SMS_PASSWORD to enforce real SMS OTP
```

- [ ] **Step 4: Verify the SQLite fallback path (no DATABASE_URL set)**

Run:
```bash
SECRET_KEY=test-key python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'], settings.DEBUG, settings.ALLOWED_HOSTS, settings.SEND_OTP)"
```
Expected output: `django.db.backends.sqlite3 False [] False`

- [ ] **Step 5: Verify the DATABASE_URL path parses to Postgres (no live DB needed — dj_database_url only parses the URL)**

Run:
```bash
SECRET_KEY=test-key DATABASE_URL=postgres://voting:pw@localhost:5432/voting DEBUG=True ALLOWED_HOSTS=voting.example.com SEND_OTP=True python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'], settings.DEBUG, settings.ALLOWED_HOSTS, settings.SEND_OTP)"
```
Expected output: `django.db.backends.postgresql True ['voting.example.com'] True`

- [ ] **Step 6: Verify missing SECRET_KEY fails loudly**

Run:
```bash
unset SECRET_KEY; python manage.py check
```
Expected: `KeyError: 'SECRET_KEY'` traceback (confirms there's no silent fallback to the old hardcoded key).

- [ ] **Step 7: Commit**

```bash
git add e_voting/settings.py
git commit -m "Move SECRET_KEY, DEBUG, ALLOWED_HOSTS, DATABASE_URL and SEND_OTP to env vars"
```

---

### Task 2: Env-driven, idempotent superuser creation

**Files:**
- Modify: `script/create_superuser.py` (entire file)

**Interfaces:**
- Consumes: `settings.DATABASES` from Task 1 (script runs against whatever DB `DATABASE_URL`/fallback resolves to).
- Produces: reads env vars `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`, `DJANGO_SUPERUSER_FIRST_NAME` (optional), `DJANGO_SUPERUSER_LAST_NAME` (optional) — these exact names are what `entrypoint.sh` (Task 3) and `.env.example` (Task 5) must set.

- [ ] **Step 1: Rewrite the script**

Replace the entire contents of `script/create_superuser.py`:

```python
#!/usr/bin/env python

import os
import sys
import django

# Add project root to Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.append(PROJECT_ROOT)

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e_voting.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

if not email or not password:
    print("ℹ️ DJANGO_SUPERUSER_EMAIL/DJANGO_SUPERUSER_PASSWORD not set, skipping superuser creation.")
elif User.objects.filter(email=email).exists():
    print("ℹ️ Superuser already exists.")
else:
    User.objects.create_superuser(
        email=email,
        password=password,
        first_name=os.environ.get("DJANGO_SUPERUSER_FIRST_NAME", "Admin"),
        last_name=os.environ.get("DJANGO_SUPERUSER_LAST_NAME", "User"),
        is_staff=True,
        is_superuser=True,
    )
    print("✅ Superuser created.")
```

- [ ] **Step 2: Verify the no-op path (env vars unset)**

Run:
```bash
SECRET_KEY=test-key unset DJANGO_SUPERUSER_EMAIL DJANGO_SUPERUSER_PASSWORD; python script/create_superuser.py
```
Expected output: `ℹ️ DJANGO_SUPERUSER_EMAIL/DJANGO_SUPERUSER_PASSWORD not set, skipping superuser creation.`

- [ ] **Step 3: Verify creation + idempotency against a throwaway SQLite DB**

Run:
```bash
export SECRET_KEY=test-key
export DATABASE_URL=sqlite:////tmp/plan_test.sqlite3
python manage.py migrate --noinput
export DJANGO_SUPERUSER_EMAIL=planverify@example.com
export DJANGO_SUPERUSER_PASSWORD=Testpass123!
python script/create_superuser.py
python script/create_superuser.py
rm -f /tmp/plan_test.sqlite3
```
Expected output: first run prints `✅ Superuser created.`, second run prints `ℹ️ Superuser already exists.`

- [ ] **Step 4: Commit**

```bash
git add script/create_superuser.py
git commit -m "Make superuser creation env-driven instead of hardcoded credentials"
```

---

### Task 3: entrypoint.sh (replaces build.sh)

**Files:**
- Create: `entrypoint.sh`
- Delete: `build.sh`

**Interfaces:**
- Consumes: `DATABASE_URL` env var (to know whether/what to wait for), `script/create_superuser.py` from Task 2.
- Produces: the container's startup sequence — `Dockerfile` (Task 4) sets `ENTRYPOINT ["./entrypoint.sh"]`.

- [ ] **Step 1: Create entrypoint.sh**

```bash
#!/usr/bin/env bash
set -o errexit

if [ -n "$DATABASE_URL" ]; then
  echo "Waiting for database..."
  python - <<'PYEOF'
import os
import socket
import sys
import time
import urllib.parse

parsed = urllib.parse.urlparse(os.environ["DATABASE_URL"])
host = parsed.hostname
port = parsed.port or 5432

for _ in range(30):
    try:
        with socket.create_connection((host, port), timeout=1):
            sys.exit(0)
    except OSError:
        time.sleep(1)
sys.exit("Database did not become available in time")
PYEOF
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python script/create_superuser.py

exec gunicorn e_voting.wsgi:application --bind 0.0.0.0:8000
```

- [ ] **Step 2: Make it executable and delete build.sh**

```bash
chmod +x entrypoint.sh
git rm build.sh
```

- [ ] **Step 3: Verify script syntax**

Run:
```bash
bash -n entrypoint.sh
```
Expected: no output (exit code 0).

- [ ] **Step 4: Commit**

```bash
git add entrypoint.sh
git commit -m "Add entrypoint.sh for Docker startup, remove Render-style build.sh"
```

---

### Task 4: Dockerfile + .dockerignore

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `entrypoint.sh` from Task 3, `requirements.txt` (existing, unchanged).
- Produces: a buildable image tagged by `docker compose build` in Task 5.

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# media/ is excluded from the build context (.dockerignore) since it's
# volume-mounted at runtime; create it here, owned by appuser, so Docker's
# first-run volume initialization inherits correct ownership instead of root.
RUN mkdir -p media staticfiles \
    && chmod +x entrypoint.sh \
    && useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
```

- [ ] **Step 2: Create .dockerignore**

```
.git
.gitignore
.vscode
__pycache__
*.pyc
db.sqlite3
db.sqlite3-journal
staticfiles/
media/
.env
docs/
```

- [ ] **Step 3: Verify the image builds**

Run:
```bash
docker build -t voting-web-test .
```
Expected: build completes with `Successfully tagged voting-web-test:latest` (or the final `naming to docker.io/library/voting-web-test` line on newer Docker), no errors.

- [ ] **Step 4: Clean up the test image and commit**

```bash
docker rmi voting-web-test
git add Dockerfile .dockerignore
git commit -m "Add Dockerfile and .dockerignore for containerized deployment"
```

---

### Task 5: docker-compose.yml + .env.example

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`

**Interfaces:**
- Consumes: `Dockerfile` (Task 4), env var names from Tasks 1-2 (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, `SEND_OTP`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`), plus `SMS_EMAIL`/`SMS_PASSWORD` (already read by `voting/views.py`, unchanged).
- Produces: external network reference `proxy-net`, which Task 6's `infra/proxy-stack/docker-compose.yml` creates.

- [ ] **Step 1: Create docker-compose.yml**

```yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-voting}
      POSTGRES_USER: ${POSTGRES_USER:-voting}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  web:
    build: .
    restart: unless-stopped
    env_file: .env
    environment:
      DATABASE_URL: postgres://${POSTGRES_USER:-voting}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-voting}
      VIRTUAL_HOST: ${VIRTUAL_HOST}
      LETSENCRYPT_HOST: ${LETSENCRYPT_HOST}
      LETSENCRYPT_EMAIL: ${LETSENCRYPT_EMAIL}
    volumes:
      - media_data:/app/media
    depends_on:
      - db
    networks:
      - default
      - proxy-net

networks:
  proxy-net:
    external: true

volumes:
  postgres_data:
  media_data:
```

- [ ] **Step 2: Create .env.example**

```
# Django
SECRET_KEY=change-me-to-a-random-secret
DEBUG=False
ALLOWED_HOSTS=voting.example.com

# Database (composed into DATABASE_URL by docker-compose.yml)
POSTGRES_DB=voting
POSTGRES_USER=voting
POSTGRES_PASSWORD=change-me

# Initial admin account (idempotent - only created if missing)
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=change-me

# SMS OTP (multitexter.com) - leave SEND_OTP=False to bypass with a fixed 0000 OTP
SEND_OTP=False
SMS_EMAIL=
SMS_PASSWORD=

# Reverse proxy / HTTPS (nginx-proxy + acme-companion, see infra/proxy-stack/)
VIRTUAL_HOST=voting.example.com
LETSENCRYPT_HOST=voting.example.com
LETSENCRYPT_EMAIL=you@example.com
```

- [ ] **Step 3: Verify .env is gitignored (it already should be)**

Run:
```bash
git check-ignore -v .env || echo "NOT IGNORED"
```
Expected: prints the matching `.gitignore` line and number (e.g. `.gitignore:123:.env	.env`), not `NOT IGNORED`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "Add docker-compose.yml and .env.example for the app stack"
```

---

### Task 6: Shared reverse-proxy stack (infra/proxy-stack)

**Files:**
- Create: `infra/proxy-stack/docker-compose.yml`
- Create: `infra/proxy-stack/README.md`

**Interfaces:**
- Produces: the external `proxy-net` Docker network and running `nginx-proxy`/`acme-companion` containers that Task 5's `docker-compose.yml` depends on.

- [ ] **Step 1: Create infra/proxy-stack/docker-compose.yml**

```yaml
services:
  nginx-proxy:
    image: nginxproxy/nginx-proxy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - conf:/etc/nginx/conf.d
      - vhost:/etc/nginx/vhost.d
      - html:/usr/share/nginx/html
      - certs:/etc/nginx/certs:ro
      - /var/run/docker.sock:/tmp/docker.sock:ro
    networks:
      - proxy-net

  acme-companion:
    image: nginxproxy/acme-companion
    restart: unless-stopped
    volumes_from:
      - nginx-proxy
    volumes:
      - certs:/etc/nginx/certs
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - proxy-net

networks:
  proxy-net:
    external: true

volumes:
  conf:
  vhost:
  html:
  certs:
```

- [ ] **Step 2: Create infra/proxy-stack/README.md**

```markdown
# Shared reverse-proxy stack

One-time host-wide setup. Run once per VPS, not per app. Any app that
joins the `proxy-net` network and sets `VIRTUAL_HOST`/`LETSENCRYPT_HOST`/
`LETSENCRYPT_EMAIL` env vars on its web container gets HTTP routing and a
Let's Encrypt certificate automatically, with no changes needed here.

## First-time setup on a new VPS

    docker network create proxy-net
    cd infra/proxy-stack
    docker compose up -d

## Adding a new app later

1. Make sure the app's compose file declares `proxy-net` as an
   `external: true` network and its web service joins it.
2. Set `VIRTUAL_HOST`, `LETSENCRYPT_HOST`, and `LETSENCRYPT_EMAIL` in that
   app's `.env`.
3. `docker compose up -d` the app. `nginx-proxy` and `acme-companion` will
   pick it up automatically within a few seconds — no restart of this
   stack required.

## Verifying certs

    docker compose logs acme-companion
```

- [ ] **Step 3: Verify compose file syntax**

Run:
```bash
docker compose -f infra/proxy-stack/docker-compose.yml config -q
```
Expected: no output, exit code 0 (this validates YAML/schema without requiring `proxy-net` to exist, since `config -q` doesn't start containers).

- [ ] **Step 4: Commit**

```bash
git add infra/proxy-stack/docker-compose.yml infra/proxy-stack/README.md
git commit -m "Add shared nginx-proxy + acme-companion stack for multi-app HTTPS routing"
```

---

### Task 7: End-to-end local verification

**Files:**
- None created/modified — this task only runs and observes the stack built in Tasks 1-6.

**Interfaces:**
- Consumes: everything from Tasks 1-6.

- [ ] **Step 1: Create a local .env from the example**

```bash
cp .env.example .env
```
Edit `.env` and set real throwaway values for local testing, e.g.:
```
SECRET_KEY=local-test-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost
POSTGRES_PASSWORD=localtestpw
DJANGO_SUPERUSER_EMAIL=localadmin@example.com
DJANGO_SUPERUSER_PASSWORD=Localtestpw123!
VIRTUAL_HOST=voting.example.com
LETSENCRYPT_HOST=voting.example.com
LETSENCRYPT_EMAIL=you@example.com
```

- [ ] **Step 2: Create the external network locally (normally done once per VPS by Task 6)**

```bash
docker network create proxy-net
```
Expected: prints a network ID (or `Error response from daemon: network with name proxy-net already exists` if already created — either is fine).

- [ ] **Step 3: Build and start the app stack**

```bash
docker compose up -d --build
```
Expected: both `db` and `web` report `Started`/`Running`.

- [ ] **Step 4: Check the web container's startup log**

```bash
docker compose logs web
```
Expected: contains `Waiting for database...`, `Operations to perform:` / `Applying voting.0001_initial... OK` (migrate output), `Superuser created.` (first run) or `Superuser already exists.`, and gunicorn's `Listening at: http://0.0.0.0:8000`.

- [ ] **Step 5: Hit the login page from inside the container**

```bash
docker compose exec web python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/').getcode())"
```
Expected output: `200`

- [ ] **Step 6: Verify the superuser account exists in Postgres**

```bash
docker compose exec web python manage.py shell -c "from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(email='localadmin@example.com').exists())"
```
Expected output: `True`

- [ ] **Step 7: Regression check — non-Docker local dev still works via SQLite**

```bash
docker compose down
unset DATABASE_URL
SECRET_KEY=dev-key DEBUG=True python manage.py migrate --noinput
SECRET_KEY=dev-key DEBUG=True python manage.py runserver 127.0.0.1:8766 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" -L http://127.0.0.1:8766/
kill %1
```
Expected output: `200`

- [ ] **Step 8: Clean up local test artifacts**

```bash
docker compose down -v
rm -f db.sqlite3
```

- [ ] **Step 9: No commit for this task** — it's a verification pass only; if any step fails, fix the relevant file from Tasks 1-6 and re-run the failing step, then commit the fix in that task's context.

---

## Post-plan notes (not part of any task, for the final rollout on the actual VPS)

- The old hardcoded superuser password from before Task 2 is already in git history — treat it as burned, don't reuse it as `DJANGO_SUPERUSER_PASSWORD`.
- On the real VPS: set the real domain in `.env` (`ALLOWED_HOSTS`, `VIRTUAL_HOST`, `LETSENCRYPT_HOST`) before first deploy, and point DNS (DNSExit) at the VPS's IP first so Let's Encrypt's HTTP-01 challenge can succeed.
- Deploys are manual: `git pull && docker compose up -d --build` in the app directory (no CI/CD configured, per scope).
