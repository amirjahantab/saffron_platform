"""WSGI config for Saffron E-commerce Platform."""
import os
from pathlib import Path
from django.core.wsgi import get_wsgi_application
from manage import load_dotenv_file

base_dir = Path(__file__).resolve().parent.parent
load_dotenv_file(base_dir / ".env")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()