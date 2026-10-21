from contextlib import contextmanager, ExitStack
from threading import RLock
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils.crypto import salted_hmac
from redis.exceptions import LockError

_test_lock = RLock()


@contextmanager
def otp_locks(*identifiers):
    """Serialize challenge mutation and shared IP admission; Redis fails closed."""
    if hasattr(cache, "lock"):
        with ExitStack() as stack:
            for value in sorted(set(identifiers)):
                key = "otp:lock:" + salted_hmac("otp-lock", value).hexdigest()
                stack.enter_context(cache.lock(key, timeout=60, blocking_timeout=5))
            yield
    elif settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache" and settings.OTP_SANDBOX_STORE_OUTBOX:
        with _test_lock:
            yield
    else:
        raise ImproperlyConfigured("OTP requires Redis distributed locks outside isolated tests.")
