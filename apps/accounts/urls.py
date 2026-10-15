"""URL routing for accounts and OTP authentication."""
from django.urls import path
from apps.accounts.views import (
    logout_view,
    otp_request_view,
    otp_verify_view,
    session_status_view,
)

app_name = "accounts"

urlpatterns = [
    path("otp/request/", otp_request_view, name="otp_request"),
    path("otp/verify/", otp_verify_view, name="otp_verify"),
    path("logout/", logout_view, name="logout"),
    path("me/", session_status_view, name="session_status"),
]