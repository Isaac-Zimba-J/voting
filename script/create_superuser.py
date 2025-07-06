#!/usr/bin/env python

import os
import sys
import django

# Add project root (where manage.py is) to PYTHONPATH
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.append(PROJECT_ROOT)

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e_voting.settings')

# Setup Django
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = "admin"
email = "21111111@gmail.com"
password = "Admin@123#@!"

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print("✅ Superuser created.")
else:
    print("ℹ️ Superuser already exists.")
