#!/usr/bin/env python

import os
import django

# Set the default Django settings module for the 'django' program.
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
