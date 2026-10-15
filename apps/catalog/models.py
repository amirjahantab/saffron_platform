"""
Domain models for the Saffron E-commerce Catalog & Laboratory Authenticity Subsystem.

Includes:
- SaffronGrade (TextChoices: Super Negin, Negin, Sargol, Pushal, Dokhtar Pich)
- PackagingType (Manageable containers with tare weight for shipping calculations)
- HarvestBatch (Origin region, harvest year, batch tracking code)
- LabCertificate & LabTestMetric (ISO 3632 / ISIRI 259 laboratory results and secure documents)
- Product, ProductVariant & ProductImage (SKUs, weights, Rial/Toman pricing, and inventory)
"""
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from apps.catalog.validators import (
    safe_certificate_upload_path,
    safe_product_image_upload_path,
    validate_certificate_file,
    validate_product_image,
)
from apps.core.currency import (
    RIAL_TO_TOMAN_FACTOR,
    format_price_toman,
    rial_to_toman,
    validate_rial_amount,
)
from apps.core.exceptions import MonetaryPrecisionError
from apps.core.models import TimeStampedModel, UUIDModel


class SaffronGrade(models.TextChoices):
    """Supported saffron grades as specified in the business domain contract."""

    SUPER_NEGIN = "super_negin", _("سوپر نگین")
    NEGIN = "negin", _("نگین")
    SARGOL = "sargol", _("سرگل")
    PUSHAL = "pushal", _("پوشال")
    DOKHTAR_PICH = "dokhtar_pich", _("دخترپیچ")


class SaleChannelType(models.TextChoices):
    """Retail vs. Wholesale sale channel classification for variants."""

    RETAIL = "retail", _("فروش خرده")
    WHOLESALE = "wholesale", _("فروش عمده")


