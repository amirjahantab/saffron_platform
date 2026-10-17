
"""
Comprehensive Integration & Security Tests for Sub-phase 5.2 (Completing Phase 5):
1. Full successful payment flow: Initiate -> Callback -> Server Verify -> Order PAID & StockReservation COMMITTED.
2. Browser Parameter Spoofing Protection: Browser sends `Status=OK`, but server verification fails ->
   Order MUST NOT be marked PAID, PaymentTransaction becomes FAILED, and reserved stock is restored.
3. User Cancellation on Gateway (`Status=NOK`): Releases stock reservation and cancels order.
4. Duplicate / Replay Callback Protection: Calling callback multiple times processes payment once.
5. Overdue Reservation Expiration on Initiate: Attempting to pay an expired order releases stock and rejects payment.
6. Refund Flow & Access Control: Staff refunds a paid order, restoring committed stock and recording PaymentRefund.
"""
from datetime import timedelta
from decimal import Decimal
import json
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User
from apps.catalog.models import (
    HarvestBatch,
    PackagingType,
    Product,
    ProductVariant,
    SaffronGrade,
)
from apps.orders.models import Cart, CartItem, Order, StockReservation
from apps.orders.services.checkout_service import CheckoutService
from apps.payments.gateways.sandbox import SandboxPaymentGateway
from apps.payments.models import PaymentRefund, PaymentTransaction


