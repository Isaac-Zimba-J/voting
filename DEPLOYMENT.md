# Deployment Guide — Two Instances (Two Associations)

This walks through running **two independent instances** of this app on one
VPS — e.g. `assoc1.yourdomain.com` for one student association and
`assoc2.yourdomain.com` for another. Each instance has its own database, its
own admin, its own candidates/positions — completely isolated — but they
share one VPS and one reverse-proxy stack.

**DNS (Step 8) is deliberately last.** Everything through Step 7 gets both
instances fully built, running, and reachable — you can verify the whole
app works before DNSExit is available to you. Only the real
`https://assoc1.yourdomain.com` URL and a trusted cert depend on DNS; until
then you verify over plain HTTP against the VPS's IP directly.

Replace `assoc1`/`assoc2` and `yourdomain.com` with the real subdomains
throughout. Every command block is meant to be run as shown, in order.

---

## Step 1 — Push this repo to GitHub

From your local machine, in this repo:

```bash
git push origin main
```

(If this is the first push of these commits, `git push -u origin main` sets
up tracking. If you get a non-fast-forward error, `git pull --rebase origin
main` first, resolve anything, then push again.)

---

## Step 2 — One-time VPS setup

SSH into the VPS, then:

```bash
# Install Docker if not already present
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out/in once for this to take effect

# Confirm
docker --version
docker compose version
```

Pick a place to keep both checkouts, e.g.:

```bash
mkdir -p ~/apps
cd ~/apps
```

Note the VPS's public IP now — you'll need it both for verification below
and for the DNS records at the end:

```bash
curl -4 ifconfig.me
```

---

## Step 3 — Clone the app twice, once per association

```bash
cd ~/apps
git clone https://github.com/Isaac-Zimba-J/voting.git voting-assoc1
git clone https://github.com/Isaac-Zimba-J/voting.git voting-assoc2
```

Two separate directories, two separate git checkouts of the same code. This
is what gives you two separate `docker compose` projects later — Compose
namespaces containers/volumes by the containing directory name, so
`voting-assoc1` and `voting-assoc2` can never collide.

---

## Step 4 — Start the shared reverse-proxy stack (once, not per-instance)

This doesn't need DNS to start — it just needs to be listening on ports
80/443:

```bash
cd ~/apps/voting-assoc1   # either checkout works, the proxy stack isn't app-specific
docker network create proxy-net
cd infra/proxy-stack
docker compose up -d
cd ~/apps
```

Confirm it's running:

```bash
docker compose -f ~/apps/voting-assoc1/infra/proxy-stack/docker-compose.yml ps
```

You should see `nginx-proxy` and `acme-companion` both `Up`. Leave this
running permanently — you will never restart it just to deploy an app.
`acme-companion` will sit idle until Step 8, since it has no cert to request
yet — that's expected, not an error.

---

## Step 5 — Configure and deploy Instance 1 (assoc1)

```bash
cd ~/apps/voting-assoc1
cp .env.example .env
```

Edit `.env`, filling in real values now — including the intended final
domain, even though it doesn't resolve yet — (do **not** reuse any
example/placeholder value, and do **not** reuse the same values across the
two instances):

```env
SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_urlsafe(50))">
DEBUG=False
ALLOWED_HOSTS=assoc1.yourdomain.com

POSTGRES_DB=voting_assoc1
POSTGRES_USER=voting_assoc1
POSTGRES_PASSWORD=<pick a strong, unique password>

DJANGO_SUPERUSER_EMAIL=<assoc1's admin email>
DJANGO_SUPERUSER_PASSWORD=<pick a strong, unique password — never reuse the old hardcoded one from git history>

SEND_OTP=False
SMS_EMAIL=
SMS_PASSWORD=

VIRTUAL_HOST=assoc1.yourdomain.com
LETSENCRYPT_HOST=assoc1.yourdomain.com
LETSENCRYPT_EMAIL=<a real email you monitor — Let's Encrypt sends expiry notices here>

CSRF_TRUSTED_ORIGINS=https://assoc1.yourdomain.com
```

Verify `.env` isn't tracked by git, then deploy:

```bash
git check-ignore -v .env      # should print a match
docker compose up -d --build
```

Watch it come up:

```bash
docker compose logs -f web
```

Expect, in order: `Waiting for database...` → migration output ending in
`Applying voting.0001_initial... OK` → `Superuser created.` → gunicorn's
`Listening at: http://0.0.0.0:8000`. Ctrl-C to stop following once you see
that.

---

## Step 6 — Configure and deploy Instance 2 (assoc2)

Same as Step 5, in the other directory, with assoc2's own values:

```bash
cd ~/apps/voting-assoc2
cp .env.example .env
```

```env
SECRET_KEY=<a different fresh secret than assoc1's>
DEBUG=False
ALLOWED_HOSTS=assoc2.yourdomain.com

POSTGRES_DB=voting_assoc2
POSTGRES_USER=voting_assoc2
POSTGRES_PASSWORD=<a different strong password than assoc1's>

DJANGO_SUPERUSER_EMAIL=<assoc2's admin email>
DJANGO_SUPERUSER_PASSWORD=<a different strong password than assoc1's>

SEND_OTP=False
SMS_EMAIL=
SMS_PASSWORD=

VIRTUAL_HOST=assoc2.yourdomain.com
LETSENCRYPT_HOST=assoc2.yourdomain.com
LETSENCRYPT_EMAIL=<a real email you monitor>

CSRF_TRUSTED_ORIGINS=https://assoc2.yourdomain.com
```

