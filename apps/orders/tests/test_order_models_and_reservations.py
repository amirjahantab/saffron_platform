"""
Tests for Sub-phase 4.2:
- Iranian 10-digit postal code normalization and validation
- Order & OrderItem immutable snapshots and Rial/Toman monetary formula enforcement
- StockReservation atomic deduction, idempotent release, commitment, and overdue batch expiration
- OrderStateAndReservationService state machine transition rules
"""
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.catalog.models import (
    HarvestBatch,
    PackagingType,
    Product,
    ProductVariant,
    SaffronGrade,
)
from apps.orders.exceptions import (
    InsufficientStockError,
    InvalidOrderStateTransitionError,
)
from apps.orders.models import (
    Order,
    OrderItem,
    ShippingAddress,
    StockReservation,
)
from apps.orders.services.reservation_service import OrderStateAndReservationService
from apps.orders.validators import normalize_iranian_postal_code


class PostalCodeAndShippingAddressTests(TestCase):
    """Test Iranian postal code normalization and ShippingAddress validation."""

    def test_valid_postal_code_with_persian_and_arabic_digits(self) -> None:
        self.assertEqual(normalize_iranian_postal_code("۹۱۸۸۱-۴۴۵۵۶"), "9188144556")
        self.assertEqual(normalize_iranian_postal_code(" ٩١٨٨١٤٤٥٥٦ "), "9188144556")

    def test_invalid_postal_codes_are_rejected(self) -> None:
        invalid_codes = [
            "123456789",       # 9 digits
            "12345678901",     # 11 digits
            "1111111111",      # All identical digits
            "0000000000",      # All zeros
            "918814455A",      # Contains letter
        ]
        for code in invalid_codes:
            with self.subTest(code=code):
                with self.assertRaises(ValidationError):
                    normalize_iranian_postal_code(code)

    def test_shipping_address_clean_normalizes_phone_and_postal_code(self) -> None:
        user = User.objects.create_user(phone_number="09151112233")
        addr = ShippingAddress(
            user=user,
            recipient_full_name="امیررضا جهان‌تاب",
            recipient_phone="+98 915-111-2233",
            province="خراسان رضوی",
            city="مشهد",
            address_line="میدان هفده شهریور، مجتمع زعفران",
            postal_code="۹۱۸۸۱-۴۴۵۵۶",
        )
        addr.full_clean()
        addr.save()
        self.assertEqual(addr.recipient_phone, "09151112233")
        self.assertEqual(addr.postal_code, "9188144556")


