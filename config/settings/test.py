"""
Test settings for Saffron E-commerce Platform.
Allows running the test suite deterministically and rapidly in CI or local environments.
Supports both PostgreSQL/Redis (when USE_EXTERNAL_TEST_SERVICES=True) and isolated in-memory backends.
"""
from .base import *  # noqa: F401, F403

DEBUG = False
ALLOW_SANDBOX_PAYMENTS = True
ENABLE_ACTION_LIMITS = False  # Individual limiter tests opt in; domain suites share cache keys.
STORE_OPEN = True
SECRET_KEY = "test-only-secret-key-with-sufficient-length-for-security-checks-0123456789"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

USE_EXTERNAL_TEST_SERVICES = get_env_bool("USE_EXTERNAL_TEST_SERVICES", default=False)

if USE_EXTERNAL_TEST_SERVICES:
    # cache.clear() in security tests must never flush development/browser sessions.
    from urllib.parse import urlsplit, urlunsplit
    CACHES["default"]["LOCATION"] = get_env_variable("TEST_REDIS_URL", urlunsplit(urlsplit(REDIS_URL)._replace(path="/15")))
    CACHES["default"]["KEY_PREFIX"] = "saffron-tests"

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
