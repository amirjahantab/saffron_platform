"""ASGI config for Saffron E-commerce Platform."""
import os
from pathlib import Path
from django.core.asgi import get_asgi_application
from manage import load_dotenv_file

base_dir = Path(__file__).resolve().parent.parent
load_dotenv_file(base_dir / ".env")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()