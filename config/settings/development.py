"""
Development settings for Saffron E-commerce Platform.
Designed for local engineering and debugging while maintaining baseline security hygiene.
"""


from .base import *  # noqa: F401, F403

DEBUG = get_env_bool("DJANGO_DEBUG", default=True)

SECRET_KEY = get_env_variable(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-only-key-do-not-use-in-production-9876543210",
)

ALLOWED_HOSTS = get_env_list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "[::1]", "0.0.0.0", "testserver"],
)

CSRF_TRUSTED_ORIGINS = get_env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:8000", "http://127.0.0.1:8000"],
)

# In development over HTTP, secure cookies are disabled so local login/CSRF works over localhost
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False