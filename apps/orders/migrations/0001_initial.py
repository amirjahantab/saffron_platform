"""Initial schema migration for Cart and CartItem models (Sub-phase 4.1)."""
import uuid
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Cart",
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
                    "session_key",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=64,
                        null=True,
                        verbose_name="کلید نشست مهمان",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "فعال"),
                            ("merged", "ادغام‌شده با حساب کاربری"),
                            ("converted", "تبدیل‌شده به سفارش"),
                            ("abandoned", "رهاشده"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=20,
                        verbose_name="وضعیت سبد",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="carts",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="کاربر",
                    ),
                ),
            ],
            options={
                "verbose_name": "سبد خرید",
                "verbose_name_plural": "سبدهای خرید",
                "ordering": ["-updated_at"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=Q(status="active", user__isnull=False),
                        fields=("user",),
                        name="unique_active_cart_per_user",
                    ),
                    models.UniqueConstraint(
                        condition=Q(
                            session_key__isnull=False,
                            status="active",
                            user__isnull=True,
                        ),
                        fields=("session_key",),
                        name="unique_active_cart_per_guest_session",
                    ),
                    models.CheckConstraint(
                        condition=Q(user__isnull=False) | Q(session_key__isnull=False),
                        name="cart_requires_user_or_session_key",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="CartItem",
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
                        default=1,
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="تعداد",
                    ),
                ),
                (
                    "cart",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="orders.cart",
                        verbose_name="سبد خرید",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cart_items",
                        to="catalog.productvariant",
                        verbose_name="گونه محصول",
                    ),
                ),
            ],
            options={
                "verbose_name": "آیتم سبد خرید",
                "verbose_name_plural": "آیتم‌های سبد خرید",
                "ordering": ["created_at", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("cart", "variant"),
                        name="unique_variant_per_cart",
                    ),
                    models.CheckConstraint(
                        condition=Q(quantity__gte=1),
                        name="cart_item_quantity_positive",
                    ),
                ],
            },
        ),
    ]