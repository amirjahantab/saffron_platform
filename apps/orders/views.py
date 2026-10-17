"""
HTTP JSON endpoints for Shopping Cart (Sub-phase 4.1) and Checkout & Order Management (Sub-phase 4.3).
All pricing is strictly computed server-side from database records, and all order endpoints
strictly enforce user ownership to prevent IDOR vulnerabilities.
"""
import json
from typing import Any
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from apps.accounts.models import User
from apps.orders.exceptions import (
    CartError,
    EmptyCartCheckoutError,
    InsufficientStockError,
    InvalidOrderStateTransitionError,
    OrderError,
)
from apps.orders.forms import (
    CartAddItemForm,
    CartRemoveItemForm,
    CartUpdateItemForm,
    CheckoutForm,
    OrderCancelForm,
)
from apps.orders.models import Order
from apps.orders.services.cart_service import CartService
from apps.orders.services.checkout_service import CheckoutService
from apps.orders.services.reservation_service import OrderStateAndReservationService


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


def _require_authenticated_user(request: HttpRequest) -> JsonResponse | None:
    """Return a 401 JsonResponse if the request user is not authenticated."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "status": "error",
                "code": "authentication_required",
                "message": _("برای ثبت و مشاهده سفارش، لطفاً ابتدا وارد حساب کاربری خود شوید."),
            },
            status=401,
        )
    return None


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


@never_cache
@require_POST
def checkout_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: POST /orders/checkout/
    Atomically converts the authenticated user's active Cart into an Order,
    reserves inventory, and returns the authoritative Order summary.
    """
    auth_err = _require_authenticated_user(request)
    if auth_err is not None:
        return auth_err

    payload = _parse_request_payload(request)
    # Also accept idempotency key from HTTP header `X-Idempotency-Key`
    header_idem_key = request.headers.get("X-Idempotency-Key", "").strip()
    if header_idem_key and not payload.get("idempotency_key"):
        payload["idempotency_key"] = header_idem_key

    form = CheckoutForm(data=payload)
    if not form.is_valid():
        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

    user: User = request.user  # type: ignore[assignment]
    cleaned = form.cleaned_data

    try:
        order, created = CheckoutService.create_order_from_cart(
            user=user,
            shipping_address_public_id=cleaned.get("shipping_address_public_id"),
            address_data={
                "recipient_full_name": cleaned.get("recipient_full_name"),
                "recipient_phone": cleaned.get("recipient_phone"),
                "province": cleaned.get("province"),
                "city": cleaned.get("city"),
                "address_line": cleaned.get("address_line"),
                "postal_code": cleaned.get("postal_code"),
            },
            save_new_address=bool(cleaned.get("save_address")),
            shipping_method=cleaned["shipping_method"],
            customer_note=cleaned.get("customer_note") or "",
            idempotency_key=cleaned.get("idempotency_key"),
        )
    except InsufficientStockError as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": exc.code,
                "message": str(exc),
            },
            status=409,
        )
    except (EmptyCartCheckoutError, CartError, OrderError) as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": exc.code,
                "message": str(exc),
            },
            status=400,
        )

    status_code = 201 if created else 200
    return JsonResponse(
        {
            "status": "ok",
            "created": created,
            "message": _("سفارش شما با موفقیت ثبت و موجودی کالا رزرو شد."),
            "order": CheckoutService.serialize_order(order, include_items=True),
        },
        status=status_code,
    )


@never_cache
@require_GET
def order_list_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: GET /orders/
    Returns the authenticated user's own orders (strictly scoped to `request.user`).
    """
    auth_err = _require_authenticated_user(request)
    if auth_err is not None:
        return auth_err

    user: User = request.user  # type: ignore[assignment]
    orders_qs = (
        Order.objects.filter(user=user)
        .prefetch_related("items", "items__variant")
        .order_by("-created_at")
    )

    serialized_orders = [
        CheckoutService.serialize_order(order, include_items=False)
        for order in orders_qs
    ]
    return JsonResponse(
        {
            "status": "ok",
            "count": len(serialized_orders),
            "orders": serialized_orders,
        },
        status=200,
    )


@never_cache
@require_GET
def order_detail_view(request: HttpRequest, order_number: str) -> JsonResponse:
    """
    Endpoint: GET /orders/<str:order_number>/
    Returns full order details and line item snapshots ONLY if owned by `request.user`.
    """
    auth_err = _require_authenticated_user(request)
    if auth_err is not None:
        return auth_err

    user: User = request.user  # type: ignore[assignment]
    order = get_object_or_404(
        Order.objects.filter(user=user).prefetch_related("items", "items__variant"),
        order_number=order_number.strip().upper(),
    )
    return JsonResponse(
        {
            "status": "ok",
            "order": CheckoutService.serialize_order(order, include_items=True),
        },
        status=200,
    )


@never_cache
@require_POST
def order_cancel_view(request: HttpRequest, order_number: str) -> JsonResponse:
    """
    Endpoint: POST /orders/<str:order_number>/cancel/
    Allows the authenticated owner to cancel a `PENDING_PAYMENT` order and immediately
    release its reserved stock back to the catalog.
    """
    auth_err = _require_authenticated_user(request)
    if auth_err is not None:
        return auth_err

    user: User = request.user  # type: ignore[assignment]
    order = get_object_or_404(
        Order.objects.filter(user=user),
        order_number=order_number.strip().upper(),
    )

    if order.status != Order.Status.PENDING_PAYMENT:
        return JsonResponse(
            {
                "status": "error",
                "code": "cannot_cancel_in_current_status",
                "message": _("لغو مستقیم توسط مشتری فقط برای سفارش‌های «در انتظار پرداخت» امکان‌پذیر است."),
            },
            status=400,
        )

    payload = _parse_request_payload(request)
    form = OrderCancelForm(data=payload)
    form.is_valid()
    reason = form.cleaned_data.get("cancel_reason") or _("لغو به درخواست مشتری")

    try:
        updated_order = OrderStateAndReservationService.transition_order_status(
            order=order,
            target_status=Order.Status.CANCELLED,
            cancel_reason=str(reason),
        )
    except InvalidOrderStateTransitionError as exc:
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
            "message": _("سفارش شما لغو شد و موجودی رزروشده آزاد گردید."),
            "order": CheckoutService.serialize_order(updated_order, include_items=True),
        },
        status=200,
    )