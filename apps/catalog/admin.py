"""Django Admin configuration for Catalog, Variants, Harvest Batches, and Lab Certificates."""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from apps.catalog.models import (
    HarvestBatch,
    LabCertificate,
    LabTestMetric,
    PackagingType,
    Product,
    ProductImage,
    ProductVariant,
)


@admin.register(PackagingType)
class PackagingTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "material", "tare_weight_grams", "is_gift_suitable", "is_active")
    list_filter = ("is_gift_suitable", "is_active")
    search_fields = ("name", "material", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("public_id", "created_at", "updated_at")


class LabTestMetricInline(admin.TabularInline):
    model = LabTestMetric
    extra = 1
    fields = (
        "metric_type",
        "metric_title",
        "value",
        "unit",
        "min_standard_limit",
        "max_standard_limit",
        "test_date",
        "reference_method",
    )


@admin.register(LabCertificate)
class LabCertificateAdmin(admin.ModelAdmin):
    list_display = (
        "certificate_number",
        "harvest_batch",
        "lab_name",
        "quality_grade_result",
        "issue_date",
        "is_verified",
    )
    list_filter = ("is_verified", "issue_date", "harvest_batch__saffron_grade")
    search_fields = ("certificate_number", "lab_name", "harvest_batch__batch_code")
    readonly_fields = ("public_id", "created_at", "updated_at")
    inlines = [LabTestMetricInline]


@admin.register(HarvestBatch)
class HarvestBatchAdmin(admin.ModelAdmin):
    list_display = (
        "batch_code",
        "saffron_grade",
        "origin_region",
        "harvest_year",
        "drying_method",
        "is_active",
    )
    list_filter = ("saffron_grade", "harvest_year", "is_active")
    search_fields = ("batch_code", "origin_region", "farm_or_supplier_code")
    readonly_fields = ("public_id", "created_at", "updated_at")


class ProductVariantInline(admin.StackedInline):
    model = ProductVariant
    extra = 0
    fields = (
        ("sku", "is_active", "sort_order"),
        ("packaging_type", "harvest_batch", "sale_type"),
        ("net_weight_grams", "weight_label"),
        ("base_price_rial", "discounted_price_rial", "stock_quantity"),
        ("min_order_quantity", "max_order_quantity"),
    )


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt_text", "variant", "is_primary", "sort_order")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "saffron_grade",
        "origin_summary",
        "is_wholesale_available",
        "is_featured",
        "is_active",
        "created_at",
    )
    list_filter = ("saffron_grade", "is_wholesale_available", "is_featured", "is_active")
    search_fields = ("name", "slug", "short_description", "origin_summary")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("public_id", "created_at", "updated_at")
    inlines = [ProductVariantInline, ProductImageInline]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "product",
        "weight_label",
        "packaging_type",
        "harvest_batch",
        "sale_type",
        "display_effective_price_toman",
        "stock_quantity",
        "is_active",
    )
    list_filter = (
        "is_active",
        "sale_type",
        "product__saffron_grade",
        "packaging_type",
    )
    search_fields = ("sku", "product__name", "weight_label", "harvest_batch__batch_code")
    readonly_fields = ("public_id", "created_at", "updated_at", "display_effective_price_toman")

    @admin.display(description=_("قیمت نهایی (تومان)"))
    def display_effective_price_toman(self, obj: ProductVariant) -> str:
        return obj.formatted_effective_price_toman