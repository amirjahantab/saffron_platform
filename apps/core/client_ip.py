from ipaddress import ip_address
from django.conf import settings


def client_ip(request):
    value = request.META.get("REMOTE_ADDR", "")
    # Production proxy overwrites this header; application port is never published.
    if settings.TRUST_PROXY_HEADERS:
        value = request.META.get("HTTP_X_REAL_IP", value)
    try:
        return str(ip_address(value))
    except ValueError:
        return "unknown"
