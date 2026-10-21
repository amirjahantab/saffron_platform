"""
Domain models for Shopping Cart (Sub-phase 4.1) and Orders, OrderItems,
ShippingAddresses, and StockReservations (Sub-phase 4.2).
"""
from collections.abc import Collection
from decimal import Decimal
import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.accounts.validators import normalize_iranian_phone, validate_iranian_phone
from apps.catalog.models import ProductVariant, SaffronGrade
from apps.core.currency import (
    RIAL_TO_TOMAN_FACTOR,
    format_price_toman,
    rial_to_toman,
    validate_rial_amount,
)
from apps.core.exceptions import MonetaryPrecisionError
from apps.core.models import TimeStampedModel, UUIDModel
from apps.orders.validators import normalize_iranian_postal_code, validate_iranian_postal_code


def generate_unique_order_number() -> str:
    """Generate a human-readable, collision-resistant order number (e.g. JHT-20261016-A1B2C3D4)."""
    now_str = timezone.now().strftime("%Y%m%d")
    random_hex = secrets.token_hex(4).upper()
    return f"JHT-{now_str}-{random_hex}"


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


class ShippingAddress(TimeStampedModel, UUIDModel):
    """
    Reusable customer shipping address book entry.
    Note: Orders copy these fields into immutable snapshot columns at checkout time
    so future edits to a ShippingAddress never alter historical order records.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shipping_addresses",
        verbose_name=_("کاربر"),
    )
    recipient_full_name = models.CharField(
        max_length=150,
        verbose_name=_("نام و نام خانوادگی گیرنده"),
    )
    recipient_phone = models.CharField(
        max_length=11,
        validators=[validate_iranian_phone],
        verbose_name=_("شماره موبایل گیرنده"),
    )
    province = models.CharField(
        max_length=80,
        verbose_name=_("استان"),
    )
    city = models.CharField(
        max_length=80,
        verbose_name=_("شهر"),
    )
    address_line = models.TextField(
        max_length=500,
        verbose_name=_("نشانی کامل پستی"),
    )
    postal_code = models.CharField(
        max_length=10,
        validators=[validate_iranian_postal_code],
        verbose_name=_("کد پستی ۱۰ رقمی"),
    )
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("آدرس پیش‌فرض"),
    )

    class Meta:
        verbose_name = _("آدرس ارسال")
        verbose_name_plural = _("آدرس‌های ارسال")
        ordering = ["-is_default", "-created_at"]

    def __str__(self) -> str:
        return f"{self.recipient_full_name} - {self.province}، {self.city} ({self.postal_code})"

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        exclude_set = set(exclude or ())
        if "recipient_phone" not in exclude_set and self.recipient_phone:
            try:
                self.recipient_phone = normalize_iranian_phone(self.recipient_phone)
            except ValidationError:
                pass
        if "postal_code" not in exclude_set and self.postal_code:
            try:
                self.postal_code = normalize_iranian_postal_code(self.postal_code)
            except ValidationError:
                pass
        super().clean_fields(exclude=exclude)

    def clean(self) -> None:
        super().clean()
        if self.recipient_phone:
            self.recipient_phone = normalize_iranian_phone(self.recipient_phone)
        if self.postal_code:
            self.postal_code = normalize_iranian_postal_code(self.postal_code)


class Order(TimeStampedModel, UUIDModel):
    """
    Authoritative Customer Order record.
    Stores immutable recipient address snapshots, strict integer Rial monetary totals,
    shipping metadata, and order lifecycle state.
    """

    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", _("در انتظار پرداخت")
        PAID = "paid", _("پرداخت‌شده")
        PROCESSING = "processing", _("در حال آماده‌سازی و بسته‌بندی")
        SHIPPED = "shipped", _("تحویل‌شده به پست / ارسال‌شده")
        DELIVERED = "delivered", _("تحویل‌شده به مشتری")
        CANCELLED = "cancelled", _("لغوشده")
        EXPIRED = "expired", _("منقضی‌شده (عدم پرداخت در مهلت رزرو)")
        REFUNDED = "refunded", _("مستردشده (بازگشت وجه)")

    class ShippingMethod(models.TextChoices):
        POST_PISHTAZ = "post_pishtaz", _("پست پیشتاز")
        TIPAX = "tipax", _("تیپاکس")
        COURIER_MASHHAD = "courier_mashhad", _("پیک ویژه مشهد")
        FREIGHT_WHOLESALE = "freight_wholesale", _("باربری (ویژه سفارش عمده)")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="orders",
        verbose_name=_("مشتری"),
    )
    guest_access_hash = models.CharField(max_length=64, blank=True, editable=False)
    source_cart = models.ForeignKey(
        Cart,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="orders",
        verbose_name=_("سبد خرید منشأ"),
    )
    order_number = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        default=generate_unique_order_number,
        editable=False,
        verbose_name=_("شماره سفارش"),
    )
    idempotency_key = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_("کلید یکتای جلوگیری از تکرار (Idempotency Key)"),
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
        db_index=True,
        verbose_name=_("وضعیت سفارش"),
    )

    # Immutable Recipient & Shipping Snapshot
    recipient_full_name = models.CharField(
        max_length=150,
        verbose_name=_("نام و نام خانوادگی گیرنده"),
    )
    recipient_phone = models.CharField(
        max_length=11,
        validators=[validate_iranian_phone],
        verbose_name=_("شماره موبایل گیرنده"),
    )
    province = models.CharField(
        max_length=80,
        verbose_name=_("استان"),
    )
    city = models.CharField(
        max_length=80,
        verbose_name=_("شهر"),
    )
    address_line = models.TextField(
        max_length=500,
        verbose_name=_("نشانی کامل پستی"),
    )
    postal_code = models.CharField(
        max_length=10,
        validators=[validate_iranian_postal_code],
        verbose_name=_("کد پستی ۱۰ رقمی"),
    )
    shipping_method = models.CharField(
        max_length=30,
        choices=ShippingMethod.choices,
        default=ShippingMethod.POST_PISHTAZ,
        verbose_name=_("روش ارسال"),
    )
    tracking_code = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        verbose_name=_("کد رهگیری مرسوله پستی"),
    )
    total_gross_weight_grams = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal("0.000"),
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name=_("وزن ناخالص کل مرسوله (گرم)"),
    )
    customer_note = models.TextField(
        max_length=500,
        blank=True,
        verbose_name=_("توضیحات مشتری"),
    )
    cancel_reason = models.CharField(
        max_length=250,
        blank=True,
        verbose_name=_("علت لغو یا انقضا"),
    )

    # Authoritative Monetary Totals in Rials (IRR)
    subtotal_base_rial = models.PositiveBigIntegerField(
        verbose_name=_("جمع کل قیمت پایه اقلام (ریال)"),
    )
    total_discount_rial = models.PositiveBigIntegerField(
        default=0,
        verbose_name=_("مجموع تخفیف اقلام (ریال)"),
    )
    shipping_cost_rial = models.PositiveBigIntegerField(
        default=0,
        verbose_name=_("هزینه ارسال (ریال)"),
    )
    payable_rial = models.PositiveBigIntegerField(
        verbose_name=_("مبلغ نهایی قابل پرداخت (ریال)"),
    )

    # Lifecycle Timestamps
    reservation_expires_at = models.DateTimeField(
        db_index=True,
        verbose_name=_("مهلت انقضای رزرو موجودی و پرداخت"),
    )
    paid_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("زمان پرداخت"),
    )
    shipped_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("زمان ارسال"),
    )
    delivered_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("زمان تحویل"),
    )
    cancelled_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("زمان لغو یا انقضا"),
    )

    class Meta:
        verbose_name = _("سفارش")
        verbose_name_plural = _("سفارش‌ها")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(user__isnull=False) | ~Q(guest_access_hash=""), name="order_has_account_or_guest_secret"),
            models.UniqueConstraint(fields=["source_cart"], condition=Q(user__isnull=True, source_cart__isnull=False), name="one_guest_order_per_cart"),
            models.UniqueConstraint(
                fields=["user", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_order_idempotency_per_user",
            ),
            models.CheckConstraint(
                condition=Q(subtotal_base_rial__gt=0)
                & Q(total_discount_rial__lte=F("subtotal_base_rial"))
                & Q(payable_rial__gt=0),
                name="order_monetary_totals_valid_bounds",
            ),
            models.CheckConstraint(
                condition=Q(
                    payable_rial=(F("subtotal_base_rial") - F("total_discount_rial"))
                    + F("shipping_cost_rial")
                ),
                name="order_payable_equals_subtotal_minus_discount_plus_shipping",
            ),
        ]

    def __str__(self) -> str:
        return f"سفارش {self.order_number} - {self.user} [{self.get_status_display()}]"

    @property
    def subtotal_base_toman(self) -> int:
        return rial_to_toman(int(self.subtotal_base_rial))

    @property
    def total_discount_toman(self) -> int:
        return rial_to_toman(int(self.total_discount_rial))

    @property
    def shipping_cost_toman(self) -> int:
        return rial_to_toman(int(self.shipping_cost_rial))

    @property
    def payable_toman(self) -> int:
        return rial_to_toman(int(self.payable_rial))

    @property
    def formatted_payable_toman(self) -> str:
        return format_price_toman(int(self.payable_rial))

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        exclude_set = set(exclude or ())
        if "recipient_phone" not in exclude_set and self.recipient_phone:
            try:
                self.recipient_phone = normalize_iranian_phone(self.recipient_phone)
            except ValidationError:
                pass
        if "postal_code" not in exclude_set and self.postal_code:
            try:
                self.postal_code = normalize_iranian_postal_code(self.postal_code)
            except ValidationError:
                pass
        super().clean_fields(exclude=exclude)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[ValidationError]] = {}

        if self.recipient_phone:
            try:
                self.recipient_phone = normalize_iranian_phone(self.recipient_phone)
            except ValidationError as exc:
                errors.setdefault("recipient_phone", []).append(exc)

        if self.postal_code:
            try:
                self.postal_code = normalize_iranian_postal_code(self.postal_code)
            except ValidationError as exc:
                errors.setdefault("postal_code", []).append(exc)

        if self.idempotency_key is not None:
            cleaned_key = self.idempotency_key.strip()
            self.idempotency_key = cleaned_key if cleaned_key else None

        # Validate Rial amounts according to the strict monetary contract
        for field_name in ("subtotal_base_rial", "total_discount_rial", "shipping_cost_rial", "payable_rial"):
            val = getattr(self, field_name)
            if val is None:
                errors.setdefault(field_name, []).append(ValidationError(_("مقدار ریالی الزامی است.")))
                continue
            try:
                validate_rial_amount(int(val))
            except MonetaryPrecisionError:
                errors.setdefault(field_name, []).append(
                    ValidationError(
                        _("مبلغ باید عدد صحیح نامنفی و مضرب %(factor)d ریال باشد."),
                        params={"factor": RIAL_TO_TOMAN_FACTOR},
                    )
                )

        if not errors:
            if self.subtotal_base_rial <= 0:
                errors.setdefault("subtotal_base_rial", []).append(
                    ValidationError(_("جمع کل قیمت پایه اقلام باید بزرگ‌تر از صفر باشد."))
                )
            if self.total_discount_rial > self.subtotal_base_rial:
                errors.setdefault("total_discount_rial", []).append(
                    ValidationError(_("مجموع تخفیف نمی‌تواند بیشتر از جمع کل قیمت پایه باشد."))
                )
            expected_payable = (
                int(self.subtotal_base_rial) - int(self.total_discount_rial) + int(self.shipping_cost_rial)
            )
            if int(self.payable_rial) != expected_payable:
                errors.setdefault("payable_rial", []).append(
                    ValidationError(
                        _("مبلغ قابل پرداخت (%(actual)d) با فرمول (جمع پایه - تخفیف + هزینه ارسال = %(expected)d) هم‌خوانی ندارد."),
                        params={"actual": self.payable_rial, "expected": expected_payable},
                    )
                )

        if errors:
            raise ValidationError(errors)


class OrderItem(TimeStampedModel, UUIDModel):
    """
    Immutable line item snapshot within an Order.
    Captures exact product, packaging, harvest batch traceability, and Rial prices
    at the moment of order placement.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("سفارش"),
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name=_("گونه محصول مرجع"),
    )

    # Immutable Product & Batch Traceability Snapshots
    product_name_snapshot = models.CharField(
        max_length=180,
        verbose_name=_("نام محصول (در لحظه خرید)"),
    )
    sku_snapshot = models.CharField(
        max_length=64,
        verbose_name=_("کد SKU (در لحظه خرید)"),
    )
    saffron_grade_snapshot = models.CharField(
        max_length=20,
        choices=SaffronGrade.choices,
        verbose_name=_("نوع زعفران (در لحظه خرید)"),
    )
    packaging_name_snapshot = models.CharField(
        max_length=100,
        verbose_name=_("نوع بسته‌بندی (در لحظه خرید)"),
    )
    weight_label_snapshot = models.CharField(
        max_length=60,
        verbose_name=_("عنوان وزن (در لحظه خرید)"),
    )
    net_weight_grams_snapshot = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name=_("وزن خالص واحد (گرم)"),
    )
    batch_code_snapshot = models.CharField(
        max_length=50,
        verbose_name=_("کد رهگیری بچ تولید (در لحظه خرید)"),
    )
    origin_region_snapshot = models.CharField(
        max_length=120,
        verbose_name=_("منطقه کشت (در لحظه خرید)"),
    )
    harvest_year_snapshot = models.PositiveSmallIntegerField(
        verbose_name=_("سال برداشت (در لحظه خرید)"),
    )

    # Quantity & Immutable Monetary Snapshots in Rials (IRR)
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("تعداد"),
    )
    unit_base_price_rial = models.PositiveBigIntegerField(
        verbose_name=_("قیمت پایه واحد (ریال)"),
    )
    unit_effective_price_rial = models.PositiveBigIntegerField(
        verbose_name=_("قیمت نهایی واحد پس از تخفیف (ریال)"),
    )
    line_base_total_rial = models.PositiveBigIntegerField(
        verbose_name=_("جمع قیمت پایه ردیف (ریال)"),
    )
    line_discount_total_rial = models.PositiveBigIntegerField(
        default=0,
        verbose_name=_("جمع تخفیف ردیف (ریال)"),
    )
    line_effective_total_rial = models.PositiveBigIntegerField(
        verbose_name=_("مبلغ نهایی ردیف (ریال)"),
    )

    class Meta:
        verbose_name = _("قلم سفارش")
        verbose_name_plural = _("اقلام سفارش")
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "variant"],
                name="unique_variant_per_order",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1)
                & Q(unit_base_price_rial__gt=0)
                & Q(unit_effective_price_rial__gt=0)
                & Q(unit_effective_price_rial__lte=F("unit_base_price_rial"))
                & Q(line_effective_total_rial__gt=0),
                name="order_item_valid_quantity_and_prices",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_name_snapshot} ({self.sku_snapshot}) × {self.quantity}"

    @property
    def unit_effective_price_toman(self) -> int:
        return rial_to_toman(int(self.unit_effective_price_rial))

    @property
    def line_effective_total_toman(self) -> int:
        return rial_to_toman(int(self.line_effective_total_rial))

    @property
    def formatted_line_effective_total_toman(self) -> str:
        return format_price_toman(int(self.line_effective_total_rial))

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[ValidationError]] = {}

        if not self.quantity or self.quantity < 1:
            errors.setdefault("quantity", []).append(ValidationError(_("تعداد باید حداقل ۱ باشد.")))

        for field_name in (
            "unit_base_price_rial",
            "unit_effective_price_rial",
            "line_base_total_rial",
            "line_discount_total_rial",
            "line_effective_total_rial",
        ):
            val = getattr(self, field_name)
            if val is None:
                errors.setdefault(field_name, []).append(ValidationError(_("مقدار ریالی الزامی است.")))
                continue
            try:
                validate_rial_amount(int(val))
            except MonetaryPrecisionError:
                errors.setdefault(field_name, []).append(
                    ValidationError(
                        _("مبلغ باید مضرب %(factor)d ریال باشد."),
                        params={"factor": RIAL_TO_TOMAN_FACTOR},
                    )
                )

        if not errors:
            if self.unit_effective_price_rial > self.unit_base_price_rial:
                errors.setdefault("unit_effective_price_rial", []).append(
                    ValidationError(_("قیمت نهایی واحد نمی‌تواند بیشتر از قیمت پایه واحد باشد."))
                )
            expected_line_base = int(self.unit_base_price_rial) * int(self.quantity)
            expected_line_effective = int(self.unit_effective_price_rial) * int(self.quantity)
            expected_line_discount = expected_line_base - expected_line_effective

            if int(self.line_base_total_rial) != expected_line_base:
                errors.setdefault("line_base_total_rial", []).append(
                    ValidationError(_("جمع قیمت پایه ردیف با حاصل‌ضرب تعداد در قیمت پایه واحد برابر نیست."))
                )
            if int(self.line_effective_total_rial) != expected_line_effective:
                errors.setdefault("line_effective_total_rial", []).append(
                    ValidationError(_("مبلغ نهایی ردیف با حاصل‌ضرب تعداد در قیمت نهایی واحد برابر نیست."))
                )
            if int(self.line_discount_total_rial) != expected_line_discount:
                errors.setdefault("line_discount_total_rial", []).append(
                    ValidationError(_("جمع تخفیف ردیف با تفاضل قیمت پایه و نهایی برابر نیست."))
                )

        if errors:
            raise ValidationError(errors)


