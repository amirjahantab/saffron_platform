import secrets
from django.contrib import messages
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from apps.core.limits import enforce_limit
from apps.core.client_ip import client_ip
from apps.orders.access import owns_order, token_digest
from apps.orders.models import Order
from .guest_forms import GuestCheckoutForm
from apps.orders.services.cart_service import CartService
from apps.orders.services.checkout_service import CheckoutService
from apps.orders.exceptions import CartError, OrderError
from apps.payments.exceptions import PaymentError
from apps.payments.services.payment_service import PaymentService


@never_cache
@require_http_methods(["GET", "POST"])
def checkout(request):
    if request.user.is_authenticated:
        return redirect("storefront:checkout_page")
    cart = CartService.get_active_cart(request, create=False)
    state = request.session.get("guest_checkout_state", {})
    if request.method == "POST" and state.get("token") and secrets.compare_digest(request.POST.get("idempotency_key", ""), state.get("key", "")):
        previous = Order.objects.filter(user__isnull=True, idempotency_key=state["key"], guest_access_hash=token_digest(state["token"])).first()
        if previous:
            return redirect("storefront:guest_order", order_number=previous.order_number)
    if not cart or not cart.items.exists():
        return redirect("storefront:cart_page")
    if not state or state.get("cart") != str(cart.public_id):
        state = {"cart": str(cart.public_id), "token": secrets.token_urlsafe(32), "key": secrets.token_hex(16)}
        request.session["guest_checkout_state"] = state
    form = GuestCheckoutForm(request.POST or None, initial={"idempotency_key": state["key"], "shipping_method": "post_pishtaz"})
    if request.method == "POST" and form.is_valid():
        if not secrets.compare_digest(form.cleaned_data.get("idempotency_key", ""), state["key"]):
            form.add_error(None, "فرم منقضی شده است؛ صفحه را دوباره باز کنید.")
        elif not enforce_limit("guest-checkout:" + client_ip(request), 10, 3600):
            form.add_error(None, "تعداد درخواست‌ها بیش از حد مجاز است.")
        else:
            try:
                cleaned = form.cleaned_data
                order, created = CheckoutService.create_order_from_cart(user=None, guest_cart=cart, guest_token=state["token"], idempotency_key=state["key"], address_data=cleaned, shipping_method=cleaned["shipping_method"], customer_note=cleaned.get("customer_note", ""))
                tokens = request.session.get("guest_orders", {})
                tokens[order.order_number] = state["token"]
                request.session["guest_orders"] = dict(list(tokens.items())[-20:])
                from apps.insights.services import attach_order
                attach_order(request, order)
                return redirect("storefront:guest_order", order_number=order.order_number)
            except (CartError, OrderError) as exc:
                form.add_error(None, str(exc))
    return render(request, "storefront/guest_checkout.html", {"form": form, "cart": CartService.serialize_cart(cart), "page_title": "تکمیل خرید مهمان"})


@never_cache
@require_http_methods(["GET", "POST"])
def order_page(request, order_number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), order_number=order_number)
    if not owns_order(request, order):
        raise Http404
    if request.method == "POST":
        if not enforce_limit("guest-payment:" + client_ip(request), 20, 3600):
            messages.error(request, "کمی بعد دوباره تلاش کنید.")
        else:
            try:
                _, destination, _ = PaymentService.initiate_payment(order=order, user=request.user if request.user.is_authenticated else None, guest_token=request.session.get("guest_orders", {}).get(order.order_number))
                return redirect(destination)
            except PaymentError as exc:
                messages.error(request, str(exc))
    return render(request, "storefront/guest_order.html", {"order": order, "page_title": "پیگیری خرید مهمان"})
