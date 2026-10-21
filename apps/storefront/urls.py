"""URL routing for Storefront HTML pages (Sub-phases 6.1 & 6.2)."""
from django.urls import path
from . import guest_views
from apps.storefront.views import (
    account_order_detail_view,
    account_orders_view,
    cart_page_view,
    checkout_page_view,
    home_page_view,
    login_page_view,
    payment_result_page_view,
    product_detail_page_view,
    product_list_page_view,
    sandbox_gateway_page_view,
    storefront_cart_add_view,
    storefront_cart_clear_view,
    storefront_cart_remove_view,
    storefront_cart_update_view,
    storefront_logout_view,
    storefront_order_cancel_view,
    storefront_order_pay_view,
)

app_name = "storefront"

urlpatterns = [
    path("checkout/guest/", guest_views.checkout, name="guest_checkout"),
    path("guest/orders/<str:order_number>/", guest_views.order_page, name="guest_order"),
    # Catalog & Product Pages (Sub-phase 6.1)
    path("", home_page_view, name="home"),
    path("shop/", product_list_page_view, name="product_list"),
    path("shop/category/<str:grade>/", product_list_page_view, name="category"),
    path("shop/<str:slug>/", product_detail_page_view, name="product_detail"),

    # Shopping Cart Pages & Form Actions (Sub-phase 6.2)
    path("cart/", cart_page_view, name="cart_page"),
    path("cart/add/", storefront_cart_add_view, name="cart_add"),
    path("cart/update/", storefront_cart_update_view, name="cart_update"),
    path("cart/remove/", storefront_cart_remove_view, name="cart_remove"),
    path("cart/clear/", storefront_cart_clear_view, name="cart_clear"),

    # Authentication Pages (Sub-phase 6.2)
    path("auth/login/", login_page_view, name="login_page"),
    path("auth/logout/", storefront_logout_view, name="logout_page"),

    # Checkout & Payment Pages (Sub-phase 6.2)
    path("checkout/", checkout_page_view, name="checkout_page"),
    path("payments/sandbox-gateway/<str:authority>/", sandbox_gateway_page_view, name="sandbox_gateway_page"),
    path("payments/result/<str:provider>/", payment_result_page_view, name="payment_result_page"),

    # Customer Account & Order Tracking Pages (Sub-phase 6.2)
    path("account/orders/", account_orders_view, name="account_orders"),
    path("account/orders/<str:order_number>/", account_order_detail_view, name="account_order_detail"),
    path("account/orders/<str:order_number>/pay/", storefront_order_pay_view, name="account_order_pay"),
    path("account/orders/<str:order_number>/cancel/", storefront_order_cancel_view, name="account_order_cancel"),
]