class OrderModelsAndReservationLifecycleTests(TestCase):
    """Verify Order monetary constraints, immutable snapshots, stock reservation, and state transitions."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(phone_number="09152223344", full_name="مشتری تست")
        self.packaging = PackagingType.objects.create(
            name="خاتم سلطنتی",
            slug="royal-khatam",
            tare_weight_grams=Decimal("25.00"),
        )
        self.batch = HarvestBatch.objects.create(
            batch_code="JHT-1405-ORD-01",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            origin_region="قائنات",
            harvest_year=1405,
        )
        self.product = Product.objects.create(
            name="زعفران سوپر نگین یک مثقالی",
            slug="super-negin-1m-order",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            short_description="زعفران سوپر نگین",
            description="توضیحات کامل",
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            packaging_type=self.packaging,
            harvest_batch=self.batch,
            sku="SN-ROYAL-1M",
            net_weight_grams=Decimal("4.608"),
            weight_label="۱ مثقال",
            base_price_rial=4_000_000,        # 400,000 Tomans
            discounted_price_rial=3_600_000,  # 360,000 Tomans
            stock_quantity=10,
            is_active=True,
        )

    def _create_sample_order(self, expires_delta_minutes: int = 15) -> Order:
        order = Order(
            user=self.user,
            recipient_full_name="مشتری تست",
            recipient_phone="09152223344",
            province="خراسان رضوی",
            city="مشهد",
            address_line="بلوار سجاد، پلاک ۱۰",
            postal_code="9188144556",
            total_gross_weight_grams=Decimal("59.216"),
            subtotal_base_rial=8_000_000,     # 2 * 4,000,000
            total_discount_rial=800_000,      # 2 * 400,000
            shipping_cost_rial=450_000,       # 45,000 Tomans
            payable_rial=7_650_000,           # 7,200,000 + 450,000 = 765,000 Tomans
            reservation_expires_at=timezone.now() + timedelta(minutes=expires_delta_minutes),
        )
        order.full_clean()
        order.save()

        item = OrderItem(
            order=order,
            variant=self.variant,
            product_name_snapshot=self.product.name,
            sku_snapshot=self.variant.sku,
            saffron_grade_snapshot=self.product.saffron_grade,
            packaging_name_snapshot=self.packaging.name,
            weight_label_snapshot=self.variant.weight_label,
            net_weight_grams_snapshot=self.variant.net_weight_grams,
            batch_code_snapshot=self.batch.batch_code,
            origin_region_snapshot=self.batch.origin_region,
            harvest_year_snapshot=self.batch.harvest_year,
            quantity=2,
            unit_base_price_rial=4_000_000,
            unit_effective_price_rial=3_600_000,
            line_base_total_rial=8_000_000,
            line_discount_total_rial=800_000,
            line_effective_total_rial=7_200_000,
        )
        item.full_clean()
        item.save()
        return order

    def test_order_monetary_formula_and_snapshot_immutability(self) -> None:
        order = self._create_sample_order()
        self.assertEqual(order.payable_toman, 765_000)
        self.assertEqual(order.formatted_payable_toman, "۷۶۵,۰۰۰ تومان")

        # Mutate catalog price and product name AFTER order creation
        self.variant.base_price_rial = 9_000_000
        self.variant.discounted_price_rial = None
        self.variant.save()
        self.product.name = "نام جدید محصول"
        self.product.save()

        # Verify historical OrderItem snapshot remains completely unchanged
        order_item = order.items.first()
        assert order_item is not None
        self.assertEqual(order_item.product_name_snapshot, "زعفران سوپر نگین یک مثقالی")
        self.assertEqual(order_item.unit_effective_price_rial, 3_600_000)
        self.assertEqual(order_item.line_effective_total_toman, 720_000)

    def test_order_rejects_mismatched_payable_rial_or_non_multiple_of_ten(self) -> None:
        bad_order = Order(
            user=self.user,
            recipient_full_name="مشتری",
            recipient_phone="09152223344",
            province="تهران",
            city="تهران",
            address_line="خیابان ولیعصر",
            postal_code="1988776655",
            total_gross_weight_grams=Decimal("29.608"),
            subtotal_base_rial=4_000_000,
            total_discount_rial=0,
            shipping_cost_rial=450_000,
            payable_rial=1_000_000,  # Should be 4,450,000
            reservation_expires_at=timezone.now() + timedelta(minutes=15),
        )
        with self.assertRaises(ValidationError) as ctx:
            bad_order.full_clean()
        self.assertIn("payable_rial", ctx.exception.message_dict)

    def test_stock_reservation_deducts_stock_and_idempotently_restores_on_cancel(self) -> None:
        order = self._create_sample_order()
        # Initial stock is 10; reserve 2 units
        res = OrderStateAndReservationService.reserve_variant_stock(
            order=order,
            variant_id=self.variant.pk,
            quantity=2,
        )
        self.assertEqual(res.status, StockReservation.Status.ACTIVE)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)

        # Transition order to CANCELLED -> stock must return to 10
        OrderStateAndReservationService.transition_order_status(
            order=order,
            target_status=Order.Status.CANCELLED,
            cancel_reason="انصراف مشتری",
        )
        self.variant.refresh_from_db()
        res.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(res.status, StockReservation.Status.RELEASED)
        self.assertEqual(self.variant.stock_quantity, 10)

        # Calling release_order_reservations a second time MUST be a no-op (stock stays 10, never 12)
        released_again = OrderStateAndReservationService.release_order_reservations(order)
        self.assertEqual(released_again, 0)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)

    def test_reserve_stock_exceeding_available_inventory_raises_error(self) -> None:
        order = self._create_sample_order()
        with self.assertRaises(InsufficientStockError):
            OrderStateAndReservationService.reserve_variant_stock(
                order=order,
                variant_id=self.variant.pk,
                quantity=11,  # Only 10 in stock
            )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)

    def test_paid_transition_commits_reservation_and_blocks_invalid_transitions(self) -> None:
        order = self._create_sample_order()
        res = OrderStateAndReservationService.reserve_variant_stock(
            order=order,
            variant_id=self.variant.pk,
            quantity=2,
        )

        # Cannot jump directly from PENDING_PAYMENT to DELIVERED
        with self.assertRaises(InvalidOrderStateTransitionError):
            OrderStateAndReservationService.transition_order_status(
                order=order,
                target_status=Order.Status.DELIVERED,
            )

        # Valid transition to PAID commits the reservation
        OrderStateAndReservationService.transition_order_status(
            order=order,
            target_status=Order.Status.PAID,
        )
        res.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertIsNotNone(order.paid_at)
        self.assertEqual(res.status, StockReservation.Status.COMMITTED)
        self.assertIsNotNone(res.committed_at)

    def test_expire_overdue_reservations_sweeps_and_restores_stock(self) -> None:
        # Create an order whose reservation expired 2 minutes ago
        overdue_order = self._create_sample_order(expires_delta_minutes=-2)
        OrderStateAndReservationService.reserve_variant_stock(
            order=overdue_order,
            variant_id=self.variant.pk,
            quantity=3,
        )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 7)

        expired_count = OrderStateAndReservationService.expire_overdue_reservations()
        self.assertEqual(expired_count, 1)

        overdue_order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(overdue_order.status, Order.Status.EXPIRED)
        self.assertEqual(self.variant.stock_quantity, 10)

        # Cannot pay for an EXPIRED order
        with self.assertRaises(InvalidOrderStateTransitionError):
            OrderStateAndReservationService.transition_order_status(
                order=overdue_order,
                target_status=Order.Status.PAID,
            )