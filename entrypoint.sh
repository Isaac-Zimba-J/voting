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
