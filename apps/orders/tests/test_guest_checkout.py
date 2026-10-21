from django.test import TestCase, Client
from django.core.cache import cache
from apps.core.tests.factories import catalog, user
from apps.orders.models import Order
from apps.accounts.signals import user_logged_in_via_otp


class GuestCheckoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.product, self.variant = catalog()
        self.client.post("/cart/add/", {"variant_public_id": str(self.variant.public_id), "quantity": 1})

    def data(self):
        response = self.client.get("/checkout/guest/")
        return {"recipient_full_name": "مشتری مهمان", "recipient_phone": "09121110001", "province": "خراسان", "city": "مشهد", "address_line": "نشانی مهمان", "postal_code": "9188144556", "shipping_method": "post_pishtaz", "idempotency_key": response.context["form"].initial["idempotency_key"]}

    def test_guest_checkout_payment_and_session_ownership(self):
        data = self.data()
        response = self.client.post("/checkout/guest/", data)
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertIsNone(order.user_id)
        self.assertTrue(order.guest_access_hash)
        receipt = response.headers["Location"]
        self.assertContains(self.client.get(receipt), "مشتری مهمان")
        self.assertEqual(Client().get(receipt).status_code, 404)
        self.assertEqual(Client().post(receipt).status_code, 404)
        response = self.client.post(receipt)
        self.assertEqual(response.status_code, 302)
        tx = order.payments.get()
        response = self.client.get("/payments/result/sandbox/", {"Authority": tx.authority, "Status": "OK"})
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, "paid")

    def test_repeated_checkout_is_idempotent_and_claim_requires_verified_phone(self):
        data = self.data()
        self.client.post("/checkout/guest/", data)
        self.client.post("/checkout/guest/", data)
        self.assertEqual(Order.objects.count(), 1)
        owner = user(is_phone_verified=False)
        user_logged_in_via_otp.send(sender=type(owner), user=owner, request=None)
        order = Order.objects.get()
        self.assertIsNone(order.user_id)
        owner.is_phone_verified = True
        owner.save()
        user_logged_in_via_otp.send(sender=type(owner), user=owner, request=None)
        order.refresh_from_db()
        self.assertEqual(order.user_id, owner.pk)
        self.assertEqual(order.guest_access_hash, "")

    def test_tampered_form_token_does_not_reserve_stock(self):
        data = self.data()
        data["idempotency_key"] = "attacker-controlled"
        self.assertEqual(self.client.post("/checkout/guest/", data).status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 20)
