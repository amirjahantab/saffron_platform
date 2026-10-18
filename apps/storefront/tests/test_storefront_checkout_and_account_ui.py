"""
End-to-End Storefront UI Tests for Sub-phase 6.2 (Completing Phase 6):
1. Guest adds saffron variant to cart -> views `/cart/` with real Toman subtotal, shipping cost, and payable amount.
2. Guest navigates to `/checkout/` -> redirected to `/auth/login/?next=/checkout/`.
3. Guest completes 2-step OTP login on `/auth/login/` -> guest cart automatically merges into user account cart.
4. Authenticated user submits `/checkout/` with invalid postal code -> form renders inline Persian error message.
5. Authenticated user submits valid `/checkout/` -> Order created, stock reserved, redirected to `/account/orders/<order_number>/`.
6. User initiates payment (`POST /account/orders/<order_number>/pay/`), views `/payments/sandbox-gateway/<authority>/`,
   and completes server-verified callback on `/payments/result/sandbox/` -> Order marked PAID & receipt rendered.
7. User cancels a pending order on `/account/orders/<order_number>/cancel/` -> stock restored.
8. Strict IDOR protection on `/account/orders/<order_number>/` (other users receive HTTP 404).
"""
from decimal import Decimal
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from apps.accounts.models import User
from apps.accounts.services.sms_provider import SandboxSMSProvider
from apps.catalog.models import (
    HarvestBatch,
    PackagingType,
    Product,
    ProductVariant,
    SaffronGrade,
)
from apps.orders.models import Order
from apps.payments.gateways.sandbox import SandboxPaymentGateway


