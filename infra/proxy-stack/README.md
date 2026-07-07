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
