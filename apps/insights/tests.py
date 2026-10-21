from datetime import timedelta
from io import StringIO
from django.test import TestCase, override_settings
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from apps.core.tests.factories import user, catalog, paid_order
from apps.orders.models import Cart, CartItem
from .models import Event, Preference, Notification
from .services import revenue_report


class InsightsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = user()
        self.product, self.variant = catalog()

    def test_analytics_is_opt_in_and_search_text_is_not_retained(self):
        self.client.get(f"/shop/{self.product.slug}/")
        self.assertEqual(Event.objects.count(), 0)
        self.client.post("/preferences/", {"analytics": "on"})
        self.client.get(f"/shop/{self.product.slug}/?utm_source=mail&utm_campaign=autumn")
        event = Event.objects.get(kind="product_view")
        self.assertEqual(event.source, "mail")
        self.assertEqual(event.campaign, "autumn")
        self.assertNotEqual(event.visitor, self.client.session.session_key)
        self.client.get("/shop/?q=private-09121110001")
        self.assertTrue(Event.objects.filter(kind="search").exists())
        self.assertNotIn("09121110001", str(list(Event.objects.values())))

    def test_withdrawing_consent_removes_current_session_telemetry(self):
        self.client.post("/preferences/", {"analytics": "on"})
        self.client.get(f"/shop/{self.product.slug}/")
        self.assertEqual(Event.objects.count(), 1)
        self.client.post("/preferences/", {})
        self.assertEqual(Event.objects.count(), 0)

    def test_purchase_event_and_notification_are_idempotent(self):
        order = paid_order(self.owner, self.variant)
        order.save()
        order.save()
        self.assertEqual(Event.objects.filter(kind="purchase", order=order).count(), 1)
        self.assertEqual(Notification.objects.filter(order=order).count(), 1)
        report = revenue_report()
        self.assertEqual(report["paid_orders"], 1)
        self.assertEqual(report["net_rial"], order.payable_rial)

    def test_abandoned_reminders_require_consent_and_deduplicate(self):
        cart = Cart.objects.create(user=self.owner)
        item = CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)
        CartItem.objects.filter(pk=item.pk).update(updated_at=timezone.now()-timedelta(days=2))
        call_command("queue_abandoned_carts", stdout=StringIO())
        self.assertEqual(Notification.objects.count(), 0)
        Preference.objects.create(user=self.owner, marketing=True)
        call_command("queue_abandoned_carts", stdout=StringIO())
        call_command("queue_abandoned_carts", stdout=StringIO())
        self.assertEqual(Notification.objects.count(), 1)

    @override_settings(NOTIFICATIONS_ENABLED=True)
    def test_revoked_marketing_is_cancelled_before_delivery(self):
        preference = Preference.objects.create(user=self.owner, marketing=False)
        cart = Cart.objects.create(user=self.owner)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)
        notice = Notification.objects.create(user=self.owner, key=f"cart:{cart.pk}:reminder", marketing=True, message="hello")
        call_command("dispatch_notifications", stdout=StringIO())
        notice.refresh_from_db()
        self.assertEqual(notice.status, "cancelled")

    @override_settings(NOTIFICATIONS_ENABLED=True)
    def test_transactional_delivery_and_retries_are_idempotent(self):
        order = paid_order(self.owner, self.variant)
        call_command("dispatch_notifications", stdout=StringIO())
        call_command("dispatch_notifications", stdout=StringIO())
        notice = Notification.objects.get(order=order)
        self.assertEqual(notice.status, "sent")
        self.assertEqual(notice.attempts, 1)

    def test_dashboard_rejects_customer_and_staff_without_permission(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get("/staff/insights/").status_code, 302)
        self.owner.is_staff = True
        self.owner.save()
        self.assertEqual(self.client.get("/staff/insights/").status_code, 403)

    def test_retention_keeps_financial_records(self):
        order = paid_order(self.owner, self.variant)
        Event.objects.all().update(created_at=timezone.now()-timedelta(days=100))
        call_command("prune_private_data", stdout=StringIO())
        self.assertEqual(Event.objects.count(), 0)
        self.assertEqual(revenue_report()["net_rial"], order.payable_rial)

    def test_campaign_attribution_survives_checkout_until_consent_is_revoked(self):
        from .models import OrderAttribution
        self.client.force_login(self.owner)
        self.client.post("/preferences/", {"analytics": "on"})
        self.client.get(f"/shop/{self.product.slug}/?utm_source=mail&utm_campaign=fall")
        self.client.post("/cart/add/", {"variant_public_id": str(self.variant.public_id), "quantity": 1})
        response = self.client.post("/checkout/", {"recipient_full_name": "تست", "recipient_phone": self.owner.phone_number, "province": "خراسان", "city": "مشهد", "address_line": "نشانی تست", "postal_code": "9188144556", "shipping_method": "post_pishtaz"})
        self.assertEqual(response.status_code, 302)
        attribution = OrderAttribution.objects.get()
        self.assertEqual(attribution.source, "mail")
        self.assertEqual(attribution.campaign, "fall")
        self.client.post("/preferences/", {})
        self.assertEqual(OrderAttribution.objects.count(), 0)
