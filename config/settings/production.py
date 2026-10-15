"""
Production settings for Saffron E-commerce Platform.
Enforces strict security controls, HTTPS headers, and mandatory environment variables.
"""
from django.core.exceptions import ImproperlyConfigured
from .base import *  # noqa: F401, F403

DEBUG = False

SECRET_KEY = get_env_variable("DJANGO_SECRET_KEY", required=True)
if SECRET_KEY.startswith("django-insecure") or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured(
        "Production DJANGO_SECRET_KEY must be at least 50 characters and not use an insecure prefix."
    )

ALLOWED_HOSTS = get_env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be explicitly set in production.")

CSRF_TRUSTED_ORIGINS = get_env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS must be explicitly set in production.")

# Enforce mandatory database password in production
if not DATABASES["default"]["PASSWORD"]:
    raise ImproperlyConfigured("POSTGRES_PASSWORD must be set in production.")

# Use Redis-backed sessions in production for performance and horizontal scalability
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# HTTPS & Transport Security Headers
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = get_env_bool("SECURE_SSL_REDIRECT", default=True)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = int(get_env_variable("SECURE_HSTS_SECONDS", default="31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True