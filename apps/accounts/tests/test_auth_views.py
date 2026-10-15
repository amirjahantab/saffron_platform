"""Integration tests for OTP request, verify, session fixation protection, and logout views."""
import json
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from apps.accounts.models import User
from apps.accounts.services.sms_provider import SandboxSMSProvider
from apps.accounts.signals import user_logged_in_via_otp


class AuthEndpointsTests(TestCase):
    """End-to-end tests for /accounts/ HTTP endpoints."""

    def setUp(self) -> None:
        cache.clear()
        SandboxSMSProvider.clear_outbox()

    def test_full_otp_login_flow_and_session_rotation(self) -> None:
        # Initialize a guest session before login (simulating a guest with a cart)
        session = self.client.session
        session["guest_cart_marker"] = "cart_123"
        session.save()
        initial_session_key = session.session_key

        signal_payloads: list[dict[str, object]] = []

        def _signal_receiver(sender: object, **kwargs: object) -> None:
            signal_payloads.append(kwargs)

        user_logged_in_via_otp.connect(_signal_receiver)
        try:
            # 1. Request OTP with Persian digits
            req_url = reverse("accounts:otp_request")
            req_resp = self.client.post(
                req_url,
                data=json.dumps({"phone_number": "۰۹۱۵۳۳۳۴۴۵۵"}),
                content_type="application/json",
            )
            self.assertEqual(req_resp.status_code, 200)
            req_data = req_resp.json()
            # Ensure raw OTP is NEVER leaked in HTTP response
            sent_code = SandboxSMSProvider.outbox[0]["code"]
            self.assertNotIn(sent_code, req_resp.content.decode("utf-8"))
            self.assertEqual(req_data["masked_phone"], "0915***4455")

            # 2. Verify OTP
            verify_url = reverse("accounts:otp_verify")
            verify_resp = self.client.post(
                verify_url,
                data=json.dumps({"phone_number": "09153334455", "code": sent_code}),
                content_type="application/json",
            )
            self.assertEqual(verify_resp.status_code, 200)
            verify_data = verify_resp.json()
            self.assertTrue(verify_data["is_new_user"])
            self.assertEqual(verify_data["user"]["phone_number"], "09153334455")

            # Verify Session Fixation protection: session_key must rotate upon login
            new_session_key = self.client.session.session_key
            self.assertNotEqual(initial_session_key, new_session_key)

            # Verify signal was fired with pre_login_session_key for Phase 4 cart merge
            self.assertEqual(len(signal_payloads), 1)
            self.assertEqual(signal_payloads[0]["pre_login_session_key"], initial_session_key)

            # 3. Check /accounts/me/ authenticated status
            me_url = reverse("accounts:session_status")
            me_resp = self.client.get(me_url)
            self.assertEqual(me_resp.status_code, 200)
            self.assertTrue(me_resp.json()["is_authenticated"])

            # 4. Logout via GET must be rejected (405 Method Not Allowed)
            logout_url = reverse("accounts:logout")
            get_logout_resp = self.client.get(logout_url)
            self.assertEqual(get_logout_resp.status_code, 405)

            # 5. Logout via POST succeeds and clears session
            post_logout_resp = self.client.post(logout_url)
            self.assertEqual(post_logout_resp.status_code, 200)

            me_after_logout = self.client.get(me_url)
            self.assertEqual(me_after_logout.status_code, 401)
        finally:
            user_logged_in_via_otp.disconnect(_signal_receiver)

    def test_disabled_user_cannot_login_even_with_valid_otp(self) -> None:
        User.objects.create_user(phone_number="09129998877", is_active=False)

        self.client.post(
            reverse("accounts:otp_request"),
            data={"phone_number": "09129998877"},
        )
        sent_code = SandboxSMSProvider.outbox[0]["code"]

        verify_resp = self.client.post(
            reverse("accounts:otp_verify"),
            data={"phone_number": "09129998877", "code": sent_code},
        )
        self.assertEqual(verify_resp.status_code, 403)
        self.assertEqual(verify_resp.json()["code"], "account_disabled")