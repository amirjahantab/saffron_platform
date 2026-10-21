"""Validate live readiness before opening checkout, then replace process with Gunicorn."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import django
from django.conf import settings
from django.core.management import call_command

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
django.setup()
if settings.STORE_OPEN:
    call_command("verify_launch")
os.execvp("gunicorn", ["gunicorn", "-c", "config/gunicorn.py", "config.wsgi:application"])
