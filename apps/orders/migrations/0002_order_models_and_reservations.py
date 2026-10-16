"""Migration for ShippingAddress, Order, OrderItem, and StockReservation models (Sub-phase 4.2)."""
from decimal import Decimal
import uuid
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q
import apps.accounts.validators
import apps.orders.models
import apps.orders.validators


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0001_initial"),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShippingAddress",
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
                    "recipient_full_name",
                    models.CharField(
                        max_length=150,
                        verbose_name="نام و نام خانوادگی گیرنده",
                    ),
                ),
                (
                    "recipient_phone",
                    models.CharField(
                        max_length=11,
                        validators=[apps.accounts.validators.validate_iranian_phone],
                        verbose_name="شماره موبایل گیرنده",
                    ),
                ),
                ("province", models.CharField(max_length=80, verbose_name="استان")),
                ("city", models.CharField(max_length=80, verbose_name="شهر")),
                (
                    "address_line",
                    models.TextField(max_length=500, verbose_name="نشانی کامل پستی"),
                ),
                (
                    "postal_code",
                    models.CharField(
                        max_length=10,
                        validators=[
                            apps.orders.validators.validate_iranian_postal_code
                        ],
                        verbose_name="کد پستی ۱۰ رقمی",
                    ),
                ),
                (
                    "is_default",
                    models.BooleanField(
                        db_index=True, default=False, verbose_name="آدرس پیش‌فرض"
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shipping_addresses",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="کاربر",
                    ),
                ),
            ],
            options={
                "verbose_name": "آدرس ارسال",
                "verbose_name_plural": "آدرس‌های ارسال",
                "ordering": ["-is_default", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Order",
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
                    "order_number",
                    models.CharField(
                        db_index=True,
                        default=apps.orders.models.generate_unique_order_number,
                        editable=False,
                        max_length=32,
                        unique=True,
                        verbose_name="شماره سفارش",
                    ),
                ),
                (
                    "idempotency_key",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=64,
                        null=True,
                        verbose_name="کلید یکتای جلوگیری از تکرار (Idempotency Key)",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_payment", "در انتظار پرداخت"),
                            ("paid", "پرداخت‌شده"),
                            ("processing", "در حال آماده‌سازی و بسته‌بندی"),
                            ("shipped", "تحویل‌شده به پست / ارسال‌شده"),
                            ("delivered", "تحویل‌شده به مشتری"),
                            ("cancelled", "لغوشده"),
                            ("expired", "منقضی‌شده (عدم پرداخت در مهلت رزرو)"),
                            ("refunded", "مستردشده (بازگشت وجه)"),
                        ],
                        db_index=True,
                        default="pending_payment",
                        max_length=25,
                        verbose_name="وضعیت سفارش",
                    ),
                ),
                (
                    "recipient_full_name",
                    models.CharField(
                        max_length=150,
                        verbose_name="نام و نام خانوادگی گیرنده",
                    ),
                ),
                (
                    "recipient_phone",
                    models.CharField(
                        max_length=11,
                        validators=[apps.accounts.validators.validate_iranian_phone],
                        verbose_name="شماره موبایل گیرنده",
                    ),
                ),
                ("province", models.CharField(max_length=80, verbose_name="استان")),
                ("city", models.CharField(max_length=80, verbose_name="شهر")),
                (
                    "address_line",
                    models.TextField(max_length=500, verbose_name="نشانی کامل پستی"),
                ),
                (
                    "postal_code",
                    models.CharField(
                        max_length=10,
                        validators=[
                            apps.orders.validators.validate_iranian_postal_code
                        ],
                        verbose_name="کد پستی ۱۰ رقمی",
                    ),
                ),
                (
                    "shipping_method",
                    models.CharField(
                        choices=[
                            ("post_pishtaz", "پست پیشتاز"),
                            ("tipax", "تیپاکس"),
                            ("courier_mashhad", "پیک ویژه مشهد"),
                            ("freight_wholesale", "باربری (ویژه سفارش عمده)"),
                        ],
                        default="post_pishtaz",
                        max_length=30,
                        verbose_name="روش ارسال",
                    ),
                ),
                (
                    "tracking_code",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=64,
                        verbose_name="کد رهگیری مرسوله پستی",
                    ),
                ),
                (
                    "total_gross_weight_grams",
                    models.DecimalField(
                        decimal_places=3,
                        default=Decimal("0.000"),
                        max_digits=10,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.001"))
                        ],
                        verbose_name="وزن ناخالص کل مرسوله (گرم)",
                    ),
                ),
                (
                    "customer_note",
                    models.TextField(
                        blank=True, max_length=500, verbose_name="توضیحات مشتری"
                    ),
                ),
                (
                    "cancel_reason",
                    models.CharField(
                        blank=True, max_length=250, verbose_name="علت لغو یا انقضا"
                    ),
                ),
                (
                    "subtotal_base_rial",
                    models.PositiveBigIntegerField(
                        verbose_name="جمع کل قیمت پایه اقلام (ریال)"
                    ),
                ),
                (
                    "total_discount_rial",
                    models.PositiveBigIntegerField(
                        default=0, verbose_name="مجموع تخفیف اقلام (ریال)"
                    ),
                ),
                (
                    "shipping_cost_rial",
                    models.PositiveBigIntegerField(
                        default=0, verbose_name="هزینه ارسال (ریال)"
                    ),
                ),
                (
                    "payable_rial",
                    models.PositiveBigIntegerField(
                        verbose_name="مبلغ نهایی قابل پرداخت (ریال)"
                    ),
                ),
                (
                    "reservation_expires_at",
                    models.DateTimeField(
                        db_index=True,
                        verbose_name="مهلت انقضای رزرو موجودی و پرداخت",
                    ),
                ),
                (
                    "paid_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="زمان پرداخت"
                    ),
                ),
                (
                    "shipped_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="زمان ارسال"
                    ),
                ),
                (
                    "delivered_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="زمان تحویل"
                    ),
                ),
                (
                    "cancelled_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="زمان لغو یا انقضا"
                    ),
                ),
                (
                    "source_cart",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="orders",
                        to="orders.cart",
                        verbose_name="سبد خرید منشأ",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="orders",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="مشتری",
                    ),
                ),
            ],
            options={
                "verbose_name": "سفارش",
                "verbose_name_plural": "سفارش‌ها",
                "ordering": ["-created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=Q(idempotency_key__isnull=False),
                        fields=("user", "idempotency_key"),
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
                            payable_rial=(
                                F("subtotal_base_rial") - F("total_discount_rial")
                            )
                            + F("shipping_cost_rial")
                        ),
                        name="order_payable_equals_subtotal_minus_discount_plus_shipping",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="OrderItem",
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
                    "product_name_snapshot",
                    models.CharField(
                        max_length=180,
                        verbose_name="نام محصول (در لحظه خرید)",
                    ),
                ),
                (
                    "sku_snapshot",
                    models.CharField(
                        max_length=64,
                        verbose_name="کد SKU (در لحظه خرید)",
                    ),
                ),
                (
                    "saffron_grade_snapshot",
                    models.CharField(
                        choices=[
                            ("super_negin", "سوپر نگین"),
                            ("negin", "نگین"),
                            ("sargol", "سرگل"),
                            ("pushal", "پوشال"),
                            ("dokhtar_pich", "دخترپیچ"),
                        ],
                        max_length=20,
                        verbose_name="نوع زعفران (در لحظه خرید)",
                    ),
                ),
                (
                    "packaging_name_snapshot",
                    models.CharField(
                        max_length=100,
                        verbose_name="نوع بسته‌بندی (در لحظه خرید)",
                    ),
                ),
                (
                    "weight_label_snapshot",
                    models.CharField(
                        max_length=60,
                        verbose_name="عنوان وزن (در لحظه خرید)",
                    ),
                ),
                (
                    "net_weight_grams_snapshot",
                    models.DecimalField(
                        decimal_places=3,
                        max_digits=8,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.001"))
                        ],
                        verbose_name="وزن خالص واحد (گرم)",
                    ),
                ),
                (
                    "batch_code_snapshot",
                    models.CharField(
                        max_length=50,
                        verbose_name="کد رهگیری بچ تولید (در لحظه خرید)",
                    ),
                ),
                (
                    "origin_region_snapshot",
                    models.CharField(
                        max_length=120,
                        verbose_name="منطقه کشت (در لحظه خرید)",
                    ),
                ),
                (
                    "harvest_year_snapshot",
                    models.PositiveSmallIntegerField(
                        verbose_name="سال برداشت (در لحظه خرید)"
                    ),
                ),
                (
                    "quantity",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="تعداد",
                    ),
                ),
                (
                    "unit_base_price_rial",
                    models.PositiveBigIntegerField(
                        verbose_name="قیمت پایه واحد (ریال)"
                    ),
                ),
                (
                    "unit_effective_price_rial",
                    models.PositiveBigIntegerField(
                        verbose_name="قیمت نهایی واحد پس از تخفیف (ریال)"
                    ),
                ),
                (
                    "line_base_total_rial",
                    models.PositiveBigIntegerField(
                        verbose_name="جمع قیمت پایه ردیف (ریال)"
                    ),
                ),
                (
                    "line_discount_total_rial",
                    models.PositiveBigIntegerField(
                        default=0, verbose_name="جمع تخفیف ردیف (ریال)"
                    ),
                ),
                (
                    "line_effective_total_rial",
                    models.PositiveBigIntegerField(
                        verbose_name="مبلغ نهایی ردیف (ریال)"
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="orders.order",
                        verbose_name="سفارش",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="order_items",
                        to="catalog.productvariant",
                        verbose_name="گونه محصول مرجع",
                    ),
                ),
            ],
            options={
                "verbose_name": "قلم سفارش",
                "verbose_name_plural": "اقلام سفارش",
                "ordering": ["id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("order", "variant"),
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
                ],
            },
        ),
        migrations.CreateModel(
            name="StockReservation",
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
                    "quantity",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="تعداد رزروشده",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "رزرو فعال (در انتظار پرداخت)"),
                            ("committed", "قطعی‌شده (پرداخت موفق)"),
                            ("released", "آزادشده (لغو سفارش یا خطای پرداخت)"),
                            ("expired", "منقضی و آزادشده (پایان مهلت پرداخت)"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=20,
                        verbose_name="وضعیت رزرو",
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        db_index=True,
                        verbose_name="زمان انقضای رزرو",
                    ),
                ),
                (
                    "committed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="زمان قطعی‌شدن رزرو"
                    ),
                ),
                (
                    "released_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="زمان آزادسازی موجودی"
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservations",
                        to="orders.order",
                        verbose_name="سفارش",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_reservations",
                        to="catalog.productvariant",
                        verbose_name="گونه محصول",
                    ),
                ),
            ],
            options={
                "verbose_name": "رزرو موجودی انبار",
                "verbose_name_plural": "رزروهای موجودی انبار",
                "ordering": ["-created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("order", "variant"),
                        name="unique_reservation_per_order_variant",
                    ),
                    models.CheckConstraint(
                        condition=Q(quantity__gte=1),
                        name="stock_reservation_quantity_positive",
                    ),
                ],
            },
        ),
    ]