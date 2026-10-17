"""
Database models for Payment Transactions and Refunds (Sub-phase 5.1).

Security & Financial Guarantees:
1. All monetary amounts (`amount_rial`, `fee_rial`) are stored in integer Rials (IRR, multiple of 10).
2. At most ONE transaction per Order can ever reach `SUCCEEDED` status (`unique_succeeded_payment_per_order`).
3. Gateway `authority` and bank `reference_id` are uniquely constrained per provider to prevent Replay Attacks.
"""
from collections.abc import Collection
import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from apps.core.currency import (
    RIAL_TO_TOMAN_FACTOR,
    format_price_toman,
    rial_to_toman,
    validate_rial_amount,
)
from apps.core.exceptions import MonetaryPrecisionError
from apps.core.models import TimeStampedModel, UUIDModel
from apps.orders.models import Order


def generate_payment_idempotency_token() -> str:
    """Generate a unique 32-character hex token for payment attempt idempotency."""
    return secrets.token_hex(16)


class PaymentProvider(models.TextChoices):
    """Supported payment gateway providers."""

    ZARINPAL = "zarinpal", _("درگاه پرداخت زرین‌پال")
    SANDBOX = "sandbox", _("درگاه آزمایشی توسعه (Sandbox)")


class PaymentTransaction(TimeStampedModel, UUIDModel):
    """
    Represents an individual payment gateway transaction attempt for an Order.
    An Order may have multiple failed/expired attempts, but at most one SUCCEEDED transaction.
    """

    class Status(models.TextChoices):
        INITIATED = "initiated", _("ایجادشده (در حال هدایت به درگاه)")
        PENDING_VERIFICATION = "pending_verification", _("بازگشت از درگاه (در انتظار تأیید سرور)")
        SUCCEEDED = "succeeded", _("پرداخت موفق و تأییدشده")
        FAILED = "failed", _("پرداخت ناموفق یا لغوشده توسط کاربر")
        EXPIRED = "expired", _("منقضی‌شده")
        REFUNDED = "refunded", _("مستردشده (بازگشت وجه)")

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("سفارش مرتبط"),
    )
    provider = models.CharField(
        max_length=30,
        choices=PaymentProvider.choices,
        default=PaymentProvider.ZARINPAL,
        db_index=True,
        verbose_name=_("ارائه‌دهنده درگاه"),
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.INITIATED,
        db_index=True,
        verbose_name=_("وضعیت تراکنش"),
    )
    amount_rial = models.PositiveBigIntegerField(
        verbose_name=_("مبلغ تراکنش (ریال)"),
    )
    fee_rial = models.PositiveBigIntegerField(
        default=0,
        verbose_name=_("کارمزد درگاه (ریال)"),
    )
    authority = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_("شناسه مرجع درگاه (Authority / Token)"),
    )
    reference_id = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_("شماره پیگیری بانکی (Ref ID)"),
    )
    card_pan_masked = models.CharField(
        max_length=32,
        blank=True,
        verbose_name=_("شماره کارت ماسک‌شده"),
    )
    card_hash = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("هش کارت بانکی (SHA256)"),
    )
    idempotency_key = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        default=generate_payment_idempotency_token,
        verbose_name=_("کلید یکتای تلاش پرداخت"),
    )
    callback_status_param = models.CharField(
        max_length=32,
        blank=True,
        verbose_name=_("پارامتر وضعیت بازگشتی مرورگر"),
    )
    failure_code = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("کد خطای درگاه"),
    )
    failure_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("علت عدم موفقیت"),
    )
    raw_request_response = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("پاسخ خام ایجاد پرداخت"),
    )
    raw_verify_response = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("پاسخ خام تأیید پرداخت (سمت سرور)"),
    )
    verified_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("زمان تأیید سمت سرور"),
    )

    class Meta:
        verbose_name = _("تراکنش پرداخت")
        verbose_name_plural = _("تراکنش‌های پرداخت")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "authority"],
                condition=Q(authority__isnull=False),
                name="unique_payment_provider_authority",
            ),
            models.UniqueConstraint(
                fields=["provider", "reference_id"],
                condition=Q(reference_id__isnull=False),
                name="unique_payment_provider_reference_id",
            ),
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(status="succeeded"),
                name="unique_succeeded_payment_per_order",
            ),
            models.CheckConstraint(
                condition=Q(amount_rial__gt=0),
                name="payment_transaction_amount_rial_positive",
            ),
        ]

    def __str__(self) -> str:
        ref = self.reference_id or self.authority or str(self.public_id)[:8]
        return f"تراکنش {ref} - سفارش {self.order.order_number} [{self.get_status_display()}]"

    @property
    def amount_toman(self) -> int:
        return rial_to_toman(int(self.amount_rial))

    @property
    def formatted_amount_toman(self) -> str:
        return format_price_toman(int(self.amount_rial))

    def _normalize_nullable_unique_fields(self) -> None:
        """Convert blank strings to None so nullable UniqueConstraints work cleanly."""
        if self.authority is not None:
            cleaned_auth = self.authority.strip()
            self.authority = cleaned_auth if cleaned_auth else None
        if self.reference_id is not None:
            cleaned_ref = self.reference_id.strip()
            self.reference_id = cleaned_ref if cleaned_ref else None

    def clean_fields(self, exclude: Collection[str] | None = None) -> None:
        self._normalize_nullable_unique_fields()
        super().clean_fields(exclude=exclude)

    def clean(self) -> None:
        super().clean()
        self._normalize_nullable_unique_fields()
        errors: dict[str, list[ValidationError]] = {}

        if self.amount_rial is None or self.amount_rial <= 0:
            errors.setdefault("amount_rial", []).append(
                ValidationError(_("مبلغ تراکنش باید بزرگ‌تر از صفر باشد."))
            )
        else:
            try:
                validate_rial_amount(int(self.amount_rial))
            except MonetaryPrecisionError:
                errors.setdefault("amount_rial", []).append(
                    ValidationError(
                        _("مبلغ تراکنش باید عدد صحیح و مضرب %(factor)d ریال باشد."),
                        params={"factor": RIAL_TO_TOMAN_FACTOR},
                    )
                )

        if self.order_id and self.amount_rial:
            if int(self.amount_rial) != int(self.order.payable_rial):
                errors.setdefault("amount_rial", []).append(
                    ValidationError(
                        _("مبلغ تراکنش (%(tx_amount)d ریال) باید دقیقاً برابر با مبلغ قابل پرداخت سفارش (%(order_amount)d ریال) باشد."),
                        params={
                            "tx_amount": self.amount_rial,
                            "order_amount": self.order.payable_rial,
                        },
                    )
                )

        if self.status == self.Status.SUCCEEDED and not self.reference_id:
            errors.setdefault("reference_id", []).append(
                ValidationError(_("ثبت شماره پیگیری بانکی (reference_id) برای تراکنش موفق الزامی است."))
            )

        if errors:
            raise ValidationError(errors)


