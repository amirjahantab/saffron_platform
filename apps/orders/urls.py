"""URL routing for shopping cart (Sub-phase 4.1) and orders (Sub-phases 4.2 & 4.3)."""
from django.urls import path
from apps.orders.views import (
    cart_add_item_view,
    cart_clear_view,
    cart_detail_view,
    cart_remove_item_view,
    cart_update_item_view,
)

app_name = "orders"

urlpatterns = [
    path("cart/", cart_detail_view, name="cart_detail"),
    path("cart/items/add/", cart_add_item_view, name="cart_add_item"),
    path("cart/items/update/", cart_update_item_view, name="cart_update_item"),
    path("cart/items/remove/", cart_remove_item_view, name="cart_remove_item"),
    path("cart/clear/", cart_clear_view, name="cart_clear"),
]