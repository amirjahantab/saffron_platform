"""Infrastructure health check views."""
import logging
import uuid
from django.core.cache import cache
from django.db import connections
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def check_database_health() -> tuple[bool, str]:
    """Execute a lightweight SELECT 1 query to verify database connectivity."""
    try:
        connection = connections["default"]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            if row and row[0] == 1:
                return True, "ok"
        return False, "unexpected_response"
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        return False, "unreachable"


def check_cache_health() -> tuple[bool, str]:
    """Perform an atomic set/get/delete cycle on the configured cache (Redis)."""
    probe_key = f"healthcheck:probe:{uuid.uuid4().hex}"
    probe_value = "alive"
    try:
        cache.set(probe_key, probe_value, timeout=10)
        fetched = cache.get(probe_key)
        cache.delete(probe_key)
        if fetched == probe_value:
            return True, "ok"
        return False, "value_mismatch"
    except Exception as exc:
        logger.error("Cache health check failed: %s", exc)
        return False, "unreachable"


@never_cache
@require_GET
def health_check_view(request: HttpRequest) -> JsonResponse:
    """
    Readiness and liveness endpoint for load balancers, Docker, and monitoring.
    Returns HTTP 200 if both PostgreSQL and Redis are operational, otherwise HTTP 503.
    """
    db_ok, db_detail = check_database_health()
    cache_ok, cache_detail = check_cache_health()

    overall_healthy = db_ok and cache_ok
    status_code = 200 if overall_healthy else 503

    payload = {
        "status": "healthy" if overall_healthy else "unhealthy",
        "services": {
            "database": db_detail,
            "cache": cache_detail,
        },
    }
    return JsonResponse(payload, status=status_code)