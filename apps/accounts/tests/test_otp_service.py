"""Security and functional tests for OTPService (hashing, expiry, rate limits, brute-force)."""
from unittest.mock import patch
from django.core.cache import cache
from django.test import TestCase, override_settings
from apps.accounts.services.otp_service import (
    OTPInvalidError,
    OTPRateLimitError,
    OTPService,
)
from apps.accounts.services.sms_provider import SandboxSMSProvider


class OTPServiceSecurityTests(TestCase):
    """Verify OTP hashing, expiration, single-use, and rate-limiting policies."""

    def setUp(self) -> None:
        cache.clear()
        SandboxSMSProvider.clear_outbox()

    def test_otp_is_hashed_in_cache_and_never_stored_in_plaintext(self) -> None:
        phone = "09121112233"
        OTPService.request_otp(phone, client_ip="127.0.0.1")

        self.assertEqual(len(SandboxSMSProvider.outbox), 1)
        sent_code = SandboxSMSProvider.outbox[0]["code"]

        stored_challenge = cache.get(OTPService._challenge_key(phone))
        self.assertIsNotNone(stored_challenge)
        self.assertNotEqual(stored_challenge["hash"], sent_code)
        self.assertNotIn(sent_code, str(stored_challenge))

    def test_valid_otp_verifies_and_is_single_use(self) -> None:
        phone = "09121112233"
        OTPService.request_otp(phone, client_ip="127.0.0.1")
        sent_code = SandboxSMSProvider.outbox[0]["code"]

        verified_phone = OTPService.verify_otp(phone, sent_code, client_ip="127.0.0.1")
        self.assertEqual(verified_phone, phone)

        # Replay attack must fail immediately because challenge was deleted
        with self.assertRaises(OTPInvalidError):
            OTPService.verify_otp(phone, sent_code, client_ip="127.0.0.1")

    def test_expired_otp_is_rejected(self) -> None:
        phone = "09121112244"
        with patch("apps.accounts.services.otp_service.time.time", return_value=1_700_000_000):
            OTPService.request_otp(phone, client_ip="127.0.0.1")
            sent_code = SandboxSMSProvider.outbox[0]["code"]

        # Advance clock past 120s expiry
        with patch("apps.accounts.services.otp_service.time.time", return_value=1_700_000_125):
            with self.assertRaises(OTPInvalidError):
                OTPService.verify_otp(phone, sent_code, client_ip="127.0.0.1")

    def test_resend_cooldown_blocks_immediate_duplicate_requests(self) -> None:
        phone = "09121112255"
        OTPService.request_otp(phone, client_ip="127.0.0.1")

        with self.assertRaises(OTPRateLimitError) as ctx:
            OTPService.request_otp(phone, client_ip="127.0.0.1")
        self.assertGreater(ctx.exception.retry_after, 0)

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=0, OTP_MAX_REQUESTS_PER_HOUR_PHONE=3)
    def test_hourly_phone_rate_limit_blocks_excessive_requests(self) -> None:
        phone = "09121112266"
        for _ in range(3):
            cache.delete(OTPService._cooldown_key(phone))
            OTPService.request_otp(phone, client_ip="127.0.0.1")

        cache.delete(OTPService._cooldown_key(phone))
        with self.assertRaises(OTPRateLimitError):
            OTPService.request_otp(phone, client_ip="127.0.0.1")

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=0, OTP_MAX_REQUESTS_PER_HOUR_IP=3)
    def test_hourly_ip_rate_limit_blocks_sms_bombing_across_numbers(self) -> None:
        client_ip = "198.51.100.25"
        for i in range(3):
            OTPService.request_otp(f"0912111220{i}", client_ip=client_ip)

        with self.assertRaises(OTPRateLimitError):
            OTPService.request_otp("09121112209", client_ip=client_ip)

    @override_settings(OTP_MAX_VERIFY_ATTEMPTS=3)
    def test_brute_force_invalidates_otp_after_max_failed_attempts(self) -> None:
        phone = "09121112277"
        OTPService.request_otp(phone, client_ip="127.0.0.1")
        real_code = SandboxSMSProvider.outbox[0]["code"]
        wrong_code = "000000" if real_code != "000000" else "999999"

        # Attempts 1 and 2 raise OTPInvalidError
        for _ in range(2):
            with self.assertRaises(OTPInvalidError):
                OTPService.verify_otp(phone, wrong_code, client_ip="127.0.0.1")

        # Attempt 3 hits the cap, deletes the challenge, and raises OTPRateLimitError
        with self.assertRaises(OTPRateLimitError):
            OTPService.verify_otp(phone, wrong_code, client_ip="127.0.0.1")

        # Even providing the real code afterward must fail because the challenge was purged
        with self.assertRaises(OTPInvalidError):
            OTPService.verify_otp(phone, real_code, client_ip="127.0.0.1")