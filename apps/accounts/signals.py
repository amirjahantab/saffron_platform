"""
Custom authentication signals for decoupled cross-app integration.
Phase 4 (Cart & Orders) will connect to `user_logged_in_via_otp` to merge guest carts.
"""
from django.dispatch import Signal

# Provides arguments: `user`, `request`, `pre_login_session_key`
user_logged_in_via_otp = Signal()