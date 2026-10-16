"""
Authoritative Shopping Cart & Pricing Calculation Service.
Handles guest carts, authenticated user carts, atomic cart merging upon OTP login,
and strict server-side Rial/Toman calculations without floating-point arithmetic.
"""
from decimal import Decimal
import logging
from typing import Any
from uuid import UUID
from django.db import transaction
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from apps.accounts.models import User
from apps.catalog.models import ProductVariant
from apps.core.currency import (
    format_price_toman,
    rial_to_toman,
    validate_rial_amount,
)
from apps.orders.exceptions import (
    CartItemUnavailableError,
    CartQuantityBoundsError,
    InsufficientStockError,
)
from apps.orders.models import Cart, CartItem

logger = logging.getLogger(__name__)


class CartService:
    """Domain service encapsulating all shopping cart rules and calculations."""

    @staticmethod
    def _ensure_session_key(request: HttpRequest) -> str:
        """Guarantee that an anonymous request has a valid persisted session_key."""
        if not request.session.session_key:
            request.session.create()
        return str(request.session.session_key)

    @classmethod
    def get_active_cart(cls, request: HttpRequest, create: bool = False) -> Cart | None:
        """
        Retrieve the active cart for the current user or anonymous session.
        If `create=True`, atomically creates the cart if it does not exist.
        """
        if request.user.is_authenticated:
            user: User = request.user  # type: ignore[assignment]
            if create:
                cart, _ = Cart.objects.get_or_create(
                    user=user,
                    status=Cart.Status.ACTIVE,
                    defaults={"session_key": request.session.session_key},
                )
                return cart
            return Cart.objects.filter(user=user, status=Cart.Status.ACTIVE).first()

        session_key = request.session.session_key
        if not session_key:
            if not create:
                return None
            session_key = cls._ensure_session_key(request)

        if create:
            cart, _ = Cart.objects.get_or_create(
                user=None,
                session_key=session_key,
                status=Cart.Status.ACTIVE,
            )
            return cart

        return Cart.objects.filter(
            user__isnull=True,
            session_key=session_key,
            status=Cart.Status.ACTIVE,
        ).first()

    @staticmethod
    def _fetch_active_variant_for_update(variant_public_id: UUID | str) -> ProductVariant:
        """
        Fetch a ProductVariant with related objects and lock the row (`select_for_update`)
        to ensure stock and active flags are checked consistently inside a transaction.
        """
        try:
            variant = (
                ProductVariant.objects.select_for_update()
                .select_related("product", "packaging_type", "harvest_batch")
                .get(public_id=variant_public_id)
            )
        except (ProductVariant.DoesNotExist, ValueError, TypeError) as exc:
            raise CartItemUnavailableError(_("محصول یا گونه موردنظر یافت نشد.")) from exc

        if (
            not variant.is_active
            or not variant.product.is_active
            or not variant.packaging_type.is_active
            or not variant.harvest_batch.is_active
        ):
            raise CartItemUnavailableError(_("این گونه از محصول در حال حاضر غیرفعال است و قابل خرید نیست."))

        return variant

    @staticmethod
    def validate_variant_quantity(variant: ProductVariant, desired_quantity: int) -> None:
        """
        Validate that `desired_quantity` satisfies stock availability and min/max order bounds.
        """
        if desired_quantity < 1:
            raise CartQuantityBoundsError(_("تعداد محصول باید حداقل ۱ عدد باشد."))

        if variant.stock_quantity <= 0 or variant.stock_quantity < variant.min_order_quantity:
            raise InsufficientStockError(_("موجودی این محصول به پایان رسیده است."))

        if desired_quantity < variant.min_order_quantity:
            raise CartQuantityBoundsError(
                _("حداقل تعداد مجاز سفارش برای این محصول %(min_qty)d عدد است.")
                % {"min_qty": variant.min_order_quantity}
            )

        if desired_quantity > variant.max_order_quantity:
            raise CartQuantityBoundsError(
                _("حداکثر تعداد مجاز در هر سفارش برای این محصول %(max_qty)d عدد است.")
                % {"max_qty": variant.max_order_quantity}
            )

        if desired_quantity > variant.stock_quantity:
            raise InsufficientStockError(
                _("تعداد درخواستی بیش از موجودی قابل فروش انبار (%(stock)d عدد) است.")
                % {"stock": variant.stock_quantity}
            )

    @classmethod
    def add_item(
        cls,
        request: HttpRequest,
        variant_public_id: UUID | str,
        quantity_to_add: int = 1,
    ) -> CartItem:
        """
        Add a ProductVariant to the active cart (or increment quantity if already present).
        Executes atomically and validates cumulative quantity against stock and order bounds.
        """
        if quantity_to_add < 1:
            raise CartQuantityBoundsError(_("تعداد افزودنی به سبد خرید باید حداقل ۱ باشد."))

        with transaction.atomic():
            variant = cls._fetch_active_variant_for_update(variant_public_id)
            cart = cls.get_active_cart(request, create=True)
            assert cart is not None

            existing_item = (
                CartItem.objects.select_for_update()
                .filter(cart=cart, variant=variant)
                .first()
            )
            new_quantity = (existing_item.quantity if existing_item else 0) + int(quantity_to_add)
            cls.validate_variant_quantity(variant, new_quantity)

            if existing_item:
                existing_item.quantity = new_quantity
                existing_item.save(update_fields=["quantity", "updated_at"])
                cart.save(update_fields=["updated_at"])
                return existing_item

            new_item = CartItem.objects.create(
                cart=cart,
                variant=variant,
                quantity=new_quantity,
            )
            cart.save(update_fields=["updated_at"])
            return new_item

    @classmethod
    def update_item_quantity(
        cls,
        request: HttpRequest,
        variant_public_id: UUID | str,
        new_quantity: int,
    ) -> CartItem | None:
        """
        Set exact quantity for a variant in the active cart.
        If `new_quantity == 0`, the item is removed from the cart.
        """
        if new_quantity < 0:
            raise CartQuantityBoundsError(_("تعداد محصول نمی‌تواند منفی باشد."))

        with transaction.atomic():
            cart = cls.get_active_cart(request, create=False)
            if cart is None:
                raise CartItemUnavailableError(_("سبد خرید فعالی یافت نشد."))

            if new_quantity == 0:
                deleted_count, _ = CartItem.objects.filter(
                    cart=cart,
                    variant__public_id=variant_public_id,
                ).delete()
                if deleted_count == 0:
                    raise CartItemUnavailableError(_("این محصول در سبد خرید شما وجود ندارد."))
                cart.save(update_fields=["updated_at"])
                return None

            variant = cls._fetch_active_variant_for_update(variant_public_id)
            item = (
                CartItem.objects.select_for_update()
                .filter(cart=cart, variant=variant)
                .first()
            )
            if item is None:
                raise CartItemUnavailableError(_("این محصول در سبد خرید شما وجود ندارد."))

            cls.validate_variant_quantity(variant, int(new_quantity))
            item.quantity = int(new_quantity)
            item.save(update_fields=["quantity", "updated_at"])
            cart.save(update_fields=["updated_at"])
            return item

    @classmethod
    def remove_item(cls, request: HttpRequest, variant_public_id: UUID | str) -> bool:
        """Remove a specific variant line item from the active cart."""
        with transaction.atomic():
            cart = cls.get_active_cart(request, create=False)
            if cart is None:
                return False
            deleted_count, _ = CartItem.objects.filter(
                cart=cart,
                variant__public_id=variant_public_id,
            ).delete()
            if deleted_count > 0:
                cart.save(update_fields=["updated_at"])
                return True
            return False

    @classmethod
    def clear_cart(cls, request: HttpRequest) -> None:
        """Remove all items from the active cart."""
        with transaction.atomic():
            cart = cls.get_active_cart(request, create=False)
            if cart is not None:
                cart.items.all().delete()
                cart.save(update_fields=["updated_at"])

    @classmethod
    def merge_guest_cart_into_user_cart(
        cls,
        user: User,
        guest_session_key: str | None,
    ) -> Cart | None:
        """
        Atomically merge an anonymous guest cart (`guest_session_key`) into the
        authenticated user's active cart upon OTP login.
        Clamps merged quantities to `min(combined_qty, max_order_quantity, stock_quantity)`
        so login never crashes while strictly enforcing stock and order ceilings.
        """
        if not guest_session_key or not isinstance(guest_session_key, str):
            return None

        with transaction.atomic():
            guest_cart = (
                Cart.objects.select_for_update()
                .filter(
                    user__isnull=True,
                    session_key=guest_session_key,
                    status=Cart.Status.ACTIVE,
                )
                .first()
            )
            if guest_cart is None:
                return None

            guest_items = list(
                guest_cart.items.select_related(
                    "variant",
                    "variant__product",
                    "variant__packaging_type",
                    "variant__harvest_batch",
                )
            )

            user_cart, _ = Cart.objects.select_for_update().get_or_create(
                user=user,
                status=Cart.Status.ACTIVE,
            )

            for guest_item in guest_items:
                variant = guest_item.variant
                # Skip inactive or out-of-stock variants safely during merge
                if (
                    not variant.is_active
                    or not variant.product.is_active
                    or not variant.packaging_type.is_active
                    or not variant.harvest_batch.is_active
                    or variant.stock_quantity < variant.min_order_quantity
                ):
                    continue

                user_item = (
                    CartItem.objects.select_for_update()
                    .filter(cart=user_cart, variant=variant)
                    .first()
                )
                existing_qty = user_item.quantity if user_item else 0
                combined_qty = existing_qty + guest_item.quantity

                allowed_ceiling = min(variant.max_order_quantity, variant.stock_quantity)
                clamped_qty = min(combined_qty, allowed_ceiling)

                if clamped_qty < variant.min_order_quantity:
                    continue

                if user_item:
                    user_item.quantity = clamped_qty
                    user_item.save(update_fields=["quantity", "updated_at"])
                else:
                    CartItem.objects.create(
                        cart=user_cart,
                        variant=variant,
                        quantity=clamped_qty,
                    )

            # Mark guest cart as MERGED and clear its items
            guest_cart.items.all().delete()
            guest_cart.status = Cart.Status.MERGED
            guest_cart.save(update_fields=["status", "updated_at"])
            user_cart.save(update_fields=["updated_at"])

            logger.info(
                "Merged guest cart (%s) into user cart (%s) for user_id=%s",
                guest_cart.public_id,
                user_cart.public_id,
                user.pk,
            )
            return user_cart

    @classmethod
    def serialize_cart(cls, cart: Cart | None) -> dict[str, Any]:
        """
        Compute authoritative server-side totals (in IRR and IRT) and serialize cart state.
        Zero floating-point operations are used.
        """
        if cart is None:
            return {
                "cart_public_id": None,
                "items_count": 0,
                "total_units_count": 0,
                "total_gross_weight_grams": "0.000",
                "has_stock_warnings": False,
                "pricing": {
                    "subtotal_base_rial": 0,
                    "subtotal_base_toman": 0,
                    "formatted_subtotal_base_toman": format_price_toman(0),
                    "total_discount_rial": 0,
                    "total_discount_toman": 0,
                    "formatted_total_discount_toman": format_price_toman(0),
                    "payable_rial": 0,
                    "payable_toman": 0,
                    "formatted_payable_toman": format_price_toman(0),
                },
                "items": [],
            }

        items_qs = cart.items.select_related(
            "variant",
            "variant__product",
            "variant__packaging_type",
            "variant__harvest_batch",
        ).order_by("created_at", "id")

        serialized_items: list[dict[str, Any]] = []
        subtotal_base_rial = 0
        payable_rial = 0
        total_units_count = 0
        total_gross_weight = Decimal("0.000")
        has_stock_warnings = False

        for item in items_qs:
            variant = item.variant
            is_available = (
                variant.is_active
                and variant.product.is_active
                and variant.packaging_type.is_active
                and variant.harvest_batch.is_active
                and variant.stock_quantity >= item.quantity
                and variant.min_order_quantity <= item.quantity <= variant.max_order_quantity
            )
            if not is_available:
                has_stock_warnings = True

            line_base = item.line_base_total_rial
            line_payable = item.line_effective_total_rial
            line_discount = item.line_discount_total_rial
            line_weight = item.line_gross_weight_grams

            subtotal_base_rial += line_base
            payable_rial += line_payable
            total_units_count += item.quantity
            total_gross_weight += line_weight

            serialized_items.append(
                {
                    "item_public_id": str(item.public_id),
                    "variant_public_id": str(variant.public_id),
                    "sku": variant.sku,
                    "product_name": variant.product.name,
                    "product_slug": variant.product.slug,
                    "saffron_grade_label": variant.product.get_saffron_grade_display(),
                    "packaging_name": variant.packaging_type.name,
                    "weight_label": variant.weight_label,
                    "batch_code": variant.harvest_batch.batch_code,
                    "quantity": item.quantity,
                    "is_available_for_checkout": is_available,
                    "available_stock": variant.stock_quantity,
                    "line_gross_weight_grams": str(line_weight),
                    "pricing": {
                        "unit_base_price_rial": item.unit_base_price_rial,
                        "unit_base_price_toman": rial_to_toman(item.unit_base_price_rial),
                        "unit_effective_price_rial": item.unit_effective_price_rial,
                        "unit_effective_price_toman": rial_to_toman(item.unit_effective_price_rial),
                        "line_base_total_rial": line_base,
                        "line_base_total_toman": rial_to_toman(line_base),
                        "line_discount_total_rial": line_discount,
                        "line_discount_total_toman": rial_to_toman(line_discount),
                        "line_effective_total_rial": line_payable,
                        "line_effective_total_toman": item.line_effective_total_toman,
                        "formatted_line_effective_total_toman": item.formatted_line_effective_total_toman,
                    },
                }
            )

        subtotal_base_rial = validate_rial_amount(subtotal_base_rial)
        payable_rial = validate_rial_amount(payable_rial)
        total_discount_rial = validate_rial_amount(subtotal_base_rial - payable_rial)

        return {
            "cart_public_id": str(cart.public_id),
            "items_count": len(serialized_items),
            "total_units_count": total_units_count,
            "total_gross_weight_grams": str(total_gross_weight.quantize(Decimal("0.001"))),
            "has_stock_warnings": has_stock_warnings,
            "pricing": {
                "subtotal_base_rial": subtotal_base_rial,
                "subtotal_base_toman": rial_to_toman(subtotal_base_rial),
                "formatted_subtotal_base_toman": format_price_toman(subtotal_base_rial),
                "total_discount_rial": total_discount_rial,
                "total_discount_toman": rial_to_toman(total_discount_rial),
                "formatted_total_discount_toman": format_price_toman(total_discount_rial),
                "payable_rial": payable_rial,
                "payable_toman": rial_to_toman(payable_rial),
                "formatted_payable_toman": format_price_toman(payable_rial),
            },
            "items": serialized_items,
        }