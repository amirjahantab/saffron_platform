from io import StringIO
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from apps.core.models import DemoDataset
from apps.accounts.models import User


class LaunchGateTests(TestCase):
    def test_launch_gate_blocks_demo_missing_business_content_and_providers(self):
        DemoDataset.objects.create(name="catalog")
        with self.assertRaises(CommandError) as error:
            call_command("verify_launch", stdout=StringIO())
        self.assertIn("demo seed markers", str(error.exception))
        self.assertIn("Publish actual business policies", str(error.exception))

    @override_settings(DEMO_MODE=False)
    def test_demo_seed_is_forbidden_outside_demo_mode(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo_catalog", stdout=StringIO())

    def test_financial_admin_cannot_add_or_mutate_financial_fields(self):
        from apps.payments.admin import PaymentTransactionAdmin, PaymentRefundAdmin
        from apps.payments.models import PaymentTransaction, PaymentRefund
        from apps.orders.admin import OrderAdmin
        from apps.orders.models import Order
        from django.contrib.admin.sites import AdminSite
        for admin_cls, model in [(PaymentTransactionAdmin, PaymentTransaction), (PaymentRefundAdmin, PaymentRefund), (OrderAdmin, Order)]:
            instance = admin_cls(model, AdminSite())
            self.assertFalse(instance.has_add_permission(None))
            readonly = instance.get_readonly_fields(None)
            self.assertIn("status", readonly)

    def test_manual_bank_refund_admin_requires_specific_permission(self):
        staff = User.objects.create_user("09121110001", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/admin/payments/paymentrefund/record-bank/").status_code, 403)

    @override_settings(ENABLE_ACTION_LIMITS=True, ACTION_LIMITS={"storefront:cart_add": (2, 60)})
    def test_sensitive_action_limiter_blocks_excess_and_sets_retry_after(self):
        from django.core.cache import cache
        cache.clear()
        self.assertEqual(self.client.post("/cart/add/", {}).status_code, 302)
        self.assertEqual(self.client.post("/cart/add/", {}).status_code, 302)
        response = self.client.post("/cart/add/", {})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "60")
        self.assertIn("noindex", response.headers["X-Robots-Tag"])

    @override_settings(DEMO_MODE=False, STORE_OPEN=False)
    def test_closed_live_store_cannot_create_orders(self):
        response = self.client.post("/checkout/guest/", {})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.post("/orders/checkout/", {}, content_type="application/json").status_code, 503)
        from .factories import catalog
        product, _ = catalog()
        response = self.client.get(f"/shop/{product.slug}/")
        self.assertContains(response, "آغاز فروش به‌زودی")
        self.assertNotContains(response, '"@type": "Offer"')