class PaymentRefund(TimeStampedModel, UUIDModel):
    """
    Audit and financial record for a payment refund (full or partial).
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("در انتظار پردازش بازگشت وجه")
        SUCCEEDED = "succeeded", _("بازگشت وجه انجام شد")
        FAILED = "failed", _("خطا در بازگشت وجه")

    payment = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name=_("تراکنش پرداخت مرجع"),
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name=_("سفارش مرتبط"),
    )
    amount_rial = models.PositiveBigIntegerField(
        verbose_name=_("مبلغ بازگشت وجه (ریال)"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name=_("وضعیت استرداد"),
    )
    reason = models.CharField(
        max_length=255,
        verbose_name=_("علت بازگشت وجه"),
    )
    provider_refund_id = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_("شناسه پیگیری استرداد درگاه/بانک"),
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="processed_refunds",
        verbose_name=_("ثبت‌کننده استرداد"),
    )
    processed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("زمان انجام بازگشت وجه"),
    )

    class Meta:
        verbose_name = _("بازگشت وجه (استرداد)")
        verbose_name_plural = _("بازگشت‌های وجه (استردادها)")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_rial__gt=0),
                name="payment_refund_amount_rial_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"استرداد {self.formatted_amount_toman} برای سفارش {self.order.order_number} [{self.get_status_display()}]"

    @property
    def amount_toman(self) -> int:
        return rial_to_toman(int(self.amount_rial))

    @property
    def formatted_amount_toman(self) -> str:
        return format_price_toman(int(self.amount_rial))

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[ValidationError]] = {}

        if self.amount_rial is None or self.amount_rial <= 0:
            errors.setdefault("amount_rial", []).append(
                ValidationError(_("مبلغ بازگشت وجه باید بزرگ‌تر از صفر باشد."))
            )
        else:
            try:
                validate_rial_amount(int(self.amount_rial))
            except MonetaryPrecisionError:
                errors.setdefault("amount_rial", []).append(
                    ValidationError(
                        _("مبلغ بازگشت وجه باید مضرب %(factor)d ریال باشد."),
                        params={"factor": RIAL_TO_TOMAN_FACTOR},
                    )
                )

        if self.payment_id and self.order_id:
            if self.payment.order_id != self.order_id:
                errors.setdefault("order", []).append(
                    ValidationError(_("سفارش انتخاب‌شده با سفارشِ تراکنش پرداخت هم‌خوانی ندارد."))
                )
            if self.amount_rial and int(self.amount_rial) > int(self.payment.amount_rial):
                errors.setdefault("amount_rial", []).append(
                    ValidationError(_("مبلغ بازگشت وجه نمی‌تواند بیشتر از مبلغ کل تراکنش پرداخت باشد."))
                )

        if errors:
            raise ValidationError(errors)