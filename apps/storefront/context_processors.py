"""
Global template context processor for the Storefront.
Injects authoritative cart summary (item count & Toman payable total) and
supported SaffronGrade choices into every rendered template.
"""
from typing import Any
from django.http import HttpRequest
from django.conf import settings
from apps.catalog.models import SaffronGrade
from apps.core.currency import format_price_toman
from apps.content.models import PolicyPage
from apps.orders.services.cart_service import CartService


def storefront_context(request: HttpRequest) -> dict[str, Any]:
    """Provide real-time cart summary and navigation categories across all pages."""
    cart = CartService.get_active_cart(request, create=False)
    cart_summary = CartService.serialize_cart(cart)

    saffron_grades = [
        {"code": code, "label": label}
        for code, label in SaffronGrade.choices
    ]

    return {
        "nav_cart": cart_summary,
        "nav_saffron_grades": saffron_grades,
        "free_shipping_threshold_formatted": format_price_toman(settings.ORDER_FREE_SHIPPING_THRESHOLD_RIAL),
        "is_demo": settings.DEMO_MODE,
        "assistant_enabled": settings.ASSISTANT_ENABLED,
        "checkout_available": settings.STORE_OPEN or settings.DEMO_MODE,
        "public_policies": PolicyPage.objects.filter(is_published=True).only("slug", "title"),
    }
