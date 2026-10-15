"""
Test settings for Saffron E-commerce Platform.
Allows running the test suite deterministically and rapidly in CI or local environments.
Supports both PostgreSQL/Redis (when USE_EXTERNAL_TEST_SERVICES=True) and isolated in-memory backends.
"""
from .base import *  # noqa: F401, F403

DEBUG = False
SECRET_KEY = "test-only-secret-key-with-sufficient-length-for-security-checks-0123456789"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

USE_EXTERNAL_TEST_SERVICES = get_env_bool("USE_EXTERNAL_TEST_SERVICES", default=False)

if not USE_EXTERNAL_TEST_SERVICES:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "saffron-test-cache",
        }
    }

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Enable in-memory SMS outbox inspection during automated test runs
OTP_SANDBOX_STORE_OUTBOX = True