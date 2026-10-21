from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from apps.accounts.models import User
from apps.core.tests.factories import user, catalog, paid_order
from apps.payments.refunds import record_bank_refund
from apps.payments.models import PaymentRefund
from apps.payments.services.payment_service import PaymentService
from apps.payments.gateways.zarinpal import ZarinpalV4Gateway
from apps.insights.services import revenue_report


class RefundSafetyTests(TestCase):
    def setUp(self):
        self.owner = user()
        self.product, self.variant = catalog()
        self.order = paid_order(self.owner, self.variant)
        self.operator = User.objects.create_superuser("09121110003", password="test-operator-password-unique")

    def test_zarinpal_never_reports_an_unexecuted_refund_as_success(self):
        result = ZarinpalV4Gateway().refund_payment(authority="authority", reference_id="reference", amount_rial=100000)
        self.assertFalse(result.is_succeeded)
        self.assertEqual(result.provider_refund_id, "")

    def test_partial_refund_preserves_order_and_inventory_until_full_refund(self):
        self.variant.refresh_from_db()
        before = self.variant.stock_quantity
        PaymentService.refund_order_payment(order=self.order, amount_rial=100000, reason="partial", actor=self.operator)
        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertEqual(self.variant.stock_quantity, before)
        self.assertEqual(revenue_report()["net_rial"], self.order.payable_rial-100000)
        PaymentService.refund_order_payment(order=self.order, amount_rial=self.order.payable_rial-100000, reason="remaining", actor=self.operator)
        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(self.order.status, "refunded")
        self.assertEqual(self.variant.stock_quantity, before+1)

    def test_bank_refund_requires_authorized_operator_and_unique_receipt(self):
        args = dict(order=self.order, reference="BANK-UNIQUE-123", amount_rial=100000, reason="manual", evidence_note="رسید انتقال بانکی با حساب فروشگاه مطابقت داده شد")
        with self.assertRaises(PermissionDenied):
            record_bank_refund(actor=self.owner, **args)
        record_bank_refund(actor=self.operator, **args)
        with self.assertRaises(ValidationError):
            record_bank_refund(actor=self.operator, **args)
        self.assertEqual(PaymentRefund.objects.count(), 1)

    def test_browser_callback_gets_receipt_while_foreign_json_caller_gets_no_details(self):
        from apps.payments.models import PaymentTransaction
        from apps.orders.models import Order
        from apps.payments.gateways.sandbox import SandboxPaymentGateway
        from unittest.mock import patch
        tx = self.order.payments.get()
        with patch.object(PaymentService, "process_callback", return_value=(tx, True)):
            response = self.client.get("/payments/callback/sandbox/", {"Authority": tx.authority, "Status": "OK"})
            self.assertNotIn("payment", response.json())
            self.assertNotIn("order_number", response.json())
            self.client.force_login(self.owner)
            response = self.client.get("/payments/callback/sandbox/", {"Authority": tx.authority, "Status": "OK"}, HTTP_ACCEPT="text/html")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/payments/result/sandbox/", response.headers["Location"])
