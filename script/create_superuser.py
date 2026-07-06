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
