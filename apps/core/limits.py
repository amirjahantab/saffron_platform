"""Atomic fixed-window admission with fail-closed cache errors."""
from django.core.cache import cache


def enforce_limit(key, maximum, seconds):
    key = "limit:" + key
    if cache.add(key, 1, timeout=seconds):
        return True
    try:
        return cache.incr(key) <= maximum
    except ValueError:
        # Expired between add and increment; compete atomically for new window.
        return cache.add(key, 1, timeout=seconds)
