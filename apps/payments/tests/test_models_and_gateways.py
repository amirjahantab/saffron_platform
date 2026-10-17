"""
Unit & Security Tests for Sub-phase 5.1:
- PaymentTransaction & PaymentRefund models, Rial/Toman contract, and DB uniqueness constraints
- ZarinpalV4Gateway official v4 REST protocol (request, verify code 100, idempotent verify code 101, error codes, network timeout)
- SandboxPaymentGateway deterministic flow, amount mismatch detection, and forced failure simulation
- Gateway registry resolution
"""
from datetime import timedelta
from decimal import Decimal
import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.orders.models import Order
from apps.payments.exceptions import (
    PaymentConfigurationError,
    PaymentGatewayCommunicationError,
    PaymentGatewayRejectionError,
)
from apps.payments.gateways.registry import get_payment_gateway
from apps.payments.gateways.sandbox import SandboxPaymentGateway
from apps.payments.gateways.zarinpal import ZarinpalV4Gateway
from apps.payments.models import (
    PaymentProvider,
    PaymentRefund,
    PaymentTransaction,
)


class PaymentModelsAndConstraintsTests(TestCase):
    """Test financial constraints, Rial/Toman conversions, and DB uniqueness rules on Payment models."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(phone_number="09154445566", full_name="خریدار زعفران")
        self.order = Order.objects.create(
            user=self.user,
            recipient_full_name="خریدار زعفران",
            recipient_phone="09154445566",
            province="خراسان رضوی",
            city="مشهد",
            address_line="بلوار فردوسی",
            postal_code="9188144556",
            total_gross_weight_grams=Decimal("40.000"),
            subtotal_base_rial=8_000_000,
            total_discount_rial=500_000,
            shipping_cost_rial=450_000,
            payable_rial=7_950_000,  # 795,000 Tomans
            reservation_expires_at=timezone.now() + timedelta(minutes=15),
        )

    def test_payment_transaction_rial_toman_properties_and_amount_match_validation(self) -> None:
        tx = PaymentTransaction(
            order=self.order,
            provider=PaymentProvider.SANDBOX,
            amount_rial=7_950_000,
            authority="SBX-AUTH-001",
        )
        tx.full_clean()
        tx.save()

        self.assertEqual(tx.amount_toman, 795_000)
        self.assertEqual(tx.formatted_amount_toman, "۷۹۵,۰۰۰ تومان")

        # Mismatched amount_rial (different from order.payable_rial) must fail validation
        bad_tx = PaymentTransaction(
            order=self.order,
            provider=PaymentProvider.SANDBOX,
            amount_rial=1_000_000,
            authority="SBX-AUTH-002",
        )
        with self.assertRaises(ValidationError) as ctx:
            bad_tx.full_clean()
        self.assertIn("amount_rial", ctx.exception.message_dict)

    def test_at_most_one_succeeded_payment_per_order_constraint(self) -> None:
        PaymentTransaction.objects.create(
            order=self.order,
            provider=PaymentProvider.SANDBOX,
            status=PaymentTransaction.Status.SUCCEEDED,
            amount_rial=self.order.payable_rial,
            authority="SBX-AUTH-SUCCESS-1",
            reference_id="REF-1001",
        )

        # Multiple FAILED transactions for the same order are allowed
        PaymentTransaction.objects.create(
            order=self.order,
            provider=PaymentProvider.SANDBOX,
            status=PaymentTransaction.Status.FAILED,
            amount_rial=self.order.payable_rial,
            authority="SBX-AUTH-FAIL-1",
        )

        # A second SUCCEEDED transaction for the same order must be blocked by DB constraint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PaymentTransaction.objects.create(
                    order=self.order,
                    provider=PaymentProvider.SANDBOX,
                    status=PaymentTransaction.Status.SUCCEEDED,
                    amount_rial=self.order.payable_rial,
                    authority="SBX-AUTH-SUCCESS-2",
                    reference_id="REF-1002",
                )

    def test_payment_refund_validation_prevents_over_refunding(self) -> None:
        tx = PaymentTransaction.objects.create(
            order=self.order,
            provider=PaymentProvider.SANDBOX,
            status=PaymentTransaction.Status.SUCCEEDED,
            amount_rial=self.order.payable_rial,
            authority="SBX-AUTH-RFD",
            reference_id="REF-RFD-01",
        )

        # Refund exceeding payment amount_rial must be rejected
        bad_refund = PaymentRefund(
            payment=tx,
            order=self.order,
            amount_rial=self.order.payable_rial + 100_000,
            reason="اضافه‌پرداخت غیرمجاز",
        )
        with self.assertRaises(ValidationError) as ctx:
            bad_refund.full_clean()
        self.assertIn("amount_rial", ctx.exception.message_dict)

        # Valid refund passes
        valid_refund = PaymentRefund(
            payment=tx,
            order=self.order,
            amount_rial=self.order.payable_rial,
            reason="لغو سفارش به درخواست مشتری",
        )
        valid_refund.full_clean()
        valid_refund.save()
        self.assertEqual(valid_refund.amount_toman, 795_000)


class ZarinpalV4GatewayProtocolTests(TestCase):
    """Test Zarinpal v4 adapter request/verify protocol using mocked HTTP responses."""

    def setUp(self) -> None:
        self.gateway = ZarinpalV4Gateway(
            merchant_id="11111111-2222-3333-4444-555555555555",
            sandbox=True,
            timeout_seconds=5,
        )

    @staticmethod
    def _mock_urlopen_json(response_dict: dict) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_dict).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        return mock_resp

    @patch("apps.payments.gateways.zarinpal.urlopen")
    def test_zarinpal_request_payment_sends_irr_and_parses_authority(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = self._mock_urlopen_json(
            {
                "data": {
                    "code": 100,
                    "message": "Success",
                    "authority": "A00000000000000000000000000123456789",
                    "fee_type": "Merchant",
                    "fee": 5000,
                },
                "errors": [],
            }
        )

        result = self.gateway.request_payment(
            amount_rial=7_950_000,
            callback_url="http://127.0.0.1:8000/payments/callback/zarinpal/",
            description="پرداخت سفارش JHT-100",
            order_number="JHT-100",
            customer_phone="09154445566",
        )

        self.assertEqual(result.authority, "A00000000000000000000000000123456789")
        self.assertIn("/pg/StartPay/A00000000000000000000000000123456789", result.redirect_url)
        self.assertEqual(result.fee_rial, 5000)

        # Verify sent payload contains explicit currency="IRR" and exact Rial amount
        sent_req = mock_urlopen.call_args[0][0]
        sent_body = json.loads(sent_req.data.decode("utf-8"))
        self.assertEqual(sent_body["currency"], "IRR")
        self.assertEqual(sent_body["amount"], 7_950_000)
        self.assertEqual(sent_body["metadata"]["order_id"], "JHT-100")

    @patch("apps.payments.gateways.zarinpal.urlopen")
    def test_zarinpal_verify_payment_handles_code_100_and_101_and_failures(self, mock_urlopen: MagicMock) -> None:
        # 1. Code 100 (First-time verification)
        mock_urlopen.return_value = self._mock_urlopen_json(
            {
                "data": {
                    "code": 100,
                    "message": "Verified",
                    "card_hash": "ABC123HASH",
                    "card_pan": "603799******1122",
                    "ref_id": 987654321,
                    "fee_type": "Merchant",
                    "fee": 0,
                },
                "errors": [],
            }
        )
        res_100 = self.gateway.verify_payment(
            authority="A00000000000000000000000000123456789",
            expected_amount_rial=7_950_000,
        )
        self.assertTrue(res_100.is_verified)
        self.assertFalse(res_100.already_verified)
        self.assertEqual(res_100.reference_id, "987654321")
        self.assertEqual(res_100.card_pan_masked, "603799******1122")

        # 2. Code 101 (Already verified -> idempotent success)
        mock_urlopen.return_value = self._mock_urlopen_json(
            {
                "data": {
                    "code": 101,
                    "message": "Verified",
                    "card_hash": "ABC123HASH",
                    "card_pan": "603799******1122",
                    "ref_id": 987654321,
                    "fee_type": "Merchant",
                    "fee": 0,
                },
                "errors": [],
            }
        )
        res_101 = self.gateway.verify_payment(
            authority="A00000000000000000000000000123456789",
            expected_amount_rial=7_950_000,
        )
        self.assertTrue(res_101.is_verified)
        self.assertTrue(res_101.already_verified)

        # 3. Failed verification (e.g. code -51)
        mock_urlopen.return_value = self._mock_urlopen_json(
            {
                "data": [],
                "errors": {
                    "code": -51,
                    "message": "Session is not valid, session is not active paid try.",
                },
            }
        )
        res_fail = self.gateway.verify_payment(
            authority="A00000000000000000000000000123456789",
            expected_amount_rial=7_950_000,
        )
        self.assertFalse(res_fail.is_verified)
        self.assertEqual(res_fail.failure_code, "-51")

    @patch("apps.payments.gateways.zarinpal.urlopen", side_effect=URLError("Connection timed out"))
    def test_zarinpal_network_timeout_raises_communication_error(self, _mock_urlopen: MagicMock) -> None:
        with self.assertRaises(PaymentGatewayCommunicationError):
            self.gateway.request_payment(
                amount_rial=500_000,
                callback_url="http://127.0.0.1:8000/callback/",
                description="Test",
                order_number="JHT-101",
            )


class SandboxGatewayAndRegistryTests(TestCase):
    """Test deterministic SandboxPaymentGateway and provider registry."""

    def setUp(self) -> None:
        SandboxPaymentGateway.clear_state()

    def test_sandbox_gateway_request_verify_and_amount_mismatch_protection(self) -> None:
        gw = get_payment_gateway("sandbox")
        req_res = gw.request_payment(
            amount_rial=4_500_000,
            callback_url="http://127.0.0.1:8000/callback/",
            description="سفارش تستی",
            order_number="JHT-SBX-01",
        )
        self.assertTrue(req_res.authority.startswith("SBX-"))

        # Tampered amount verification must fail
        mismatch_res = gw.verify_payment(
            authority=req_res.authority,
            expected_amount_rial=9_000_000,
        )
        self.assertFalse(mismatch_res.is_verified)
        self.assertEqual(mismatch_res.failure_code, "-50")

        # First verification with exact amount succeeds (code 100 -> already_verified=False)
        verify_1 = gw.verify_payment(
            authority=req_res.authority,
            expected_amount_rial=4_500_000,
        )
        self.assertTrue(verify_1.is_verified)
        self.assertFalse(verify_1.already_verified)
        self.assertTrue(verify_1.reference_id.startswith("SBX-REF-"))

        # Second verification with same authority succeeds with already_verified=True (code 101)
        verify_2 = gw.verify_payment(
            authority=req_res.authority,
            expected_amount_rial=4_500_000,
        )
        self.assertTrue(verify_2.is_verified)
        self.assertTrue(verify_2.already_verified)
        self.assertEqual(verify_1.reference_id, verify_2.reference_id)

    def test_registry_rejects_unknown_gateway_provider(self) -> None:
        with self.assertRaises(PaymentConfigurationError):
            get_payment_gateway("non_existent_gateway")