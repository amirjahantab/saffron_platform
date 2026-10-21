from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from apps.accounts.services.otp_service import OTPService, OTPRateLimitError, OTPInvalidError
from apps.accounts.services.sms_provider import SandboxSMSProvider, SMSDeliveryError


class ConcurrentOTPTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        SandboxSMSProvider.clear_outbox()

    def test_simultaneous_sms_requests_admit_only_one(self):
        def request():
            try:
                OTPService.request_otp("09121114444", "198.51.100.1")
                return "sent"
            except OTPRateLimitError:
                return "limited"
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: request(), range(4)))
        self.assertEqual(results.count("sent"), 1)
        self.assertEqual(len(SandboxSMSProvider.outbox), 1)

    def test_simultaneous_valid_verifications_consume_code_once(self):
        OTPService.request_otp("09121114444")
        code = SandboxSMSProvider.outbox[0]["code"]
        def verify():
            try:
                OTPService.verify_otp("09121114444", code)
                return "accepted"
            except (OTPInvalidError, OTPRateLimitError):
                return "rejected"
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: verify(), range(3)))
        self.assertEqual(results.count("accepted"), 1)

    @patch("apps.accounts.services.sms_provider.SandboxSMSProvider.send_otp", side_effect=SMSDeliveryError("failed"))
    def test_provider_failure_still_consumes_admission(self, provider):
        with self.assertRaises(SMSDeliveryError):
            OTPService.request_otp("09121114444")
        with self.assertRaises(OTPRateLimitError):
            OTPService.request_otp("09121114444")
        self.assertEqual(provider.call_count, 1)
