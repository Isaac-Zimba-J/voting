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

email = "21111111@gmail.com"
password = "Admin@123#@!"
first_name = "Admin"  # optional
last_name = "User"    # optional

if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_staff=True,
        is_superuser=True
    )
    print("✅ Superuser created.")
else:
    print("ℹ️ Superuser already exists.")
