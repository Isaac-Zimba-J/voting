#!/usr/bin/env bash
# This script builds the Docker image for the project.

set -o errexit

# Install dependencies
pip install -r requirements.txt

# Collect static files and run migrations
python manage.py collectstatic --noinput
python manage.py migrate

python script/create_superuser.py


# Optional: Create superuser if environment variable is set
if [[ "$CREATE_SUPERUSER" == "true" ]]; then
  python manage.py createsuperuser \
    --no-input \
    --email "$DJANGO_SUPERUSER_EMAIL" \
    --username "$DJANGO_SUPERUSER_USERNAME"
fi

