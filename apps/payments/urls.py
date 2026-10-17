"""URL routing for payment initiation, gateway callbacks, status inspection, and refunds."""
from django.urls import path
from apps.payments.views import (
    order_payment_refund_view,
    order_payment_status_view,
    payment_callback_view,
    payment_initiate_view,
)

app_name = "payments"

urlpatterns = [
    path("initiate/<str:order_number>/", payment_initiate_view, name="payment_initiate"),
    path("callback/<str:provider>/", payment_callback_view, name="payment_callback"),
    path("order/<str:order_number>/status/", order_payment_status_view, name="order_payment_status"),
    path("order/<str:order_number>/refund/", order_payment_refund_view, name="order_payment_refund"),
]