class PaymentLifecycleAndSecurityTests(TestCase):
    """End-to-end tests for payment initiation, callback verification, stock reservations, and refunds."""

    def setUp(self) -> None:
        SandboxPaymentGateway.clear_state()

        self.customer = User.objects.create_user(phone_number="09153334455", full_name="خریدار اصلی")
        self.other_user = User.objects.create_user(phone_number="09153334466", full_name="کاربر دیگر")
        self.staff_admin = User.objects.create_superuser(
            phone_number="09153334477",
            password="StrongStaffPassword!2026",
            full_name="مدیر مالی",
        )

        self.packaging = PackagingType.objects.create(
            name="خاتم اعلا",
            slug="premium-khatam-pay",
            tare_weight_grams=Decimal("25.00"),
        )
        self.batch = HarvestBatch.objects.create(
            batch_code="JHT-1405-PAY-01",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            origin_region="قائنات",
            harvest_year=1405,
        )
        self.product = Product.objects.create(
            name="زعفران سوپر نگین صادراتی ویژه پرداخت",
            slug="super-negin-pay-test",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            short_description="زعفران سوپر نگین",
            description="توضیحات کامل",
            is_active=True,
        )
        # Initial stock is 10 units
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packaging_type=self.packaging,
            harvest_batch=self.batch,
            sku="SN-PAY-1M",
            net_weight_grams=Decimal("4.608"),
            weight_label="۱ مثقال",
            base_price_rial=4_500_000,
            discounted_price_rial=4_000_000,
            stock_quantity=10,
            min_order_quantity=1,
            max_order_quantity=5,
            is_active=True,
        )

    def _create_order_via_checkout(self, quantity: int = 2) -> Order:
        cart, _ = Cart.objects.get_or_create(user=self.customer, status=Cart.Status.ACTIVE)
        CartItem.objects.update_or_create(
            cart=cart,
            variant=self.variant,
            defaults={"quantity": quantity},
        )
        order, _ = CheckoutService.create_order_from_cart(
            user=self.customer,
            address_data={
                "recipient_full_name": "خریدار اصلی",
                "recipient_phone": "09153334455",
                "province": "خراسان رضوی",
                "city": "مشهد",
                "address_line": "خیابان دانشگاه، پلاک ۵",
                "postal_code": "9188144556",
            },
        )
        return order

    def test_successful_payment_initiation_and_server_verified_callback(self) -> None:
        order = self._create_order_via_checkout(quantity=2)
        # Stock was 10, 2 reserved -> 8 remaining
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)

        self.client.force_login(self.customer)
        init_url = reverse("payments:payment_initiate", kwargs={"order_number": order.order_number})
        init_resp = self.client.post(
            init_url,
            data=json.dumps({"provider": "sandbox", "idempotency_key": "pay-init-001"}),
            content_type="application/json",
        )
        self.assertEqual(init_resp.status_code, 201)
        init_data = init_resp.json()
        authority = init_data["payment"]["authority"]
        self.assertTrue(authority.startswith("SBX-"))
        self.assertIn(authority, init_data["redirect_url"])

        # Simulate gateway callback redirect: GET /payments/callback/sandbox/?Authority=...&Status=OK
        callback_url = reverse("payments:payment_callback", kwargs={"provider": "sandbox"})
        cb_resp = self.client.get(callback_url, {"Authority": authority, "Status": "OK"})
        self.assertEqual(cb_resp.status_code, 200)
        cb_data = cb_resp.json()

        self.assertFalse(cb_data["already_processed"])
        self.assertEqual(cb_data["order_status"], Order.Status.PAID)
        self.assertTrue(cb_data["payment"]["reference_id"].startswith("SBX-REF-"))

        # Verify database states: Order is PAID, Reservation is COMMITTED, Stock stays 8
        order.refresh_from_db()
        self.variant.refresh_from_db()
        reservation = order.reservations.first()
        assert reservation is not None

        self.assertEqual(order.status, Order.Status.PAID)
        self.assertIsNotNone(order.paid_at)
        self.assertEqual(reservation.status, StockReservation.Status.COMMITTED)
        self.assertEqual(self.variant.stock_quantity, 8)

    def test_browser_spoofed_ok_status_is_rejected_when_server_verification_fails(self) -> None:
        """
        ACCEPTANCE CRITERION:
        Merely sending `Status=OK` (or tampered query params) in the browser callback
        MUST NEVER mark an order as paid if server-to-server verification fails.
        """
        order = self._create_order_via_checkout(quantity=3)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 7)

        self.client.force_login(self.customer)
        init_resp = self.client.post(
            reverse("payments:payment_initiate", kwargs={"order_number": order.order_number}),
            data=json.dumps({"provider": "sandbox"}),
            content_type="application/json",
        )
        authority = init_resp.json()["payment"]["authority"]

        # Instruct the sandbox gateway server to reject verification even though browser sends Status=OK
        SandboxPaymentGateway.mark_authority_to_fail_verification(authority)

        callback_url = reverse("payments:payment_callback", kwargs={"provider": "sandbox"})
        spoofed_resp = self.client.get(
            callback_url,
            {
                "Authority": authority,
                "Status": "OK",
                "amount": "10",
                "paid": "true",
                "ref_id": "FAKE-REF-99999",
            },
        )
        self.assertEqual(spoofed_resp.status_code, 400)
        self.assertEqual(spoofed_resp.json()["code"], "server_verification_rejected")

        # Verify Order was NOT marked PAID, transaction is FAILED, and reserved stock returned to 10!
        order.refresh_from_db()
        self.variant.refresh_from_db()
        tx = PaymentTransaction.objects.get(authority=authority)
        reservation = order.reservations.first()
        assert reservation is not None

        self.assertNotEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(tx.status, PaymentTransaction.Status.FAILED)
        self.assertIsNone(tx.reference_id)
        self.assertEqual(reservation.status, StockReservation.Status.RELEASED)
        self.assertEqual(self.variant.stock_quantity, 10)

    def test_user_cancelled_callback_nok_marks_payment_failed_and_restores_stock(self) -> None:
        order = self._create_order_via_checkout(quantity=2)
        self.client.force_login(self.customer)

        init_resp = self.client.post(
            reverse("payments:payment_initiate", kwargs={"order_number": order.order_number}),
            data=json.dumps({"provider": "sandbox"}),
            content_type="application/json",
        )
        authority = init_resp.json()["payment"]["authority"]

        # Browser returns with Status=NOK (user clicked cancel on payment page)
        callback_url = reverse("payments:payment_callback", kwargs={"provider": "sandbox"})
        cb_resp = self.client.get(callback_url, {"Authority": authority, "Status": "NOK"})
        self.assertEqual(cb_resp.status_code, 400)
        self.assertEqual(cb_resp.json()["code"], "payment_cancelled_by_user")

        order.refresh_from_db()
        self.variant.refresh_from_db()
        tx = PaymentTransaction.objects.get(authority=authority)

        self.assertEqual(tx.status, PaymentTransaction.Status.FAILED)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.variant.stock_quantity, 10)

    def test_duplicate_callback_replay_is_idempotent_and_processed_only_once(self) -> None:
        order = self._create_order_via_checkout(quantity=2)
        self.client.force_login(self.customer)

        init_resp = self.client.post(
            reverse("payments:payment_initiate", kwargs={"order_number": order.order_number}),
            data=json.dumps({"provider": "sandbox"}),
            content_type="application/json",
        )
        authority = init_resp.json()["payment"]["authority"]
        callback_url = reverse("payments:payment_callback", kwargs={"provider": "sandbox"})

        # First callback
        cb_resp_1 = self.client.get(callback_url, {"Authority": authority, "Status": "OK"})
        self.assertEqual(cb_resp_1.status_code, 200)
        self.assertFalse(cb_resp_1.json()["already_processed"])
        ref_id_1 = cb_resp_1.json()["payment"]["reference_id"]

        # Second callback (user refreshes browser or gateway retries webhook)
        cb_resp_2 = self.client.get(callback_url, {"Authority": authority, "Status": "OK"})
        self.assertEqual(cb_resp_2.status_code, 200)
        self.assertTrue(cb_resp_2.json()["already_processed"])
        self.assertEqual(cb_resp_2.json()["payment"]["reference_id"], ref_id_1)

        # Ensure stock was deducted only once (10 - 2 = 8)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)
        self.assertEqual(PaymentTransaction.objects.filter(order=order, status="succeeded").count(), 1)

    def test_initiating_payment_on_expired_order_releases_stock_and_rejects_request(self) -> None:
        order = self._create_order_via_checkout(quantity=4)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 6)

        # Fast-forward order reservation expiry into the past
        Order.objects.filter(pk=order.pk).update(
            reservation_expires_at=timezone.now() - timedelta(minutes=2)
        )

        self.client.force_login(self.customer)
        init_resp = self.client.post(
            reverse("payments:payment_initiate", kwargs={"order_number": order.order_number}),
            data=json.dumps({"provider": "sandbox"}),
            content_type="application/json",
        )
        self.assertEqual(init_resp.status_code, 400)
        self.assertEqual(init_resp.json()["code"], "order_reservation_expired")

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.EXPIRED)
        self.assertEqual(self.variant.stock_quantity, 10)

    def test_refund_flow_restores_stock_and_enforces_staff_authorization(self) -> None:
        order = self._create_order_via_checkout(quantity=2)
        self.client.force_login(self.customer)

        init_resp = self.client.post(
            reverse("payments:payment_initiate", kwargs={"order_number": order.order_number}),
            data=json.dumps({"provider": "sandbox"}),
            content_type="application/json",
        )
        authority = init_resp.json()["payment"]["authority"]
        self.client.get(
            reverse("payments:payment_callback", kwargs={"provider": "sandbox"}),
            {"Authority": authority, "Status": "OK"},
        )

        # Stock is now 8 (COMMITTED)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)

        # 1. IDOR check on payment status: other_user cannot view customer's order payment status
        other_client = Client()
        other_client.force_login(self.other_user)
        idor_status_resp = other_client.get(
            reverse("payments:order_payment_status", kwargs={"order_number": order.order_number})
        )
        self.assertEqual(idor_status_resp.status_code, 404)

        # 2. Regular customer cannot call the staff refund endpoint (403 Forbidden)
        refund_url = reverse("payments:order_payment_refund", kwargs={"order_number": order.order_number})
        customer_refund_resp = self.client.post(
            refund_url,
            data=json.dumps({"reason": "تلاش غیرمجاز مشتری"}),
            content_type="application/json",
        )
        self.assertEqual(customer_refund_resp.status_code, 403)

        # 3. Staff admin executes full refund -> succeeds, creates PaymentRefund, restores stock to 10
        staff_client = Client()
        staff_client.force_login(self.staff_admin)
        staff_refund_resp = staff_client.post(
            refund_url,
            data=json.dumps({"reason": "درخواست استرداد پیش از ارسال مرسوله"}),
            content_type="application/json",
        )
        self.assertEqual(staff_refund_resp.status_code, 200)
        refund_data = staff_refund_resp.json()
        self.assertEqual(refund_data["order_status"], Order.Status.REFUNDED)
        self.assertEqual(refund_data["refund"]["amount_rial"], order.payable_rial)

        order.refresh_from_db()
        self.variant.refresh_from_db()
        tx = PaymentTransaction.objects.get(authority=authority)
        self.assertEqual(order.status, Order.Status.REFUNDED)
        self.assertEqual(tx.status, PaymentTransaction.Status.REFUNDED)
        self.assertEqual(PaymentRefund.objects.filter(order=order, status="succeeded").count(), 1)
        self.assertEqual(self.variant.stock_quantity, 10)