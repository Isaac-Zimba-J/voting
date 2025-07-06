#!/usr/bin/env bash
# This script builds the Docker image for the project.

set -o errexit


pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate

if[[ $CREATE_SUPERUSER == "true" ]]; 
then
    python manage.py createsuperuser --no-input  --email "$DJANGO_SUPERUSER_EMAIL" --username "$DJANGO_SUPERUSER_USERNAME" 
fiA#!/usr/bin/env bash
# This script builds the Docker image for the project.

set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate

if [ "$CREATE_SUPERUSER" = "true" ]; then
  python manage.py createsuperuser \
    --no-input \
    --email "$DJANGO_SUPERUSER_EMAIL" \
    --username "$DJANGO_SUPERUSER_USERNAME"
fi
