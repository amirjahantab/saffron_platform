"""
Transactional Checkout & Order Creation Service (Sub-phase 4.3).

Enforces:
1. Overdue stock reservation cleanup prior to inventory verification.
2. Row-level locking (`select_for_update`) in deterministic order (User -> Cart -> Variants by PK)
   to prevent race conditions (overselling) and database deadlocks.
3. Idempotent order creation via `idempotency_key`.
4. Authoritative server-side Rial/Toman pricing and shipping cost calculation.
5. Immutable OrderItem and ShippingAddress snapshots.
"""
from datetime import timedelta
from decimal import Decimal
import logging
from apps.orders.access import token_digest
from typing import Any
from uuid import UUID
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.accounts.models import User
from apps.accounts.validators import normalize_iranian_phone
from apps.catalog.models import ProductVariant
from apps.core.currency import (
    format_price_toman,
    rial_to_toman,
    validate_rial_amount,
)
from apps.orders.exceptions import (
    CartItemUnavailableError,
    EmptyCartCheckoutError,
    OrderError,
)
from apps.orders.models import (
    Cart,
    Order,
    OrderItem,
    ShippingAddress,
)
from apps.orders.services.cart_service import CartService
from apps.orders.services.reservation_service import OrderStateAndReservationService
from apps.orders.validators import normalize_iranian_postal_code

logger = logging.getLogger(__name__)


