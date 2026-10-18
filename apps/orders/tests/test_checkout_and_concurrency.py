"""
Comprehensive tests for Sub-phase 4.3 (Completing Phase 4):
- Atomic checkout from Cart to Order, OrderItem snapshots, and StockReservation creation
- Shipping cost calculation (default cost vs free shipping threshold)
- Idempotency key enforcement (preventing duplicate orders on double-submit)
- Concurrency & Overselling prevention (simultaneous checkout attempts on limited stock)
- Automatic overdue reservation cleanup before checkout when scarce stock is locked by an expired order
- Strict ownership access control (IDOR protection on order detail and cancel endpoints)
- Management command `expire_overdue_orders`
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import StringIO
import json
from django.core.management import call_command
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
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
from apps.orders.exceptions import InsufficientStockError
from apps.orders.models import (
    Cart,
    CartItem,
    Order,
    ShippingAddress,
    StockReservation,
)
from apps.orders.services.checkout_service import CheckoutService


class CheckoutFlowAndSecurityTests(TestCase):
    """Test end-to-end checkout, idempotency, shipping thresholds, and IDOR protection."""

    def setUp(self) -> None:
        self.user_a = User.objects.create_user(phone_number="09151110001", full_name="کاربر الف")
        self.user_b = User.objects.create_user(phone_number="09151110002", full_name="کاربر ب")

        self.packaging = PackagingType.objects.create(
            name="خاتم ممتاز صادراتی",
            slug="export-khatam",
            tare_weight_grams=Decimal("30.00"),
        )
        self.batch = HarvestBatch.objects.create(
            batch_code="JHT-1405-CHK-01",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            origin_region="قائنات",
            harvest_year=1405,
        )
        self.product = Product.objects.create(
            name="زعفران سوپر نگین قائنات",
            slug="qayenat-super-negin",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            short_description="سوپر نگین درجه یک",
            description="توضیحات کامل",
            is_active=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packaging_type=self.packaging,
            harvest_batch=self.batch,
            sku="SN-CHK-1M",
            net_weight_grams=Decimal("4.608"),
            weight_label="۱ مثقال",
            base_price_rial=4_500_000,        # 450,000 Tomans
            discounted_price_rial=4_000_000,  # 400,000 Tomans
            stock_quantity=5,
            min_order_quantity=1,
            max_order_quantity=5,
            is_active=True,
        )

    def _populate_cart_for_user(self, user: User, quantity: int) -> Cart:
        cart, _ = Cart.objects.get_or_create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.update_or_create(
            cart=cart,
            variant=self.variant,
            defaults={"quantity": quantity},
        )
        return cart

    @override_settings(
        ORDER_DEFAULT_SHIPPING_COST_RIAL=450_000,
        ORDER_FREE_SHIPPING_THRESHOLD_RIAL=15_000_000,
    )
    def test_full_checkout_creates_order_reserves_stock_and_converts_cart(self) -> None:
        cart = self._populate_cart_for_user(self.user_a, quantity=2)
        self.client.force_login(self.user_a)

        checkout_payload = {
            "recipient_full_name": "امیررضا جهانتاب",
            "recipient_phone": "۰۹۱۵۱۱۱۰۰۰۱",
            "province": "خراسان رضوی",
            "city": "مشهد",
            "address_line": "مجتمع زعفران سی‌نور، واحد ۱۲",
            "postal_code": "۹۱۸۸۱-۴۴۵۵۶",
            "save_address": True,
            "shipping_method": Order.ShippingMethod.POST_PISHTAZ,
            "customer_note": "لطفاً بسته‌بندی کادویی شود.",
            "idempotency_key": "idem-checkout-001",
        }
        resp = self.client.post(
            reverse("orders:checkout"),
            data=json.dumps(checkout_payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["created"])

        order_data = data["order"]
        # 2 * 4,500,000 = 9,000,000 base; 2 * 4,000,000 = 8,000,000 effective (< 15M threshold -> +450,000 shipping)
        self.assertEqual(order_data["pricing"]["subtotal_base_rial"], 9_000_000)
        self.assertEqual(order_data["pricing"]["total_discount_rial"], 1_000_000)
        self.assertEqual(order_data["pricing"]["shipping_cost_rial"], 450_000)
        self.assertEqual(order_data["pricing"]["payable_rial"], 8_450_000)
        self.assertEqual(order_data["pricing"]["payable_toman"], 845_000)

        # Verify stock was deducted (5 - 2 = 3) and active reservation exists
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)

        order = Order.objects.get(order_number=order_data["order_number"])
        self.assertEqual(order.reservations.filter(status=StockReservation.Status.ACTIVE).count(), 1)

        # Verify source cart was marked CONVERTED and emptied
        cart.refresh_from_db()
        self.assertEqual(cart.status, Cart.Status.CONVERTED)
        self.assertEqual(cart.items.count(), 0)

        # Verify address was saved to user's address book
        self.assertTrue(ShippingAddress.objects.filter(user=self.user_a, postal_code="9188144556").exists())

    @override_settings(
        ORDER_DEFAULT_SHIPPING_COST_RIAL=450_000,
        ORDER_FREE_SHIPPING_THRESHOLD_RIAL=15_000_000,
    )
    def test_free_shipping_threshold_applied_when_order_exceeds_limit(self) -> None:
        # 4 * 4,000,000 = 16,000,000 Rials (>= 15,000,000 threshold -> shipping_cost_rial = 0)
        self._populate_cart_for_user(self.user_a, quantity=4)
        order, created = CheckoutService.create_order_from_cart(
            user=self.user_a,
            address_data={
                "recipient_full_name": "کاربر الف",
                "recipient_phone": "09151110001",
                "province": "تهران",
                "city": "تهران",
                "address_line": "میدان ونک",
                "postal_code": "1988776654",
            },
        )
        self.assertTrue(created)
        self.assertEqual(order.shipping_cost_rial, 0)
        self.assertEqual(order.payable_rial, 16_000_000)

    def test_idempotency_key_prevents_duplicate_orders_and_double_stock_deduction(self) -> None:
        self._populate_cart_for_user(self.user_a, quantity=2)
        self.client.force_login(self.user_a)

        payload = {
            "recipient_full_name": "کاربر الف",
            "recipient_phone": "09151110001",
            "province": "خراسان رضوی",
            "city": "مشهد",
            "address_line": "خیابان امام رضا",
            "postal_code": "9188144556",
            "idempotency_key": "duplicate-click-key-999",
        }
        resp1 = self.client.post(
            reverse("orders:checkout"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp1.status_code, 201)

        # Even if user adds another item to a new cart and retries the same idempotency_key,
        # the exact first order must be returned without creating a second order or deducting more stock.
        self._populate_cart_for_user(self.user_a, quantity=1)
        resp2 = self.client.post(
            reverse("orders:checkout"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertFalse(resp2.json()["created"])
        self.assertEqual(resp1.json()["order"]["order_number"], resp2.json()["order"]["order_number"])
        self.assertEqual(Order.objects.filter(user=self.user_a).count(), 1)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)

    def test_competing_checkouts_prevent_overselling_last_items(self) -> None:
        # Stock is 5. Both User A and User B add 4 units to their respective carts.
        self._populate_cart_for_user(self.user_a, quantity=4)
        self._populate_cart_for_user(self.user_b, quantity=4)

        addr_payload = {
            "recipient_full_name": "خریدار",
            "recipient_phone": "09151110001",
            "province": "خراسان رضوی",
            "city": "مشهد",
            "address_line": "آدرس تست",
            "postal_code": "9188144556",
        }

        # User A checks out first -> succeeds, remaining stock becomes 1
        order_a, _ = CheckoutService.create_order_from_cart(user=self.user_a, address_data=addr_payload)
        self.assertIsNotNone(order_a)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 1)

        # User B attempts to checkout 4 units when only 1 remains -> must fail with InsufficientStockError
        with self.assertRaises(InsufficientStockError):
            CheckoutService.create_order_from_cart(user=self.user_b, address_data=addr_payload)

        # Verify no order was created for User B and stock remains 1
        self.assertEqual(Order.objects.filter(user=self.user_b).count(), 0)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 1)

    def test_overdue_reservation_is_automatically_freed_during_next_customer_checkout(self) -> None:
        # User A reserves 4 out of 5 units, then their reservation expires
        self._populate_cart_for_user(self.user_a, quantity=4)
        addr_payload = {
            "recipient_full_name": "خریدار",
            "recipient_phone": "09151110001",
            "province": "خراسان رضوی",
            "city": "مشهد",
            "address_line": "آدرس تست",
            "postal_code": "9188144556",
        }
        order_a, _ = CheckoutService.create_order_from_cart(user=self.user_a, address_data=addr_payload)
        # Fast-forward expiration into the past
        Order.objects.filter(pk=order_a.pk).update(
            reservation_expires_at=timezone.now() - timedelta(minutes=5)
        )

        # Now User B wants 4 units. CheckoutService automatically sweeps overdue reservations first!
        self._populate_cart_for_user(self.user_b, quantity=4)
        order_b, created = CheckoutService.create_order_from_cart(user=self.user_b, address_data=addr_payload)
        self.assertTrue(created)

        order_a.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order_a.status, Order.Status.EXPIRED)
        self.assertEqual(order_b.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(self.variant.stock_quantity, 1)

    def test_idor_access_control_prevents_viewing_or_cancelling_other_users_order(self) -> None:
        self._populate_cart_for_user(self.user_a, quantity=2)
        order_a, _ = CheckoutService.create_order_from_cart(
            user=self.user_a,
            address_data={
                "recipient_full_name": "کاربر الف",
                "recipient_phone": "09151110001",
                "province": "خراسان رضوی",
                "city": "مشهد",
                "address_line": "آدرس خصوصی کاربر الف",
                "postal_code": "9188144556",
            },
        )

        # Log in as User B and attempt to view or cancel User A's order
        client_b = Client()
        client_b.force_login(self.user_b)

        detail_resp = client_b.get(
            reverse("orders:order_detail", kwargs={"order_number": order_a.order_number})
        )
        self.assertEqual(detail_resp.status_code, 404)

        cancel_resp = client_b.post(
            reverse("orders:order_cancel", kwargs={"order_number": order_a.order_number})
        )
        self.assertEqual(cancel_resp.status_code, 404)

        # Owner (User A) CAN cancel their own PENDING_PAYMENT order and stock returns to 5
        client_a = Client()
        client_a.force_login(self.user_a)
        owner_cancel_resp = client_a.post(
            reverse("orders:order_cancel", kwargs={"order_number": order_a.order_number}),
            data=json.dumps({"cancel_reason": "تغییر وزن سفارش"}),
            content_type="application/json",
        )
        self.assertEqual(owner_cancel_resp.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)

    def test_expire_overdue_orders_management_command(self) -> None:
        self._populate_cart_for_user(self.user_a, quantity=3)
        order_a, _ = CheckoutService.create_order_from_cart(
            user=self.user_a,
            address_data={
                "recipient_full_name": "کاربر الف",
                "recipient_phone": "09151110001",
                "province": "خراسان رضوی",
                "city": "مشهد",
                "address_line": "آدرس",
                "postal_code": "9188144556",
            },
        )
        Order.objects.filter(pk=order_a.pk).update(
            reservation_expires_at=timezone.now() - timedelta(minutes=1)
        )

        out = StringIO()
        call_command("expire_overdue_orders", stdout=out)
        self.assertIn("1 order(s) expired", out.getvalue())

        order_a.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order_a.status, Order.Status.EXPIRED)
        self.assertEqual(self.variant.stock_quantity, 5)


class ConcurrentCheckoutTransactionTests(TransactionTestCase):
    """
    True multi-threaded concurrency test verifying `select_for_update` row locking
    prevents overselling when two threads attempt to buy the last stock simultaneously.
    """

    def setUp(self) -> None:
        self.user_1 = User.objects.create_user(phone_number="09159000001", full_name="نخ اول")
        self.user_2 = User.objects.create_user(phone_number="09159000002", full_name="نخ دوم")

        self.packaging = PackagingType.objects.create(
            name="ظرف کریستالی",
            slug="crystal-pack-conc",
            tare_weight_grams=Decimal("15.00"),
        )
        self.batch = HarvestBatch.objects.create(
            batch_code="JHT-1405-CONC-01",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            origin_region="قائنات",
            harvest_year=1405,
        )
        self.product = Product.objects.create(
            name="زعفران سوپر نگین تست هم‌زمانی",
            slug="super-negin-concurrency",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            short_description="تست هم‌زمانی",
            description="توضیحات",
            is_active=True,
        )
        # Only 3 units in stock; both users will attempt to purchase 2 units concurrently
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packaging_type=self.packaging,
            harvest_batch=self.batch,
            sku="SN-CONC-1M",
            net_weight_grams=Decimal("4.608"),
            weight_label="۱ مثقال",
            base_price_rial=4_000_000,
            stock_quantity=3,
            min_order_quantity=1,
            max_order_quantity=5,
            is_active=True,
        )

        cart_1 = Cart.objects.create(user=self.user_1, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart_1, variant=self.variant, quantity=2)

        cart_2 = Cart.objects.create(user=self.user_2, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart_2, variant=self.variant, quantity=2)

    def test_simultaneous_threaded_checkouts_never_oversell_inventory(self) -> None:
        address_data = {
            "recipient_full_name": "خریدار هم‌زمان",
            "recipient_phone": "09159000001",
            "province": "خراسان رضوی",
            "city": "مشهد",
            "address_line": "بلوار وکیل‌آباد",
            "postal_code": "9188144556",
        }

        def _attempt_checkout(user_obj: User) -> str:
            try:
                CheckoutService.create_order_from_cart(user=user_obj, address_data=address_data)
                return "success"
            except InsufficientStockError:
                return "insufficient_stock"
            finally:
                connections.close_all()

        # On PostgreSQL, execute in parallel threads to test database-level row locks.
        # On in-memory SQLite (which shares a single memory connection), execute sequentially.
        if connection.vendor == "postgresql":
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(_attempt_checkout, self.user_1),
                    executor.submit(_attempt_checkout, self.user_2),
                ]
                results = [f.result() for f in futures]
        else:
            results = [
                _attempt_checkout(self.user_1),
                _attempt_checkout(self.user_2),
            ]

        self.assertEqual(sorted(results), ["insufficient_stock", "success"])
        self.assertEqual(Order.objects.count(), 1)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 1)