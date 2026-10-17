"""Initial schema migration for PaymentTransaction and PaymentRefund models (Sub-phase 5.1)."""
import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import apps.payments.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0002_order_models_and_reservations"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentTransaction",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        verbose_name="تاریخ ایجاد",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="تاریخ آخرین ویرایش",
                    ),
                ),
                (
                    "public_id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                        verbose_name="شناسه عمومی",
                    ),
                ),
                (
                    "provider",
                    models.CharField(
                        choices=[
                            ("zarinpal", "درگاه پرداخت زرین‌پال"),
                            ("sandbox", "درگاه آزمایشی توسعه (Sandbox)"),
                        ],
                        db_index=True,
                        default="zarinpal",
                        max_length=30,
                        verbose_name="ارائه‌دهنده درگاه",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("initiated", "ایجادشده (در حال هدایت به درگاه)"),
                            (
                                "pending_verification",
                                "بازگشت از درگاه (در انتظار تأیید سرور)",
                            ),
                            ("succeeded", "پرداخت موفق و تأییدشده"),
                            ("failed", "پرداخت ناموفق یا لغوشده توسط کاربر"),
                            ("expired", "منقضی‌شده"),
                            ("refunded", "مستردشده (بازگشت وجه)"),
                        ],
                        db_index=True,
                        default="initiated",
                        max_length=25,
                        verbose_name="وضعیت تراکنش",
                    ),
                ),
                (
                    "amount_rial",
                    models.PositiveBigIntegerField(verbose_name="مبلغ تراکنش (ریال)"),
                ),
                (
                    "fee_rial",
                    models.PositiveBigIntegerField(
                        default=0, verbose_name="کارمزد درگاه (ریال)"
                    ),
                ),
                (
                    "authority",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=128,
                        null=True,
                        verbose_name="شناسه مرجع درگاه (Authority / Token)",
                    ),
                ),
                (
                    "reference_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=128,
                        null=True,
                        verbose_name="شماره پیگیری بانکی (Ref ID)",
                    ),
                ),
                (
                    "card_pan_masked",
                    models.CharField(
                        blank=True,
                        max_length=32,
                        verbose_name="شماره کارت ماسک‌شده",
                    ),
                ),
                (
                    "card_hash",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="هش کارت بانکی (SHA256)",
                    ),
                ),
                (
                    "idempotency_key",
                    models.CharField(
                        db_index=True,
                        default=apps.payments.models.generate_payment_idempotency_token,
                        max_length=64,
                        unique=True,
                        verbose_name="کلید یکتای تلاش پرداخت",
                    ),
                ),
                (
                    "callback_status_param",
                    models.CharField(
                        blank=True,
                        max_length=32,
                        verbose_name="پارامتر وضعیت بازگشتی مرورگر",
                    ),
                ),
                (
                    "failure_code",
                    models.CharField(
                        blank=True, max_length=64, verbose_name="کد خطای درگاه"
                    ),
                ),
                (
                    "failure_reason",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="علت عدم موفقیت"
                    ),
                ),
                (
                    "raw_request_response",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="پاسخ خام ایجاد پرداخت",
                    ),
                ),
                (
                    "raw_verify_response",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="پاسخ خام تأیید پرداخت (سمت سرور)",
                    ),
                ),
                (
                    "verified_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="زمان تأیید سمت سرور"
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to="orders.order",
                        verbose_name="سفارش مرتبط",
                    ),
                ),
            ],
            options={
                "verbose_name": "تراکنش پرداخت",
                "verbose_name_plural": "تراکنش‌های پرداخت",
                "ordering": ["-created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=Q(authority__isnull=False),
                        fields=("provider", "authority"),
                        name="unique_payment_provider_authority",
                    ),
                    models.UniqueConstraint(
                        condition=Q(reference_id__isnull=False),
                        fields=("provider", "reference_id"),
                        name="unique_payment_provider_reference_id",
                    ),
                    models.UniqueConstraint(
                        condition=Q(status="succeeded"),
                        fields=("order",),
                        name="unique_succeeded_payment_per_order",
                    ),
                    models.CheckConstraint(
                        condition=Q(amount_rial__gt=0),
                        name="payment_transaction_amount_rial_positive",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PaymentRefund",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        verbose_name="تاریخ ایجاد",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="تاریخ آخرین ویرایش",
                    ),
                ),
                (
                    "public_id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                        verbose_name="شناسه عمومی",
                    ),
                ),
                (
                    "amount_rial",
                    models.PositiveBigIntegerField(
                        verbose_name="مبلغ بازگشت وجه (ریال)"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "در انتظار پردازش بازگشت وجه"),
                            ("succeeded", "بازگشت وجه انجام شد"),
                            ("failed", "خطا در بازگشت وجه"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="وضعیت استرداد",
                    ),
                ),
                (
                    "reason",
                    models.CharField(max_length=255, verbose_name="علت بازگشت وجه"),
                ),
                (
                    "provider_refund_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=128,
                        null=True,
                        verbose_name="شناسه پیگیری استرداد درگاه/بانک",
                    ),
                ),
                (
                    "processed_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="زمان انجام بازگشت وجه",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="refunds",
                        to="orders.order",
                        verbose_name="سفارش مرتبط",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="refunds",
                        to="payments.paymenttransaction",
                        verbose_name="تراکنش پرداخت مرجع",
                    ),
                ),
                (
                    "processed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="processed_refunds",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="ثبت‌کننده استرداد",
                    ),
                ),
            ],
            options={
                "verbose_name": "بازگشت وجه (استرداد)",
                "verbose_name_plural": "بازگشت‌های وجه (استردادها)",
                "ordering": ["-created_at"],
                "constraints": [
                    models.CheckConstraint(
                        condition=Q(amount_rial__gt=0),
                        name="payment_refund_amount_rial_positive",
                    )
                ],
            },
        ),
    ]