from django.test import TestCase, Client
from django.core.exceptions import ValidationError
from apps.core.tests.factories import user, catalog, paid_order
from .models import Ticket, Reply, Review


class CareSecurityTests(TestCase):
    def setUp(self):
        self.user = user()
        self.other = user("09121110002")
        self.product, self.variant = catalog()
        self.client.force_login(self.user)

    def test_support_cannot_read_other_ticket_or_internal_notes(self):
        ticket = Ticket.objects.create(user=self.other, subject="خصوصی")
        self.assertEqual(self.client.get(f"/support/{ticket.public_id}/").status_code, 404)
        own = Ticket.objects.create(user=self.user, subject="آشکار")
        Reply.objects.create(ticket=own, author=self.other, body="راز داخلی", is_internal=True)
        Reply.objects.create(ticket=own, author=self.other, body="پاسخ قابل نمایش")
        response = self.client.get(f"/support/{own.public_id}/")
        self.assertNotContains(response, "راز داخلی")
        self.assertContains(response, "پاسخ قابل نمایش")

    def test_cannot_attach_another_users_order(self):
        order = paid_order(self.other, self.variant)
        response = self.client.post("/support/", {"subject": "test", "body": "hello", "order": order.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_ticket_flow_and_escaping(self):
        response = self.client.post("/support/", {"subject": "پرسش", "body": "<script>bad()</script>"})
        self.assertEqual(response.status_code, 302)
        response = self.client.get(response.headers["Location"])
        self.assertNotContains(response, "<script>bad()</script>")
        self.assertContains(response, "&lt;script&gt;")
        self.assertIn("noindex", response.headers["X-Robots-Tag"])

    def test_review_requires_paid_purchase_and_moderation(self):
        data = {"rating": 5, "title": "تجربه من", "body": "این تجربه خصوصی ثبت‌شده است"}
        self.client.post(f"/reviews/{self.product.slug}/", data)
        self.assertEqual(Review.objects.count(), 0)
        paid_order(self.user, self.variant)
        self.client.post(f"/reviews/{self.product.slug}/", data)
        review = Review.objects.get()
        self.assertTrue(review.verified_purchase)
        self.assertFalse(review.is_approved)
        response = self.client.get(f"/shop/{self.product.slug}/")
        self.assertNotContains(response, "این تجربه خصوصی ثبت‌شده است")
        review.is_approved = True
        review.save()
        self.assertContains(self.client.get(f"/shop/{self.product.slug}/"), "این تجربه خصوصی ثبت‌شده است")
        self.client.post(f"/reviews/{self.product.slug}/", data)
        self.assertEqual(Review.objects.count(), 1)

    def test_invalid_rating_is_rejected(self):
        paid_order(self.user, self.variant)
        self.client.post(f"/reviews/{self.product.slug}/", {"rating": 9, "title": "x", "body": "x"})
        self.assertEqual(Review.objects.count(), 0)

    def test_support_requires_login_and_csrf(self):
        self.assertEqual(Client().get("/support/").status_code, 302)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.user)
        self.assertEqual(secure.post("/support/", {"subject": "x", "body": "x"}).status_code, 403)
