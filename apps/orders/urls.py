"""URL routing for shopping cart (Sub-phase 4.1) and checkout/order management (Sub-phase 4.3)."""
from django.urls import path
from apps.orders.views import (
    cart_add_item_view,
    cart_clear_view,
    cart_detail_view,
    cart_remove_item_view,
    cart_update_item_view,
    checkout_view,
    order_cancel_view,
    order_detail_view,
    order_list_view,
)

app_name = "orders"

urlpatterns = [
    # Shopping Cart endpoints
    path("cart/", cart_detail_view, name="cart_detail"),
    path("cart/items/add/", cart_add_item_view, name="cart_add_item"),
    path("cart/items/update/", cart_update_item_view, name="cart_update_item"),
    path("cart/items/remove/", cart_remove_item_view, name="cart_remove_item"),
    path("cart/clear/", cart_clear_view, name="cart_clear"),
    # Checkout & Order endpoints
    path("checkout/", checkout_view, name="checkout"),
    path("", order_list_view, name="order_list"),
    path("<str:order_number>/", order_detail_view, name="order_detail"),
    path("<str:order_number>/cancel/", order_cancel_view, name="order_cancel"),
]