class StockReservation(TimeStampedModel, UUIDModel):
    """
    Time-bound inventory reservation tied to an Order and a ProductVariant.
    Prevents overselling during payment gateway redirects while guaranteeing that
    abandoned or failed payments return their reserved stock to the catalog.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", _("رزرو فعال (در انتظار پرداخت)")
        COMMITTED = "committed", _("قطعی‌شده (پرداخت موفق)")
        RELEASED = "released", _("آزادشده (لغو سفارش یا خطای پرداخت)")
        EXPIRED = "expired", _("منقضی و آزادشده (پایان مهلت پرداخت)")

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name=_("سفارش"),
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="stock_reservations",
        verbose_name=_("گونه محصول"),
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("تعداد رزروشده"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name=_("وضعیت رزرو"),
    )
    expires_at = models.DateTimeField(
        db_index=True,
        verbose_name=_("زمان انقضای رزرو"),
    )
    committed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("زمان قطعی‌شدن رزرو"),
    )
    released_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("زمان آزادسازی موجودی"),
    )

    class Meta:
        verbose_name = _("رزرو موجودی انبار")
        verbose_name_plural = _("رزروهای موجودی انبار")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "variant"],
                name="unique_reservation_per_order_variant",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1),
                name="stock_reservation_quantity_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"رزرو {self.variant.sku} × {self.quantity} برای {self.order.order_number} [{self.get_status_display()}]"

    @property
    def is_overdue(self) -> bool:
        return self.status == self.Status.ACTIVE and timezone.now() >= self.expires_at