class PackagingType(TimeStampedModel, UUIDModel):
    """
    Represents a physical packaging option (e.g., Khatam metal tin, Crystal box, Velvet gift box, Bulk pack).
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("نام بسته‌بندی"),
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        allow_unicode=True,
        verbose_name=_("نامک (Slug)"),
    )
    material = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("جنس بسته‌بندی"),
    )
    tare_weight_grams = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("وزن ظرف خالی (گرم)"),
    )
    is_gift_suitable = models.BooleanField(
        default=False,
        verbose_name=_("مناسب هدیه و سوغات"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("توضیحات بسته‌بندی"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("فعال"),
    )

    class Meta:
        verbose_name = _("نوع بسته‌بندی")
        verbose_name_plural = _("انواع بسته‌بندی")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class HarvestBatch(TimeStampedModel, UUIDModel):
    """
    Tracks a specific saffron harvest batch, cultivation origin, and harvest year.
    Provides full traceability from farm/region to laboratory certificate and customer package.
    """

    batch_code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_("کد رهگیری بچ تولید"),
    )
    saffron_grade = models.CharField(
        max_length=20,
        choices=SaffronGrade.choices,
        db_index=True,
        verbose_name=_("نوع زعفران"),
    )
    origin_region = models.CharField(
        max_length=120,
        verbose_name=_("منطقه کشت"),
    )
    farm_or_supplier_code = models.CharField(
        max_length=80,
        blank=True,
        verbose_name=_("کد مزرعه / تأمین‌کننده"),
    )
    harvest_year = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1380), MaxValueValidator(1450)],
        verbose_name=_("سال برداشت (شمسی)"),
    )
    harvest_date = models.DateField(
        blank=True,
        null=True,
        verbose_name=_("تاریخ برداشت"),
    )
    drying_method = models.CharField(
        max_length=100,
        blank=True,
        default="خشک‌کردن سنتی بهداشتی",
        verbose_name=_("روش فرآوری و خشک‌کردن"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_("یادداشت‌های کنترلی بچ"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("فعال"),
    )

    class Meta:
        verbose_name = _("سری تولید و برداشت (بچ)")
        verbose_name_plural = _("سری‌های تولید و برداشت (بچ‌ها)")
        ordering = ["-harvest_year", "-created_at"]

    def __str__(self) -> str:
        return f"{self.batch_code} - {self.get_saffron_grade_display()} ({self.origin_region} - {self.harvest_year})"

    def clean(self) -> None:
        super().clean()
        if self.batch_code:
            self.batch_code = self.batch_code.strip().upper()


class LabCertificate(TimeStampedModel, UUIDModel):
    """
    Official laboratory analysis certificate and authenticity document attached to a HarvestBatch.
    """

    harvest_batch = models.ForeignKey(
        HarvestBatch,
        on_delete=models.PROTECT,
        related_name="certificates",
        verbose_name=_("بچ تولید مربوطه"),
    )
    lab_name = models.CharField(
        max_length=150,
        verbose_name=_("نام آزمایشگاه مرجع"),
    )
    certificate_number = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name=_("شماره گواهی آزمایش"),
    )
    issue_date = models.DateField(
        verbose_name=_("تاریخ صدور گواهی"),
    )
    expiry_date = models.DateField(
        blank=True,
        null=True,
        verbose_name=_("تاریخ انقضای گواهی"),
    )
    standard_reference = models.CharField(
        max_length=120,
        default="ISO 3632-2 / ISIRI 259-2",
        verbose_name=_("استاندارد مرجع"),
    )
    quality_grade_result = models.CharField(
        max_length=80,
        default="درجه یک ممتاز (Grade I)",
        verbose_name=_("نتیجه درجه‌بندی کیفی"),
    )
    document_file = models.FileField(
        upload_to=safe_certificate_upload_path,
        validators=[validate_certificate_file],
        verbose_name=_("فایل گواهی اصالت (PDF یا تصویر)"),
    )
    is_verified = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("تأییدشده جهت نمایش عمومی"),
    )

    class Meta:
        verbose_name = _("گواهی آزمایشگاهی و اصالت")
        verbose_name_plural = _("گواهی‌های آزمایشگاهی و اصالت")
        ordering = ["-issue_date"]

    def __str__(self) -> str:
        return f"گواهی {self.certificate_number} ({self.lab_name}) - بچ {self.harvest_batch.batch_code}"

    def clean(self) -> None:
        super().clean()
        if self.certificate_number:
            self.certificate_number = self.certificate_number.strip().upper()
        if self.issue_date and self.expiry_date and self.expiry_date <= self.issue_date:
            raise ValidationError(
                {"expiry_date": _("تاریخ انقضای گواهی باید بعد از تاریخ صدور آن باشد.")}
            )


class LabTestMetric(TimeStampedModel, UUIDModel):
    """
    Quantitative laboratory metric (e.g., Crocin, Picrocrocin, Safranal, Moisture)
    with measured value, unit, test date, and standard reference range.
    """

    class MetricType(models.TextChoices):
        CROCIN = "crocin", _("کروسین (قدرت رنگ‌دهی)")
        PICROCROCIN = "picrocrocin", _("پیکروکروسین (طعم و تلخی)")
        SAFRANAL = "safranal", _("سافرانال (عطر)")
        MOISTURE = "moisture", _("رطوبت و مواد فرار")
        TOTAL_ASH = "total_ash", _("خاکستر کل")
        FOREIGN_MATTER = "foreign_matter", _("مواد خارجی")
        OTHER = "other", _("سایر شاخص‌ها")

    certificate = models.ForeignKey(
        LabCertificate,
        on_delete=models.CASCADE,
        related_name="metrics",
        verbose_name=_("گواهی آزمایشگاه"),
    )
    metric_type = models.CharField(
        max_length=30,
        choices=MetricType.choices,
        verbose_name=_("نوع شاخص"),
    )
    metric_title = models.CharField(
        max_length=120,
        verbose_name=_("عنوان شاخص"),
    )
    value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("مقدار اندازه‌گیری‌شده"),
    )
    unit = models.CharField(
        max_length=50,
        default="A1% 1cm",
        verbose_name=_("واحد اندازه‌گیری"),
    )
    min_standard_limit = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("حداقل مجاز استاندارد"),
    )
    max_standard_limit = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("حداکثر مجاز استاندارد"),
    )
    test_date = models.DateField(
        verbose_name=_("تاریخ انجام آزمون"),
    )
    reference_method = models.CharField(
        max_length=100,
        default="ISO 3632-2",
        verbose_name=_("مرجع روش آزمون"),
    )

    class Meta:
        verbose_name = _("شاخص نتیجه آزمایش")
        verbose_name_plural = _("شاخص‌های نتایج آزمایش")
        ordering = ["metric_type", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["certificate", "metric_type", "metric_title"],
                name="unique_metric_per_certificate",
            )
        ]

    def __str__(self) -> str:
        return f"{self.metric_title}: {self.value} {self.unit}"

    def clean(self) -> None:
        super().clean()
        if (
            self.min_standard_limit is not None
            and self.max_standard_limit is not None
            and self.min_standard_limit > self.max_standard_limit
        ):
            raise ValidationError(
                _("حداقل مجاز استاندارد نمی‌تواند بزرگ‌تر از حداکثر مجاز استاندارد باشد.")
            )


class Product(TimeStampedModel, UUIDModel):
    """
    Core Saffron Product entity representing a saffron grade/line in the store catalog.
    Actual purchasable weights, packages, prices, and SKUs are modeled via `ProductVariant`.
    """

    name = models.CharField(
        max_length=180,
        verbose_name=_("نام محصول"),
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        allow_unicode=True,
        db_index=True,
        verbose_name=_("نامک (Slug)"),
    )
    saffron_grade = models.CharField(
        max_length=20,
        choices=SaffronGrade.choices,
        db_index=True,
        verbose_name=_("نوع زعفران"),
    )
    short_description = models.CharField(
        max_length=350,
        verbose_name=_("توضیح کوتاه"),
    )
    description = models.TextField(
        verbose_name=_("توضیحات کامل و تخصصی محصول"),
    )
    origin_summary = models.CharField(
        max_length=120,
        default="خراسان - قائنات",
        verbose_name=_("خلاصه منطقه کشت"),
    )
    is_wholesale_available = models.BooleanField(
        default=False,
        verbose_name=_("امکان فروش عمده"),
    )
    is_featured = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("محصول ویژه"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("فعال در فروشگاه"),
    )

    class Meta:
        verbose_name = _("محصول زعفران")
        verbose_name_plural = _("محصولات زعفران")
        ordering = ["-is_featured", "-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_saffron_grade_display()})"


class ProductVariant(TimeStampedModel, UUIDModel):
    """
    Purchasable product SKU combining Product, PackagingType, HarvestBatch, Weight,
    strict integer Rial pricing, and independent stock quantity.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("محصول پایه"),
    )
    packaging_type = models.ForeignKey(
        PackagingType,
        on_delete=models.PROTECT,
        related_name="variants",
        verbose_name=_("نوع بسته‌بندی"),
    )
    harvest_batch = models.ForeignKey(
        HarvestBatch,
        on_delete=models.PROTECT,
        related_name="variants",
        verbose_name=_("بچ تولید و برداشت"),
    )
    sku = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name=_("کد محصول (SKU)"),
    )
    net_weight_grams = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        verbose_name=_("وزن خالص زعفران (گرم)"),
        help_text=_("برای یک مثقال مقدار 4.608 وارد شود."),
    )
    weight_label = models.CharField(
        max_length=60,
        verbose_name=_("عنوان نمایشی وزن"),
        help_text=_("مثال: ۱ مثقال (۴.۶۰۸ گرم) یا ۵ گرم"),
    )
    sale_type = models.CharField(
        max_length=20,
        choices=SaleChannelType.choices,
        default=SaleChannelType.RETAIL,
        db_index=True,
        verbose_name=_("نوع عرضه"),
    )
    min_order_quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("حداقل تعداد سفارش"),
    )
    max_order_quantity = models.PositiveIntegerField(
        default=50,
        validators=[MinValueValidator(1)],
        verbose_name=_("حداکثر تعداد در هر سفارش"),
    )
    base_price_rial = models.PositiveBigIntegerField(
        verbose_name=_("قیمت پایه (ریال)"),
        help_text=_("مبلغ به ریال و مضرب ۱۰ وارد شود (مثال: 1250000 برای ۱۲۵,۰۰۰ تومان)."),
    )
    discounted_price_rial = models.PositiveBigIntegerField(
        blank=True,
        null=True,
        verbose_name=_("قیمت پس از تخفیف (ریال)"),
        help_text=_("اختیاری. باید به ریال، مضرب ۱۰ و کمتر از قیمت پایه باشد."),
    )
    stock_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name=_("موجودی قابل فروش"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("فعال"),
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("ترتیب نمایش"),
    )

    class Meta:
        verbose_name = _("گونه محصول (وزن و بسته‌بندی)")
        verbose_name_plural = _("گونه‌های محصول (وزن و بسته‌بندی)")
        ordering = ["sort_order", "net_weight_grams", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(base_price_rial__gt=0),
                name="variant_base_price_positive",
            ),
            models.CheckConstraint(
                condition=Q(discounted_price_rial__isnull=True)
                | (Q(discounted_price_rial__gt=0) & Q(discounted_price_rial__lt=F("base_price_rial"))),
                name="variant_discounted_price_lt_base_price",
            ),
            models.CheckConstraint(
                condition=Q(min_order_quantity__gte=1) & Q(max_order_quantity__gte=F("min_order_quantity")),
                name="variant_valid_order_quantity_bounds",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} - {self.weight_label} ({self.packaging_type.name}) [{self.sku}]"

    @property
    def has_discount(self) -> bool:
        return bool(
            self.discounted_price_rial is not None
            and self.discounted_price_rial < self.base_price_rial
        )

    @property
    def effective_price_rial(self) -> int:
        if self.has_discount and self.discounted_price_rial is not None:
            return int(self.discounted_price_rial)
        return int(self.base_price_rial)

    @property
    def base_price_toman(self) -> int:
        return rial_to_toman(int(self.base_price_rial))

    @property
    def discounted_price_toman(self) -> int | None:
        if self.discounted_price_rial is not None:
            return rial_to_toman(int(self.discounted_price_rial))
        return None

    @property
    def effective_price_toman(self) -> int:
        return rial_to_toman(self.effective_price_rial)

    @property
    def formatted_effective_price_toman(self) -> str:
        return format_price_toman(self.effective_price_rial)

    @property
    def formatted_base_price_toman(self) -> str:
        return format_price_toman(int(self.base_price_rial))

    @property
    def discount_percentage(self) -> int:
        """Calculate integer discount percentage using Decimal arithmetic (zero floats)."""
        if not self.has_discount or self.discounted_price_rial is None or self.base_price_rial <= 0:
            return 0
        base_dec = Decimal(self.base_price_rial)
        disc_dec = Decimal(self.discounted_price_rial)
        ratio = ((base_dec - disc_dec) * Decimal("100")) / base_dec
        return int(ratio.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @property
    def gross_weight_grams(self) -> Decimal:
        """Total shipping weight in grams (net saffron weight + packaging tare weight)."""
        tare = self.packaging_type.tare_weight_grams if self.packaging_type_id else Decimal("0.00")
        return (self.net_weight_grams + tare).quantize(Decimal("0.001"))

    @property
    def is_in_stock(self) -> bool:
        return (
            self.is_active
            and self.product.is_active
            and self.stock_quantity >= self.min_order_quantity
        )

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[ValidationError]] = {}

        if self.sku:
            self.sku = self.sku.strip().upper()

        if self.net_weight_grams is None or self.net_weight_grams <= Decimal("0"):
            errors.setdefault("net_weight_grams", []).append(
                ValidationError(_("وزن خالص زعفران باید بزرگ‌تر از صفر باشد."))
            )

        # Validate base_price_rial according to the Monetary Contract (IRR multiple of 10)
        if self.base_price_rial is None or self.base_price_rial <= 0:
            errors.setdefault("base_price_rial", []).append(
                ValidationError(_("قیمت پایه باید بزرگ‌تر از صفر باشد."))
            )
        else:
            try:
                validate_rial_amount(int(self.base_price_rial))
            except MonetaryPrecisionError as exc:
                errors.setdefault("base_price_rial", []).append(
                    ValidationError(
                        _("قیمت پایه باید مضرب %(factor)d ریال باشد تا به تومان قابل تبدیل دقیق باشد."),
                        params={"factor": RIAL_TO_TOMAN_FACTOR},
                    )
                )

        # Validate discounted_price_rial if provided
        if self.discounted_price_rial is not None:
            if self.discounted_price_rial <= 0:
                errors.setdefault("discounted_price_rial", []).append(
                    ValidationError(_("قیمت تخفیف‌دار باید بزرگ‌تر از صفر باشد."))
                )
            else:
                try:
                    validate_rial_amount(int(self.discounted_price_rial))
                except MonetaryPrecisionError:
                    errors.setdefault("discounted_price_rial", []).append(
                        ValidationError(
                            _("قیمت تخفیف‌دار باید مضرب %(factor)d ریال باشد."),
                            params={"factor": RIAL_TO_TOMAN_FACTOR},
                        )
                    )
                if self.base_price_rial and self.discounted_price_rial >= self.base_price_rial:
                    errors.setdefault("discounted_price_rial", []).append(
                        ValidationError(_("قیمت تخفیف‌دار باید اکیداً کمتر از قیمت پایه باشد."))
                    )

        if self.min_order_quantity < 1:
            errors.setdefault("min_order_quantity", []).append(
                ValidationError(_("حداقل تعداد سفارش باید حداقل ۱ باشد."))
            )
        if self.max_order_quantity < self.min_order_quantity:
            errors.setdefault("max_order_quantity", []).append(
                ValidationError(_("حداکثر تعداد سفارش نمی‌تواند کمتر از حداقل تعداد سفارش باشد."))
            )

        # Ensure saffron grade consistency between Product and HarvestBatch
        if self.product_id and self.harvest_batch_id:
            if self.product.saffron_grade != self.harvest_batch.saffron_grade:
                errors.setdefault("harvest_batch", []).append(
                    ValidationError(
                        _(
                            "نوع زعفران در بچ تولید (%(batch_grade)s) با نوع زعفران محصول پایه (%(product_grade)s) هم‌خوانی ندارد."
                        ),
                        params={
                            "batch_grade": self.harvest_batch.get_saffron_grade_display(),
                            "product_grade": self.product.get_saffron_grade_display(),
                        },
                    )
                )

        if errors:
            raise ValidationError(errors)


class ProductImage(TimeStampedModel, UUIDModel):
    """
    Verified product image with mandatory alt text for accessibility and SEO.
    Can be attached to the general Product or a specific ProductVariant.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("محصول"),
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="images",
        verbose_name=_("گونه مرتبط (اختیاری)"),
    )
    image = models.ImageField(
        upload_to=safe_product_image_upload_path,
        validators=[validate_product_image],
        verbose_name=_("فایل تصویر"),
    )
    alt_text = models.CharField(
        max_length=180,
        verbose_name=_("متن جایگزین (Alt Text)"),
    )
    is_primary = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("تصویر اصلی محصول"),
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("ترتیب نمایش"),
    )

    class Meta:
        verbose_name = _("تصویر محصول")
        verbose_name_plural = _("تصاویر محصولات")
        ordering = ["-is_primary", "sort_order", "id"]

    def __str__(self) -> str:
        return f"تصویر {self.product.name} ({self.alt_text})"

    def clean(self) -> None:
        super().clean()
        if self.variant_id and self.product_id and self.variant.product_id != self.product_id:
            raise ValidationError(
                {"variant": _("گونه انتخاب‌شده متعلق به این محصول نیست.")}
            )