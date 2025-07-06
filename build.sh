#!/usr/bin/env bash
# This script builds the Docker image for the project.

set -o errexit

# Install dependencies
pip install -r requirements.txt

# Collect static files and run migrations
python manage.py collectstatic --noinput
python manage.py migrate

# Optional: Create superuser if environment variable is set
if [[ "$CREATE_SUPERUSER" == "true" ]]; then
  python manage.py createsuperuser \
    --no-input \
    --email "$DJANGO_SUPERUSER_EMAIL" \
    --username "$DJANGO_SUPERUSER_USERNAME"
fi


# Hardcode superuser creation
echo "Creating hardcoded superuser..."

python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
username = 'admin'
email = '21111111@gmail.com'
password = 'Admin@1234'

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print('Superuser created.')
else:
    print('Superuser already exists.')
"