class CheckoutService:
    """Orchestrates atomic conversion of a user's active Cart into an Order with stock reservations."""

    @staticmethod
    def calculate_shipping_cost_rial(items_payable_rial: int) -> int:
        """
        Calculate shipping cost in Rials based on configured thresholds.
        Zero floating-point arithmetic is used.
        """
        validated_payable = validate_rial_amount(items_payable_rial)
        free_threshold = validate_rial_amount(
            int(getattr(settings, "ORDER_FREE_SHIPPING_THRESHOLD_RIAL", 15_000_000))
        )
        default_shipping = validate_rial_amount(
            int(getattr(settings, "ORDER_DEFAULT_SHIPPING_COST_RIAL", 450_000))
        )
        if validated_payable >= free_threshold:
            return 0
        return default_shipping

    @staticmethod
    def _resolve_shipping_snapshot(
        user: User,
        shipping_address_public_id: UUID | str | None,
        address_data: dict[str, Any],
        save_new_address: bool = False,
    ) -> dict[str, str]:
        """
        Resolve recipient and address details either from an existing user-owned
        ShippingAddress or from validated form payload, optionally saving it to the user's address book.
        """
        if shipping_address_public_id:
            try:
                saved_addr = ShippingAddress.objects.get(
                    public_id=shipping_address_public_id,
                    user=user,
                )
            except (ShippingAddress.DoesNotExist, ValueError, TypeError) as exc:
                raise OrderError(
                    _("آدرس انتخاب‌شده یافت نشد یا متعلق به حساب کاربری شما نیست."),
                    code="invalid_shipping_address",
                ) from exc

            return {
                "recipient_full_name": saved_addr.recipient_full_name,
                "recipient_phone": saved_addr.recipient_phone,
                "province": saved_addr.province,
                "city": saved_addr.city,
                "address_line": saved_addr.address_line,
                "postal_code": saved_addr.postal_code,
            }

        normalized_phone = normalize_iranian_phone(str(address_data.get("recipient_phone", "")))
        normalized_postal = normalize_iranian_postal_code(str(address_data.get("postal_code", "")))
        recipient_full_name = str(address_data.get("recipient_full_name", "")).strip()
        province = str(address_data.get("province", "")).strip()
        city = str(address_data.get("city", "")).strip()
        address_line = str(address_data.get("address_line", "")).strip()

        if not all([recipient_full_name, province, city, address_line]):
            raise OrderError(
                _("تکمیل تمامی اطلاعات گیرنده و نشانی پستی برای ثبت سفارش الزامی است."),
                code="incomplete_address",
            )

        if save_new_address and user is not None:
            has_existing = ShippingAddress.objects.filter(user=user).exists()
            new_addr = ShippingAddress(
                user=user,
                recipient_full_name=recipient_full_name,
                recipient_phone=normalized_phone,
                province=province,
                city=city,
                address_line=address_line,
                postal_code=normalized_postal,
                is_default=not has_existing,
            )
            new_addr.full_clean()
            new_addr.save()

        return {
            "recipient_full_name": recipient_full_name,
            "recipient_phone": normalized_phone,
            "province": province,
            "city": city,
            "address_line": address_line,
            "postal_code": normalized_postal,
        }

    @classmethod
    def create_order_from_cart(
        cls,
        *,
        user: User | None,
        shipping_address_public_id: UUID | str | None = None,
        address_data: dict[str, Any] | None = None,
        save_new_address: bool = False,
        shipping_method: str = Order.ShippingMethod.POST_PISHTAZ,
        customer_note: str = "",
        idempotency_key: str | None = None,
        guest_cart: Cart | None = None,
        guest_token: str | None = None,
    ) -> tuple[Order, bool]:
        """
        Atomically convert the authenticated user's active Cart into an Order.
        Returns `(order, created_bool)`.
        If `idempotency_key` matches an existing order for this user, returns `(existing_order, False)`.
        """
        cleaned_idem_key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None

        # 1. Sweep overdue reservations before starting checkout so expired stock is freed
        OrderStateAndReservationService.expire_overdue_reservations()

        with transaction.atomic():
            # 2. Lock the User row to serialize concurrent checkout attempts by the same user
            locked_user = User.objects.select_for_update().get(pk=user.pk) if user is not None else None
            if locked_user is None and (guest_cart is None or not guest_token or len(guest_token) < 32):
                raise EmptyCartCheckoutError("نشست خرید مهمان معتبر نیست.")
            if locked_user is None:
                guest_cart = Cart.objects.select_for_update().get(pk=guest_cart.pk, user__isnull=True)

            # 3. Check idempotency key inside the user lock
            if cleaned_idem_key:
                existing_order = (
                    Order.objects.filter(user=locked_user, idempotency_key=cleaned_idem_key, **({"source_cart": guest_cart} if locked_user is None else {}))
                    .prefetch_related("items", "reservations")
                    .first()
                )
                if existing_order is not None:
                    logger.info(
                        "Idempotent checkout hit: returning existing order=%s for user_id=%s",
                        existing_order.order_number,
                        locked_user.pk if locked_user else None,
                    )
                    return existing_order, False

            # 4. Lock the user's active Cart
            if locked_user is None:
                cart = guest_cart if guest_cart.status == Cart.Status.ACTIVE else None
            else:
                cart = Cart.objects.select_for_update().filter(user=locked_user, status=Cart.Status.ACTIVE).first()
            if cart is None or (locked_user is None and cart.pk != guest_cart.pk):
                raise EmptyCartCheckoutError(_("سبد خرید فعالی برای ثبت سفارش وجود ندارد."))

            cart_items = list(cart.items.order_by("variant_id"))
            if not cart_items:
                raise EmptyCartCheckoutError(_("سبد خرید شما خالی است."))

            # 5. Lock all ProductVariant rows in deterministic ascending ID order to prevent deadlocks
            variant_ids = [ci.variant_id for ci in cart_items]
            locked_variants_qs = (
                ProductVariant.objects.select_for_update()
                .select_related("product", "packaging_type", "harvest_batch")
                .filter(pk__in=variant_ids)
                .order_by("pk")
            )
            locked_variants_map = {v.pk: v for v in locked_variants_qs}

            # 6. Validate availability, stock, and calculate authoritative server-side totals
            subtotal_base_rial = 0
            items_payable_rial = 0
            total_gross_weight_grams = Decimal("0.000")

            for ci in cart_items:
                variant = locked_variants_map.get(ci.variant_id)
                if (
                    variant is None
                    or not variant.is_active
                    or not variant.product.is_active
                    or not variant.packaging_type.is_active
                    or not variant.harvest_batch.is_active
                ):
                    raise CartItemUnavailableError(
                        _("یکی از اقلام موجود در سبد خرید شما غیرفعال شده و قابل سفارش نیست.")
                    )

                # Validates stock_quantity >= ci.quantity and min/max bounds
                CartService.validate_variant_quantity(variant, ci.quantity)

                unit_base = validate_rial_amount(int(variant.base_price_rial))
                unit_effective = validate_rial_amount(int(variant.effective_price_rial))

                subtotal_base_rial += unit_base * ci.quantity
                items_payable_rial += unit_effective * ci.quantity
                total_gross_weight_grams += (
                    variant.gross_weight_grams * Decimal(int(ci.quantity))
                ).quantize(Decimal("0.001"))

            subtotal_base_rial = validate_rial_amount(subtotal_base_rial)
            items_payable_rial = validate_rial_amount(items_payable_rial)
            total_discount_rial = validate_rial_amount(subtotal_base_rial - items_payable_rial)
            shipping_cost_rial = cls.calculate_shipping_cost_rial(items_payable_rial)
            payable_rial = validate_rial_amount(items_payable_rial + shipping_cost_rial)

            # 7. Resolve recipient address snapshot
            shipping_snapshot = cls._resolve_shipping_snapshot(
                user=locked_user,
                shipping_address_public_id=shipping_address_public_id,
                address_data=address_data or {},
                save_new_address=save_new_address,
            )

            expiry_minutes = int(getattr(settings, "ORDER_RESERVATION_EXPIRY_MINUTES", 15))
            reservation_expires_at = timezone.now() + timedelta(minutes=expiry_minutes)

            # 8. Create the authoritative Order record
            order = Order(
                user=locked_user,
                guest_access_hash=token_digest(guest_token) if locked_user is None else "",
                source_cart=cart,
                idempotency_key=cleaned_idem_key,
                status=Order.Status.PENDING_PAYMENT,
                recipient_full_name=shipping_snapshot["recipient_full_name"],
                recipient_phone=shipping_snapshot["recipient_phone"],
                province=shipping_snapshot["province"],
                city=shipping_snapshot["city"],
                address_line=shipping_snapshot["address_line"],
                postal_code=shipping_snapshot["postal_code"],
                shipping_method=shipping_method,
                total_gross_weight_grams=total_gross_weight_grams.quantize(Decimal("0.001")),
                customer_note=customer_note.strip(),
                subtotal_base_rial=subtotal_base_rial,
                total_discount_rial=total_discount_rial,
                shipping_cost_rial=shipping_cost_rial,
                payable_rial=payable_rial,
                reservation_expires_at=reservation_expires_at,
            )
            order.full_clean()
            order.save()

            # 9. Create immutable OrderItem snapshots and deduct/reserve stock
            for ci in cart_items:
                variant = locked_variants_map[ci.variant_id]
                unit_base = validate_rial_amount(int(variant.base_price_rial))
                unit_effective = validate_rial_amount(int(variant.effective_price_rial))
                line_base = validate_rial_amount(unit_base * ci.quantity)
                line_effective = validate_rial_amount(unit_effective * ci.quantity)
                line_discount = validate_rial_amount(line_base - line_effective)

                order_item = OrderItem(
                    order=order,
                    variant=variant,
                    product_name_snapshot=variant.product.name,
                    sku_snapshot=variant.sku,
                    saffron_grade_snapshot=variant.product.saffron_grade,
                    packaging_name_snapshot=variant.packaging_type.name,
                    weight_label_snapshot=variant.weight_label,
                    net_weight_grams_snapshot=variant.net_weight_grams,
                    batch_code_snapshot=variant.harvest_batch.batch_code,
                    origin_region_snapshot=variant.harvest_batch.origin_region,
                    harvest_year_snapshot=variant.harvest_batch.harvest_year,
                    quantity=ci.quantity,
                    unit_base_price_rial=unit_base,
                    unit_effective_price_rial=unit_effective,
                    line_base_total_rial=line_base,
                    line_discount_total_rial=line_discount,
                    line_effective_total_rial=line_effective,
                )
                order_item.full_clean()
                order_item.save()

                OrderStateAndReservationService.reserve_variant_stock(
                    order=order,
                    variant_id=variant.pk,
                    quantity=ci.quantity,
                )

            # 10. Transition Cart to CONVERTED and clear its mutable items
            cart.items.all().delete()
            cart.status = Cart.Status.CONVERTED
            cart.save(update_fields=["status", "updated_at"])

            logger.info(
                "Order created successfully: order_number=%s user_id=%s payable_rial=%d",
                order.order_number,
                locked_user.pk if locked_user else None,
                order.payable_rial,
            )
            return order, True

    @staticmethod
    def serialize_order(order: Order, include_items: bool = True) -> dict[str, Any]:
        """Serialize an Order instance with full Rial/Toman monetary details and item snapshots."""
        payload: dict[str, Any] = {
            "public_id": str(order.public_id),
            "order_number": order.order_number,
            "status": {
                "code": order.status,
                "label": order.get_status_display(),
            },
            "shipping": {
                "recipient_full_name": order.recipient_full_name,
                "recipient_phone": order.recipient_phone,
                "province": order.province,
                "city": order.city,
                "address_line": order.address_line,
                "postal_code": order.postal_code,
                "shipping_method": order.shipping_method,
                "shipping_method_label": order.get_shipping_method_display(),
                "tracking_code": order.tracking_code,
                "total_gross_weight_grams": str(order.total_gross_weight_grams),
            },
            "pricing": {
                "subtotal_base_rial": order.subtotal_base_rial,
                "subtotal_base_toman": order.subtotal_base_toman,
                "formatted_subtotal_base_toman": format_price_toman(order.subtotal_base_rial),
                "total_discount_rial": order.total_discount_rial,
                "total_discount_toman": order.total_discount_toman,
                "formatted_total_discount_toman": format_price_toman(order.total_discount_rial),
                "shipping_cost_rial": order.shipping_cost_rial,
                "shipping_cost_toman": order.shipping_cost_toman,
                "formatted_shipping_cost_toman": format_price_toman(order.shipping_cost_rial),
                "payable_rial": order.payable_rial,
                "payable_toman": order.payable_toman,
                "formatted_payable_toman": order.formatted_payable_toman,
            },
            "timestamps": {
                "created_at": order.created_at.isoformat(),
                "reservation_expires_at": order.reservation_expires_at.isoformat(),
                "paid_at": order.paid_at.isoformat() if order.paid_at else None,
                "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
                "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
                "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
            },
            "customer_note": order.customer_note,
            "cancel_reason": order.cancel_reason,
        }

        if include_items:
            items_list = []
            for item in order.items.all():
                items_list.append(
                    {
                        "public_id": str(item.public_id),
                        "variant_public_id": str(item.variant.public_id),
                        "product_name": item.product_name_snapshot,
                        "sku": item.sku_snapshot,
                        "saffron_grade": item.saffron_grade_snapshot,
                        "saffron_grade_label": item.get_saffron_grade_snapshot_display(),
                        "packaging_name": item.packaging_name_snapshot,
                        "weight_label": item.weight_label_snapshot,
                        "net_weight_grams": str(item.net_weight_grams_snapshot),
                        "batch_traceability": {
                            "batch_code": item.batch_code_snapshot,
                            "origin_region": item.origin_region_snapshot,
                            "harvest_year": item.harvest_year_snapshot,
                        },
                        "quantity": item.quantity,
                        "pricing": {
                            "unit_base_price_rial": item.unit_base_price_rial,
                            "unit_base_price_toman": rial_to_toman(item.unit_base_price_rial),
                            "unit_effective_price_rial": item.unit_effective_price_rial,
                            "unit_effective_price_toman": item.unit_effective_price_toman,
                            "line_base_total_rial": item.line_base_total_rial,
                            "line_discount_total_rial": item.line_discount_total_rial,
                            "line_effective_total_rial": item.line_effective_total_rial,
                            "line_effective_total_toman": item.line_effective_total_toman,
                            "formatted_line_effective_total_toman": item.formatted_line_effective_total_toman,
                        },
                    }
                )
            payload["items"] = items_list

        return payload
