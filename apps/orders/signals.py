"""
Signal receivers for the orders app.
Listens to `user_logged_in_via_otp` from `apps.accounts` to merge guest shopping carts.
"""
from typing import Any
from django.dispatch import receiver
from apps.accounts.models import User
from apps.accounts.signals import user_logged_in_via_otp
from apps.orders.services.cart_service import CartService


@receiver(user_logged_in_via_otp)
def handle_guest_cart_merge_on_otp_login(
    sender: Any,
    user: User,
    request: Any,
    pre_login_session_key: str | None = None,
    **kwargs: Any,
) -> None:
    """Automatically merge any active guest cart into the authenticated user's cart."""
    if pre_login_session_key:
        CartService.merge_guest_cart_into_user_cart(
            user=user,
            guest_session_key=pre_login_session_key,
        )