```bash
git check-ignore -v .env
docker compose up -d --build
docker compose logs -f web
```

Same expected startup sequence as Step 5.

---

## Step 7 — Verify both instances *before* DNS exists

`nginx-proxy` routes by the `Host` header it receives, not by real DNS
resolution — so you can fully exercise both apps right now by sending that
header yourself against the VPS's IP on plain HTTP:

```bash
docker compose -f ~/apps/voting-assoc1/docker-compose.yml ps
docker compose -f ~/apps/voting-assoc2/docker-compose.yml ps
```

Both should show their `web`/`db` containers `Up`, none `Restarting`. Then,
from the VPS itself (or any machine that can reach it on port 80):

```bash
curl -s -o /dev/null -w "assoc1: %{http_code}\n" -H "Host: assoc1.yourdomain.com" http://<VPS_PUBLIC_IP>/
curl -s -o /dev/null -w "assoc2: %{http_code}\n" -H "Host: assoc2.yourdomain.com" http://<VPS_PUBLIC_IP>/
```

Both should print `200` (or `302` redirecting to the login page — either
means it's alive; follow with `curl -L` if you want to see the final `200`).
This confirms, before any DNS exists: both containers are healthy, both
migrated and created their superuser, and `nginx-proxy` is correctly routing
each hostname to the right instance.

To poke around in a real browser instead of `curl`, temporarily add to your
own machine's `/etc/hosts` (not the VPS's):

```text
<VPS_PUBLIC_IP>  assoc1.yourdomain.com
<VPS_PUBLIC_IP>  assoc2.yourdomain.com
```

Then visit `http://assoc1.yourdomain.com/` and `http://assoc2.yourdomain.com/`
normally (plain HTTP, expect a certificate warning if you try `https://` at
this stage — there's no cert yet). Log into each with its own
`DJANGO_SUPERUSER_EMAIL`/`DJANGO_SUPERUSER_PASSWORD`, confirm the admin
dashboard loads for both, and that assoc1's admin cannot see assoc2's data
(they're fully separate databases, so this is guaranteed by construction).
Set up each association's positions/candidates and run through
register → verify → vote → submit once yourself.

Remove those `/etc/hosts` lines again once you're done — Step 8 replaces
them with real DNS.

---

## Step 8 — Point DNS at the VPS and get real HTTPS (do this once you have DNSExit access)

In your DNSExit control panel, add **two A records**, both pointing at the
VPS's public IP address:

| Type | Host          | Value              |
|------|---------------|--------------------|
| A    | `assoc1`      | `<VPS_PUBLIC_IP>`  |
| A    | `assoc2`      | `<VPS_PUBLIC_IP>`  |

Check propagation from anywhere with normal internet access:

```bash
dig +short assoc1.yourdomain.com
dig +short assoc2.yourdomain.com
```

Both should print `<VPS_PUBLIC_IP>`. Once they do, trigger `acme-companion`
to request certs now rather than waiting for its next periodic check:

```bash
docker compose -f ~/apps/voting-assoc1/infra/proxy-stack/docker-compose.yml restart acme-companion
```

Then confirm issuance:

```bash
docker compose -f ~/apps/voting-assoc1/infra/proxy-stack/docker-compose.yml logs acme-companion
```

Look for both `assoc1.yourdomain.com` and `assoc2.yourdomain.com` getting a
certificate obtained successfully (no `NXDOMAIN`/challenge-failed errors).
Then visit `https://assoc1.yourdomain.com/` and `https://assoc2.yourdomain.com/`
for real — both should load with a valid padlock, no warning.

---

## After both are deployed

- [ ] Rotate/never reuse the old hardcoded superuser password that's in this
      repo's git history from before the Docker migration — treat it as
      burned regardless of which instance you're on.
- [ ] Back up both `.env` files somewhere safe off the VPS (e.g. a password
      manager) — they're gitignored, so losing the VPS means losing them,
      and regenerating `SECRET_KEY` invalidates every session/password reset
      link.
- [ ] `media_data` and `postgres_data` are per-instance named Docker volumes
      (Compose prefixes them with the directory name, e.g.
      `voting-assoc1_postgres_data`) — they persist across
      `docker compose up -d --build` but **not** across `docker compose down
      -v`. Never run `-v` on either instance unless you intend to wipe that
      instance's database and uploaded candidate photos.

## Redeploying later (code changes)

Per instance, independently:

```bash
cd ~/apps/voting-assoc1   # or voting-assoc2
git pull
docker compose up -d --build
```

Migrations and static files re-apply automatically on every container start
— no manual steps needed. Redeploying one instance never touches the other.

## Adding a third association later

Repeat Steps 3, 5/6, 8 for the new subdomain (`assoc3.yourdomain.com`,
`voting-assoc3` directory, its own `.env`) — Steps 2 and 4 (VPS setup,
shared proxy stack) are already done and don't need repeating.
