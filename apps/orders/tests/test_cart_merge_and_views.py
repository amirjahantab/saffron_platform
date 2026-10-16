"""Integration and security tests for cart endpoints, price-tampering protection, and OTP cart merging."""
import json
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
from apps.orders.models import Cart, CartItem


class CartEndpointsAndMergeSecurityTests(TestCase):
    """Test HTTP cart endpoints, price tampering immunity, and automatic guest-to-user merge on OTP login."""

    def setUp(self) -> None:
        cache.clear()
        SandboxSMSProvider.clear_outbox()

        self.packaging = PackagingType.objects.create(
            name="پاکتی سوغات",
            slug="gift-packet",
            tare_weight_grams=Decimal("8.00"),
        )
        self.batch = HarvestBatch.objects.create(
            batch_code="JHT-1405-CART-02",
            saffron_grade=SaffronGrade.NEGIN,
            origin_region="تربت حیدریه",
            harvest_year=1405,
        )
        self.product = Product.objects.create(
            name="زعفران نگین درجه یک",
            slug="grade-one-negin",
            saffron_grade=SaffronGrade.NEGIN,
            short_description="زعفران نگین",
            description="توضیحات زعفران نگین",
            is_active=True,
        )
        self.variant_a = ProductVariant.objects.create(
            product=self.product,
            packaging_type=self.packaging,
            harvest_batch=self.batch,
            sku="NG-PACKET-2G",
            net_weight_grams=Decimal("2.000"),
            weight_label="۲ گرم",
            base_price_rial=2_000_000,        # 200,000 Tomans
            discounted_price_rial=1_800_000,  # 180,000 Tomans
            stock_quantity=8,
            min_order_quantity=1,
            max_order_quantity=5,
            is_active=True,
        )
        self.variant_b = ProductVariant.objects.create(
            product=self.product,
            packaging_type=self.packaging,
            harvest_batch=self.batch,
            sku="NG-PACKET-5G",
            net_weight_grams=Decimal("5.000"),
            weight_label="۵ گرم",
            base_price_rial=4_800_000,        # 480,000 Tomans
            discounted_price_rial=None,
            stock_quantity=10,
            min_order_quantity=1,
            max_order_quantity=10,
            is_active=True,
        )

    def test_client_supplied_price_tampering_is_completely_ignored(self) -> None:
        add_url = reverse("orders:cart_add_item")
        tampered_payload = {
            "variant_public_id": str(self.variant_a.public_id),
            "quantity": 2,
            "price": 10,
            "base_price_rial": 10,
            "discounted_price_rial": 10,
            "payable_rial": 20,
        }
        resp = self.client.post(
            add_url,
            data=json.dumps(tampered_payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        cart_data = resp.json()["cart"]
        # Real effective price is 2 * 1,800,000 = 3,600,000 Rials (360,000 Tomans)
        self.assertEqual(cart_data["pricing"]["payable_rial"], 3_600_000)
        self.assertEqual(cart_data["pricing"]["payable_toman"], 360_000)

    def test_guest_cart_automatically_merges_into_user_cart_on_otp_login_with_clamping(self) -> None:
        # 1. Existing user already has 3 units of variant_a in their saved account cart
        user = User.objects.create_user(phone_number="09157778899")
        existing_user_cart = Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=existing_user_cart, variant=self.variant_a, quantity=3)

        # 2. Using a fresh unauthenticated browser client, guest adds 4 units of variant_a and 2 units of variant_b
        guest_client = Client()
        add_url = reverse("orders:cart_add_item")
        resp_a = guest_client.post(
            add_url,
            data=json.dumps({"variant_public_id": str(self.variant_a.public_id), "quantity": 4}),
            content_type="application/json",
        )
        self.assertEqual(resp_a.status_code, 200)

        resp_b = guest_client.post(
            add_url,
            data=json.dumps({"variant_public_id": str(self.variant_b.public_id), "quantity": 2}),
            content_type="application/json",
        )
        self.assertEqual(resp_b.status_code, 200)

        guest_cart_id = resp_b.json()["cart"]["cart_public_id"]

        # 3. Guest logs in via OTP
        guest_client.post(
            reverse("accounts:otp_request"),
            data=json.dumps({"phone_number": "09157778899"}),
            content_type="application/json",
        )
        otp_code = SandboxSMSProvider.outbox[0]["code"]

        verify_resp = guest_client.post(
            reverse("accounts:otp_verify"),
            data=json.dumps({"phone_number": "09157778899", "code": otp_code}),
            content_type="application/json",
        )
        self.assertEqual(verify_resp.status_code, 200)

        # 4. Verify guest cart was marked MERGED
        guest_cart = Cart.objects.get(public_id=guest_cart_id)
        self.assertEqual(guest_cart.status, Cart.Status.MERGED)
        self.assertEqual(guest_cart.items.count(), 0)

        # 5. Fetch user's cart via GET /orders/cart/
        cart_resp = guest_client.get(reverse("orders:cart_detail"))
        self.assertEqual(cart_resp.status_code, 200)
        merged_cart = cart_resp.json()["cart"]

        self.assertEqual(merged_cart["items_count"], 2)
        items_by_sku = {item["sku"]: item["quantity"] for item in merged_cart["items"]}

        # variant_a had 3 (user) + 4 (guest) = 7, clamped to max_order_quantity = 5
        self.assertEqual(items_by_sku["NG-PACKET-2G"], 5)
        # variant_b had 0 (user) + 2 (guest) = 2
        self.assertEqual(items_by_sku["NG-PACKET-5G"], 2)

        # Total payable = (5 * 1,800,000) + (2 * 4,800,000) = 9,000,000 + 9,600,000 = 18,600,000 Rials
        self.assertEqual(merged_cart["pricing"]["payable_rial"], 18_600_000)
        self.assertEqual(merged_cart["pricing"]["payable_toman"], 1_860_000)

    def test_update_to_zero_removes_item_and_clear_empties_cart(self) -> None:
        add_url = reverse("orders:cart_add_item")
        self.client.post(
            add_url,
            data=json.dumps({"variant_public_id": str(self.variant_a.public_id), "quantity": 2}),
            content_type="application/json",
        )
        self.client.post(
            add_url,
            data=json.dumps({"variant_public_id": str(self.variant_b.public_id), "quantity": 1}),
            content_type="application/json",
        )

        # Update variant_a quantity to 0 -> removes variant_a
        update_resp = self.client.post(
            reverse("orders:cart_update_item"),
            data=json.dumps({"variant_public_id": str(self.variant_a.public_id), "quantity": 0}),
            content_type="application/json",
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.json()["cart"]["items_count"], 1)

        # Clear remaining cart
        clear_resp = self.client.post(reverse("orders:cart_clear"))
        self.assertEqual(clear_resp.status_code, 200)
        self.assertEqual(clear_resp.json()["cart"]["items_count"], 0)
        self.assertEqual(clear_resp.json()["cart"]["pricing"]["payable_rial"], 0)