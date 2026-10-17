"""URL routing for Storefront HTML pages."""
from django.urls import path
from apps.storefront.views import (
    account_orders_stub_view,
    cart_page_stub_view,
    checkout_page_stub_view,
    home_page_view,
    login_page_stub_view,
    product_detail_page_view,
    product_list_page_view,
    storefront_cart_add_view,
)

app_name = "storefront"

urlpatterns = [
    path("", home_page_view, name="home"),
    path("shop/", product_list_page_view, name="product_list"),
    path("shop/<str:slug>/", product_detail_page_view, name="product_detail"),
    path("cart/add/", storefront_cart_add_view, name="cart_add"),
    # Navigation routes to be expanded with full templates in Sub-phase 6.2
    path("cart/", cart_page_stub_view, name="cart_page"),
    path("checkout/", checkout_page_stub_view, name="checkout_page"),
    path("auth/login/", login_page_stub_view, name="login_page"),
    path("account/orders/", account_orders_stub_view, name="account_orders"),
]