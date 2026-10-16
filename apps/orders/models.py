"""
Shopping Cart and CartItem models (Sub-phase 4.1).
Order, OrderItem, and StockReservation models will be added in Sub-phase 4.2.
"""
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from apps.catalog.models import ProductVariant
from apps.core.currency import (
    format_price_toman,
    rial_to_toman,
    validate_rial_amount,
)
from apps.core.models import TimeStampedModel, UUIDModel


class Cart(TimeStampedModel, UUIDModel):
    """
    Shopping Cart supporting both anonymous guests (via `session_key`)
    and authenticated users (via `user`).
    """

    class Status(models.TextChoices):
        ACTIVE = "active", _("فعال")
        MERGED = "merged", _("ادغام‌شده با حساب کاربری")
        CONVERTED = "converted", _("تبدیل‌شده به سفارش")
        ABANDONED = "abandoned", _("رهاشده")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="carts",
        verbose_name=_("کاربر"),
    )
    session_key = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_("کلید نشست مهمان"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name=_("وضعیت سبد"),
    )

    class Meta:
        verbose_name = _("سبد خرید")
        verbose_name_plural = _("سبدهای خرید")
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="active", user__isnull=False),
                name="unique_active_cart_per_user",
            ),
            models.UniqueConstraint(
                fields=["session_key"],
                condition=Q(status="active", user__isnull=True, session_key__isnull=False),
                name="unique_active_cart_per_guest_session",
            ),
            models.CheckConstraint(
                condition=Q(user__isnull=False) | Q(session_key__isnull=False),
                name="cart_requires_user_or_session_key",
            ),
        ]

    def __str__(self) -> str:
        owner = str(self.user) if self.user_id else f"مهمان ({self.session_key or 'بدون نشست'})"
        return f"سبد خرید {owner} [{self.get_status_display()}]"

    def clean(self) -> None:
        super().clean()
        if self.session_key is not None:
            cleaned_sk = self.session_key.strip()
            self.session_key = cleaned_sk if cleaned_sk else None
        if not self.user_id and not self.session_key:
            raise ValidationError(_("سبد خرید باید حداقل دارای یک کاربر یا کلید نشست مهمان باشد."))


class CartItem(TimeStampedModel, UUIDModel):
    """
    Individual SKU line item within a Cart.
    Security Contract: Never stores mutable client-provided prices; all unit and line
    prices are dynamically computed from the authoritative `ProductVariant` record.
    """

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("سبد خرید"),
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name=_("گونه محصول"),
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("تعداد"),
    )

    class Meta:
        verbose_name = _("آیتم سبد خرید")
        verbose_name_plural = _("آیتم‌های سبد خرید")
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "variant"],
                name="unique_variant_per_cart",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="cart_item_quantity_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.variant.sku} × {self.quantity}"

    @property
    def unit_base_price_rial(self) -> int:
        return validate_rial_amount(int(self.variant.base_price_rial))

    @property
    def unit_effective_price_rial(self) -> int:
        return validate_rial_amount(int(self.variant.effective_price_rial))

    @property
    def line_base_total_rial(self) -> int:
        return validate_rial_amount(self.unit_base_price_rial * int(self.quantity))

    @property
    def line_effective_total_rial(self) -> int:
        return validate_rial_amount(self.unit_effective_price_rial * int(self.quantity))

    @property
    def line_discount_total_rial(self) -> int:
        return validate_rial_amount(self.line_base_total_rial - self.line_effective_total_rial)

    @property
    def line_effective_total_toman(self) -> int:
        return rial_to_toman(self.line_effective_total_rial)

    @property
    def formatted_line_effective_total_toman(self) -> str:
        return format_price_toman(self.line_effective_total_rial)

    @property
    def line_gross_weight_grams(self) -> Decimal:
        return (self.variant.gross_weight_grams * Decimal(int(self.quantity))).quantize(Decimal("0.001"))