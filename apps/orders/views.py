"""
HTTP JSON endpoints for shopping cart inspection and manipulation (Sub-phase 4.1).
All pricing is strictly computed server-side from database records.
"""
import json
from typing import Any
from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from apps.orders.exceptions import CartError
from apps.orders.forms import CartAddItemForm, CartRemoveItemForm, CartUpdateItemForm
from apps.orders.services.cart_service import CartService


def _parse_request_payload(request: HttpRequest) -> dict[str, Any]:
    """Parse JSON or form-urlencoded POST payload safely."""
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            parsed = json.loads(request.body.decode("utf-8") or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}
    return request.POST.dict()


@never_cache
@require_GET
def cart_detail_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: GET /orders/cart/
    Returns current guest or authenticated user cart with authoritative Rial/Toman totals.
    """
    cart = CartService.get_active_cart(request, create=False)
    return JsonResponse(
        {
            "status": "ok",
            "cart": CartService.serialize_cart(cart),
        },
        status=200,
    )


@never_cache
@require_POST
def cart_add_item_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: POST /orders/cart/items/add/
    Adds a ProductVariant to the active cart (ignores any client-supplied price fields).
    """
    payload = _parse_request_payload(request)
    form = CartAddItemForm(data=payload)
    if not form.is_valid():
        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

    try:
        item = CartService.add_item(
            request=request,
            variant_public_id=form.cleaned_data["variant_public_id"],
            quantity_to_add=form.cleaned_data["quantity"],
        )
    except CartError as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": exc.code,
                "message": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "status": "ok",
            "message": _("محصول به سبد خرید اضافه شد."),
            "cart": CartService.serialize_cart(item.cart),
        },
        status=200,
    )


@never_cache
@require_POST
def cart_update_item_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: POST /orders/cart/items/update/
    Updates exact quantity of a variant in the cart (or removes it if quantity == 0).
    """
    payload = _parse_request_payload(request)
    form = CartUpdateItemForm(data=payload)
    if not form.is_valid():
        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

    try:
        CartService.update_item_quantity(
            request=request,
            variant_public_id=form.cleaned_data["variant_public_id"],
            new_quantity=form.cleaned_data["quantity"],
        )
    except CartError as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": exc.code,
                "message": str(exc),
            },
            status=400,
        )

    cart = CartService.get_active_cart(request, create=False)
    return JsonResponse(
        {
            "status": "ok",
            "message": _("سبد خرید به‌روزرسانی شد."),
            "cart": CartService.serialize_cart(cart),
        },
        status=200,
    )


@never_cache
@require_POST
def cart_remove_item_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: POST /orders/cart/items/remove/
    Removes a variant line item from the active cart.
    """
    payload = _parse_request_payload(request)
    form = CartRemoveItemForm(data=payload)
    if not form.is_valid():
        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

    removed = CartService.remove_item(
        request=request,
        variant_public_id=form.cleaned_data["variant_public_id"],
    )
    if not removed:
        return JsonResponse(
            {
                "status": "error",
                "code": "item_not_found",
                "message": _("این محصول در سبد خرید شما یافت نشد."),
            },
            status=404,
        )

    cart = CartService.get_active_cart(request, create=False)
    return JsonResponse(
        {
            "status": "ok",
            "message": _("محصول از سبد خرید حذف شد."),
            "cart": CartService.serialize_cart(cart),
        },
        status=200,
    )


@never_cache
@require_POST
def cart_clear_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: POST /orders/cart/clear/
    Empties all items from the active cart.
    """
    CartService.clear_cart(request)
    cart = CartService.get_active_cart(request, create=False)
    return JsonResponse(
        {
            "status": "ok",
            "message": _("سبد خرید خالی شد."),
            "cart": CartService.serialize_cart(cart),
        },
        status=200,
    )