class StorefrontFullPurchaseJourneyUITests(TestCase):
    """Verify the complete customer journey from viewing a product to checkout, payment, and account tracking."""

    def setUp(self) -> None:
        cache.clear()
        SandboxSMSProvider.clear_outbox()
        SandboxPaymentGateway.clear_state()

        self.packaging = PackagingType.objects.create(
            name="خاتم سلطنتی",
            slug="royal-khatam-e2e",
            material="فلزی",
            tare_weight_grams=Decimal("25.00"),
            is_gift_suitable=True,
        )
        self.batch = HarvestBatch.objects.create(
            batch_code="JHT-1405-E2E-01",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            origin_region="قائنات",
            harvest_year=1405,
        )
        self.product = Product.objects.create(
            name="زعفران سوپر نگین صادراتی جهانتاب",
            slug="jahantab-export-super-negin",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            short_description="زعفران سوپر نگین آزمایش‌شده",
            description="توضیحات کامل زعفران سوپر نگین.",
            is_active=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packaging_type=self.packaging,
            harvest_batch=self.batch,
            sku="SN-E2E-1M",
            net_weight_grams=Decimal("4.608"),
            weight_label="۱ مثقال",
            base_price_rial=4_500_000,        # 450,000 Tomans
            discounted_price_rial=4_000_000,  # 400,000 Tomans
            stock_quantity=10,
            min_order_quantity=1,
            max_order_quantity=5,
            is_active=True,
        )

    def test_complete_customer_journey_from_guest_cart_to_otp_login_checkout_and_payment(self) -> None:
        # 1. Guest adds 2 units of variant (2 * 400,000 = 800,000 Tomans) to cart
        add_resp = self.client.post(
            reverse("storefront:cart_add"),
            data={
                "variant_public_id": str(self.variant.public_id),
                "quantity": 2,
                "next": reverse("storefront:cart_page"),
            },
            follow=True,
        )
        self.assertEqual(add_resp.status_code, 200)
        cart_html = add_resp.content.decode("utf-8")
        # 800,000 Tomans items + 45,000 Tomans shipping = 845,000 Tomans payable
        self.assertIn("۸۰۰,۰۰۰ تومان", cart_html)
        self.assertIn("۸۴۵,۰۰۰ تومان", cart_html)

        # 2. Guest attempts to access /checkout/ -> redirected to /auth/login/?next=/checkout/
        checkout_get_guest = self.client.get(reverse("storefront:checkout_page"))
        self.assertEqual(checkout_get_guest.status_code, 302)
        self.assertIn(reverse("storefront:login_page"), checkout_get_guest["Location"])

        # 3. Guest requests OTP on /auth/login/
        login_url = reverse("storefront:login_page")
        req_otp_resp = self.client.post(
            login_url,
            data={
                "action": "request_otp",
                "phone_number": "۰۹۱۵۸۸۸۹۹۰۰",
                "next": reverse("storefront:checkout_page"),
            },
        )
        self.assertEqual(req_otp_resp.status_code, 200)
        self.assertEqual(len(SandboxSMSProvider.outbox), 1)
        otp_code = SandboxSMSProvider.outbox[0]["code"]

        # 4. Guest verifies OTP on /auth/login/ -> logs in, merges guest cart, redirects to /checkout/
        verify_otp_resp = self.client.post(
            login_url,
            data={
                "action": "verify_otp",
                "phone_number": "09158889900",
                "code": otp_code,
                "next": reverse("storefront:checkout_page"),
            },
            follow=True,
        )
        self.assertEqual(verify_otp_resp.status_code, 200)
        checkout_html = verify_otp_resp.content.decode("utf-8")
        self.assertIn("تسویه‌حساب و اطلاعات ارسال", checkout_html)
        self.assertIn("۸۴۵,۰۰۰ تومان", checkout_html)

        # 5. Submit /checkout/ with an invalid postal code -> displays Persian validation error
        bad_checkout_resp = self.client.post(
            reverse("storefront:checkout_page"),
            data={
                "recipient_full_name": "امیررضا جهانتاب",
                "recipient_phone": "09158889900",
                "province": "خراسان رضوی",
                "city": "مشهد",
                "address_line": "مجتمع زعفران سی‌نور",
                "postal_code": "1111111111",  # Invalid repeated digits
                "shipping_method": Order.ShippingMethod.POST_PISHTAZ,
                "idempotency_key": "ui-idem-001",
            },
        )
        self.assertEqual(bad_checkout_resp.status_code, 200)
        self.assertIn("کد پستی واردشده معتبر نیست", bad_checkout_resp.content.decode("utf-8"))

        # 6. Submit /checkout/ with valid address -> creates Order, reserves 2 units (stock: 10 -> 8)
        good_checkout_resp = self.client.post(
            reverse("storefront:checkout_page"),
            data={
                "recipient_full_name": "امیررضا جهانتاب",
                "recipient_phone": "09158889900",
                "province": "خراسان رضوی",
                "city": "مشهد",
                "address_line": "مجتمع زعفران سی‌نور، واحد ۱۲",
                "postal_code": "۹۱۸۸۱-۴۴۵۵۶",
                "save_address": "true",
                "shipping_method": Order.ShippingMethod.POST_PISHTAZ,
                "idempotency_key": "ui-idem-001",
            },
            follow=True,
        )
        self.assertEqual(good_checkout_resp.status_code, 200)
        order = Order.objects.get(user__phone_number="09158889900")
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)

        order_detail_html = good_checkout_resp.content.decode("utf-8")
        self.assertIn(order.order_number, order_detail_html)
        self.assertIn("JHT-1405-E2E-01", order_detail_html)

        # 7. Initiate Payment from Order Detail page (`POST /account/orders/<order_number>/pay/`)
        pay_init_resp = self.client.post(
            reverse("storefront:account_order_pay", kwargs={"order_number": order.order_number}),
            follow=True,
        )
        self.assertEqual(pay_init_resp.status_code, 200)
        sandbox_html = pay_init_resp.content.decode("utf-8")
        self.assertIn("شبیه‌ساز درگاه پرداخت اینترنتی", sandbox_html)

        tx = order.payments.first()
        assert tx is not None

        # 8. Simulate returning from bank to `/payments/result/sandbox/?Authority=...&Status=OK`
        result_resp = self.client.get(
            reverse("storefront:payment_result_page", kwargs={"provider": "sandbox"}),
            {"Authority": tx.authority, "Status": "OK"},
        )
        self.assertEqual(result_resp.status_code, 200)
        receipt_html = result_resp.content.decode("utf-8")
        self.assertIn("پرداخت شما با موفقیت تأیید و ثبت شد", receipt_html)
        self.assertIn("SBX-REF-", receipt_html)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_account_order_cancellation_and_idor_protection(self) -> None:
        owner = User.objects.create_user(phone_number="09157000001", full_name="مالک سفارش")
        intruder = User.objects.create_user(phone_number="09157000002", full_name="کاربر غیرمجاز")

        self.client.force_login(owner)
        self.client.post(
            reverse("storefront:cart_add"),
            data={"variant_public_id": str(self.variant.public_id), "quantity": 3},
        )
        self.client.post(
            reverse("storefront:checkout_page"),
            data={
                "recipient_full_name": "مالک سفارش",
                "recipient_phone": "09157000001",
                "province": "تهران",
                "city": "تهران",
                "address_line": "خیابان ولیعصر",
                "postal_code": "1988776654",
                "shipping_method": Order.ShippingMethod.POST_PISHTAZ,
            },
        )
        order = Order.objects.get(user=owner)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 7)

        # Intruder attempts to view or cancel owner's order -> must get 404
        intruder_client = Client()
        intruder_client.force_login(intruder)
        idor_view = intruder_client.get(
            reverse("storefront:account_order_detail", kwargs={"order_number": order.order_number})
        )
        self.assertEqual(idor_view.status_code, 404)

        idor_cancel = intruder_client.post(
            reverse("storefront:account_order_cancel", kwargs={"order_number": order.order_number})
        )
        self.assertEqual(idor_cancel.status_code, 404)

        # Owner cancels their own order -> status becomes CANCELLED and stock returns to 10
        cancel_resp = self.client.post(
            reverse("storefront:account_order_cancel", kwargs={"order_number": order.order_number}),
            follow=True,
        )
        self.assertEqual(cancel_resp.status_code, 200)
        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.variant.stock_quantity, 10)