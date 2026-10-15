"""Initial schema migration for catalog, packaging, harvest batches, and lab certificates."""
from decimal import Decimal
import uuid
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F, Q
import apps.catalog.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="HarvestBatch",
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
                    "batch_code",
                    models.CharField(
                        db_index=True,
                        max_length=50,
                        unique=True,
                        verbose_name="کد رهگیری بچ تولید",
                    ),
                ),
                (
                    "saffron_grade",
                    models.CharField(
                        choices=[
                            ("super_negin", "سوپر نگین"),
                            ("negin", "نگین"),
                            ("sargol", "سرگل"),
                            ("pushal", "پوشال"),
                            ("dokhtar_pich", "دخترپیچ"),
                        ],
                        db_index=True,
                        max_length=20,
                        verbose_name="نوع زعفران",
                    ),
                ),
                (
                    "origin_region",
                    models.CharField(max_length=120, verbose_name="منطقه کشت"),
                ),
                (
                    "farm_or_supplier_code",
                    models.CharField(
                        blank=True,
                        max_length=80,
                        verbose_name="کد مزرعه / تأمین‌کننده",
                    ),
                ),
                (
                    "harvest_year",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1380),
                            django.core.validators.MaxValueValidator(1450),
                        ],
                        verbose_name="سال برداشت (شمسی)",
                    ),
                ),
                (
                    "harvest_date",
                    models.DateField(blank=True, null=True, verbose_name="تاریخ برداشت"),
                ),
                (
                    "drying_method",
                    models.CharField(
                        blank=True,
                        default="خشک‌کردن سنتی بهداشتی",
                        max_length=100,
                        verbose_name="روش فرآوری و خشک‌کردن",
                    ),
                ),
                (
                    "notes",
                    models.TextField(blank=True, verbose_name="یادداشت‌های کنترلی بچ"),
                ),
                (
                    "is_active",
                    models.BooleanField(db_index=True, default=True, verbose_name="فعال"),
                ),
            ],
            options={
                "verbose_name": "سری تولید و برداشت (بچ)",
                "verbose_name_plural": "سری‌های تولید و برداشت (بچ‌ها)",
                "ordering": ["-harvest_year", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PackagingType",
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
                    "name",
                    models.CharField(
                        max_length=100,
                        unique=True,
                        verbose_name="نام بسته‌بندی",
                    ),
                ),
                (
                    "slug",
                    models.SlugField(
                        allow_unicode=True,
                        max_length=120,
                        unique=True,
                        verbose_name="نامک (Slug)",
                    ),
                ),
                (
                    "material",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="جنس بسته‌بندی",
                    ),
                ),
                (
                    "tare_weight_grams",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=7,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                        verbose_name="وزن ظرف خالی (گرم)",
                    ),
                ),
                (
                    "is_gift_suitable",
                    models.BooleanField(default=False, verbose_name="مناسب هدیه و سوغات"),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="توضیحات بسته‌بندی"),
                ),
                (
                    "is_active",
                    models.BooleanField(db_index=True, default=True, verbose_name="فعال"),
                ),
            ],
            options={
                "verbose_name": "نوع بسته‌بندی",
                "verbose_name_plural": "انواع بسته‌بندی",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Product",
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
                ("name", models.CharField(max_length=180, verbose_name="نام محصول")),
                (
                    "slug",
                    models.SlugField(
                        allow_unicode=True,
                        db_index=True,
                        max_length=200,
                        unique=True,
                        verbose_name="نامک (Slug)",
                    ),
                ),
                (
                    "saffron_grade",
                    models.CharField(
                        choices=[
                            ("super_negin", "سوپر نگین"),
                            ("negin", "نگین"),
                            ("sargol", "سرگل"),
                            ("pushal", "پوشال"),
                            ("dokhtar_pich", "دخترپیچ"),
                        ],
                        db_index=True,
                        max_length=20,
                        verbose_name="نوع زعفران",
                    ),
                ),
                (
                    "short_description",
                    models.CharField(max_length=350, verbose_name="توضیح کوتاه"),
                ),
                (
                    "description",
                    models.TextField(verbose_name="توضیحات کامل و تخصصی محصول"),
                ),
                (
                    "origin_summary",
                    models.CharField(
                        default="خراسان - قائنات",
                        max_length=120,
                        verbose_name="خلاصه منطقه کشت",
                    ),
                ),
                (
                    "is_wholesale_available",
                    models.BooleanField(default=False, verbose_name="امکان فروش عمده"),
                ),
                (
                    "is_featured",
                    models.BooleanField(
                        db_index=True, default=False, verbose_name="محصول ویژه"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True, default=True, verbose_name="فعال در فروشگاه"
                    ),
                ),
            ],
            options={
                "verbose_name": "محصول زعفران",
                "verbose_name_plural": "محصولات زعفران",
                "ordering": ["-is_featured", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="LabCertificate",
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
                    "lab_name",
                    models.CharField(max_length=150, verbose_name="نام آزمایشگاه مرجع"),
                ),
                (
                    "certificate_number",
                    models.CharField(
                        db_index=True,
                        max_length=100,
                        unique=True,
                        verbose_name="شماره گواهی آزمایش",
                    ),
                ),
                ("issue_date", models.DateField(verbose_name="تاریخ صدور گواهی")),
                (
                    "expiry_date",
                    models.DateField(
                        blank=True, null=True, verbose_name="تاریخ انقضای گواهی"
                    ),
                ),
                (
                    "standard_reference",
                    models.CharField(
                        default="ISO 3632-2 / ISIRI 259-2",
                        max_length=120,
                        verbose_name="استاندارد مرجع",
                    ),
                ),
                (
                    "quality_grade_result",
                    models.CharField(
                        default="درجه یک ممتاز (Grade I)",
                        max_length=80,
                        verbose_name="نتیجه درجه‌بندی کیفی",
                    ),
                ),
                (
                    "document_file",
                    models.FileField(
                        upload_to=apps.catalog.validators.safe_certificate_upload_path,
                        validators=[apps.catalog.validators.validate_certificate_file],
                        verbose_name="فایل گواهی اصالت (PDF یا تصویر)",
                    ),
                ),
                (
                    "is_verified",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        verbose_name="تأییدشده جهت نمایش عمومی",
                    ),
                ),
                (
                    "harvest_batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="certificates",
                        to="catalog.harvestbatch",
                        verbose_name="بچ تولید مربوطه",
                    ),
                ),
            ],
            options={
                "verbose_name": "گواهی آزمایشگاهی و اصالت",
                "verbose_name_plural": "گواهی‌های آزمایشگاهی و اصالت",
                "ordering": ["-issue_date"],
            },
        ),
        migrations.CreateModel(
            name="ProductVariant",
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
                    "sku",
                    models.CharField(
                        db_index=True,
                        max_length=64,
                        unique=True,
                        verbose_name="کد محصول (SKU)",
                    ),
                ),
                (
                    "net_weight_grams",
                    models.DecimalField(
                        decimal_places=3,
                        help_text="برای یک مثقال مقدار 4.608 وارد شود.",
                        max_digits=8,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.001"))
                        ],
                        verbose_name="وزن خالص زعفران (گرم)",
                    ),
                ),
                (
                    "weight_label",
                    models.CharField(
                        help_text="مثال: ۱ مثقال (۴.۶۰۸ گرم) یا ۵ گرم",
                        max_length=60,
                        verbose_name="عنوان نمایشی وزن",
                    ),
                ),
                (
                    "sale_type",
                    models.CharField(
                        choices=[("retail", "فروش خرده"), ("wholesale", "فروش عمده")],
                        db_index=True,
                        default="retail",
                        max_length=20,
                        verbose_name="نوع عرضه",
                    ),
                ),
                (
                    "min_order_quantity",
                    models.PositiveIntegerField(
                        default=1,
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="حداقل تعداد سفارش",
                    ),
                ),
                (
                    "max_order_quantity",
                    models.PositiveIntegerField(
                        default=50,
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="حداکثر تعداد در هر سفارش",
                    ),
                ),
                (
                    "base_price_rial",
                    models.PositiveBigIntegerField(
                        help_text="مبلغ به ریال و مضرب ۱۰ وارد شود (مثال: 1250000 برای ۱۲۵,۰۰۰ تومان).",
                        verbose_name="قیمت پایه (ریال)",
                    ),
                ),
                (
                    "discounted_price_rial",
                    models.PositiveBigIntegerField(
                        blank=True,
                        help_text="اختیاری. باید به ریال، مضرب ۱۰ و کمتر از قیمت پایه باشد.",
                        null=True,
                        verbose_name="قیمت پس از تخفیف (ریال)",
                    ),
                ),
                (
                    "stock_quantity",
                    models.PositiveIntegerField(
                        default=0, verbose_name="موجودی قابل فروش"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(db_index=True, default=True, verbose_name="فعال"),
                ),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(
                        default=0, verbose_name="ترتیب نمایش"
                    ),
                ),
                (
                    "harvest_batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="variants",
                        to="catalog.harvestbatch",
                        verbose_name="بچ تولید و برداشت",
                    ),
                ),
                (
                    "packaging_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="variants",
                        to="catalog.packagingtype",
                        verbose_name="نوع بسته‌بندی",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="variants",
                        to="catalog.product",
                        verbose_name="محصول پایه",
                    ),
                ),
            ],
            options={
                "verbose_name": "گونه محصول (وزن و بسته‌بندی)",
                "verbose_name_plural": "گونه‌های محصول (وزن و بسته‌بندی)",
                "ordering": ["sort_order", "net_weight_grams", "id"],
            },
        ),
        migrations.CreateModel(
            name="ProductImage",
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
                    "image",
                    models.ImageField(
                        upload_to=apps.catalog.validators.safe_product_image_upload_path,
                        validators=[apps.catalog.validators.validate_product_image],
                        verbose_name="فایل تصویر",
                    ),
                ),
                (
                    "alt_text",
                    models.CharField(
                        max_length=180, verbose_name="متن جایگزین (Alt Text)"
                    ),
                ),
                (
                    "is_primary",
                    models.BooleanField(
                        db_index=True, default=False, verbose_name="تصویر اصلی محصول"
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(
                        default=0, verbose_name="ترتیب نمایش"
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="catalog.product",
                        verbose_name="محصول",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="images",
                        to="catalog.productvariant",
                        verbose_name="گونه مرتبط (اختیاری)",
                    ),
                ),
            ],
            options={
                "verbose_name": "تصویر محصول",
                "verbose_name_plural": "تصاویر محصولات",
                "ordering": ["-is_primary", "sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="LabTestMetric",
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
                    "metric_type",
                    models.CharField(
                        choices=[
                            ("crocin", "کروسین (قدرت رنگ‌دهی)"),
                            ("picrocrocin", "پیکروکروسین (طعم و تلخی)"),
                            ("safranal", "سافرانال (عطر)"),
                            ("moisture", "رطوبت و مواد فرار"),
                            ("total_ash", "خاکستر کل"),
                            ("foreign_matter", "مواد خارجی"),
                            ("other", "سایر شاخص‌ها"),
                        ],
                        max_length=30,
                        verbose_name="نوع شاخص",
                    ),
                ),
                (
                    "metric_title",
                    models.CharField(max_length=120, verbose_name="عنوان شاخص"),
                ),
                (
                    "value",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=8,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                        verbose_name="مقدار اندازه‌گیری‌شده",
                    ),
                ),
                (
                    "unit",
                    models.CharField(
                        default="A1% 1cm",
                        max_length=50,
                        verbose_name="واحد اندازه‌گیری",
                    ),
                ),
                (
                    "min_standard_limit",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                        verbose_name="حداقل مجاز استاندارد",
                    ),
                ),
                (
                    "max_standard_limit",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                        verbose_name="حداکثر مجاز استاندارد",
                    ),
                ),
                ("test_date", models.DateField(verbose_name="تاریخ انجام آزمون")),
                (
                    "reference_method",
                    models.CharField(
                        default="ISO 3632-2",
                        max_length=100,
                        verbose_name="مرجع روش آزمون",
                    ),
                ),
                (
                    "certificate",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="metrics",
                        to="catalog.labcertificate",
                        verbose_name="گواهی آزمایشگاه",
                    ),
                ),
            ],
            options={
                "verbose_name": "شاخص نتیجه آزمایش",
                "verbose_name_plural": "شاخص‌های نتایج آزمایش",
                "ordering": ["metric_type", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("certificate", "metric_type", "metric_title"),
                        name="unique_metric_per_certificate",
                    )
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.CheckConstraint(
                condition=Q(base_price_rial__gt=0),
                name="variant_base_price_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.CheckConstraint(
                condition=Q(discounted_price_rial__isnull=True)
                | (
                    Q(discounted_price_rial__gt=0)
                    & Q(discounted_price_rial__lt=F("base_price_rial"))
                ),
                name="variant_discounted_price_lt_base_price",
            ),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.CheckConstraint(
                condition=Q(min_order_quantity__gte=1)
                & Q(max_order_quantity__gte=F("min_order_quantity")),
                name="variant_valid_order_quantity_bounds",
            ),
        ),
    ]