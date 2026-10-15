"""
Read-only catalog endpoints serving real database records for products, variants,
harvest traceability, and verified laboratory metrics.
"""
from django.db.models import Prefetch
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from apps.catalog.models import (
    LabCertificate,
    LabTestMetric,
    Product,
    ProductImage,
    ProductVariant,
    SaffronGrade,
    SaleChannelType,
)


@require_GET
def product_list_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: GET /catalog/products/
    Optional query params:
      - grade: super_negin | negin | sargol | pushal | dokhtar_pich
      - sale_type: retail | wholesale
    Returns active products with their active variants and real database prices.
    """
    grade_filter = request.GET.get("grade", "").strip()
    sale_type_filter = request.GET.get("sale_type", "").strip()

    variant_qs = ProductVariant.objects.filter(
        is_active=True,
        packaging_type__is_active=True,
        harvest_batch__is_active=True,
    ).select_related("packaging_type", "harvest_batch").order_by("sort_order", "net_weight_grams")

    if sale_type_filter in SaleChannelType.values:
        variant_qs = variant_qs.filter(sale_type=sale_type_filter)

    image_qs = ProductImage.objects.order_by("-is_primary", "sort_order")

    products_qs = (
        Product.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch("variants", queryset=variant_qs, to_attr="active_variants"),
            Prefetch("images", queryset=image_qs, to_attr="ordered_images"),
        )
        .order_by("-is_featured", "-created_at")
    )

    if grade_filter in SaffronGrade.values:
        products_qs = products_qs.filter(saffron_grade=grade_filter)

    results = []
    for product in products_qs:
        active_variants: list[ProductVariant] = getattr(product, "active_variants", [])
        if sale_type_filter and not active_variants:
            continue

        ordered_images: list[ProductImage] = getattr(product, "ordered_images", [])
        primary_img = ordered_images[0] if ordered_images else None

        min_variant = min(active_variants, key=lambda v: v.effective_price_rial) if active_variants else None

        results.append(
            {
                "public_id": str(product.public_id),
                "name": product.name,
                "slug": product.slug,
                "saffron_grade": {
                    "code": product.saffron_grade,
                    "label": product.get_saffron_grade_display(),
                },
                "short_description": product.short_description,
                "origin_summary": product.origin_summary,
                "is_wholesale_available": product.is_wholesale_available,
                "is_featured": product.is_featured,
                "primary_image": (
                    {
                        "url": primary_img.image.url,
                        "alt_text": primary_img.alt_text,
                    }
                    if primary_img and primary_img.image
                    else None
                ),
                "starting_price": (
                    {
                        "amount_rial": min_variant.effective_price_rial,
                        "amount_toman": min_variant.effective_price_toman,
                        "formatted_toman": min_variant.formatted_effective_price_toman,
                    }
                    if min_variant
                    else None
                ),
                "available_variants_count": len(active_variants),
            }
        )

    return JsonResponse({"status": "ok", "count": len(results), "products": results}, status=200)


@require_GET
def product_detail_view(request: HttpRequest, slug: str) -> JsonResponse:
    """
    Endpoint: GET /catalog/products/<slug>/
    Returns comprehensive product details, active variants (weights, packaging, Rial/Toman prices, stock),
    harvest batch traceability, and verified laboratory certificates/metrics.
    """
    verified_certs_qs = (
        LabCertificate.objects.filter(is_verified=True)
        .prefetch_related(
            Prefetch(
                "metrics",
                queryset=LabTestMetric.objects.order_by("metric_type", "id"),
                to_attr="ordered_metrics",
            )
        )
        .order_by("-issue_date")
    )

    variant_qs = (
        ProductVariant.objects.filter(
            is_active=True,
            packaging_type__is_active=True,
            harvest_batch__is_active=True,
        )
        .select_related("packaging_type", "harvest_batch")
        .prefetch_related(
            Prefetch(
                "harvest_batch__certificates",
                queryset=verified_certs_qs,
                to_attr="verified_certificates",
            )
        )
        .order_by("sort_order", "net_weight_grams")
    )

    product = get_object_or_404(
        Product.objects.filter(is_active=True).prefetch_related(
            Prefetch("variants", queryset=variant_qs, to_attr="active_variants"),
            Prefetch("images", queryset=ProductImage.objects.order_by("-is_primary", "sort_order"), to_attr="ordered_images"),
        ),
        slug=slug,
    )

    variants_payload = []
    for variant in getattr(product, "active_variants", []):
        batch = variant.harvest_batch
        certs_payload = []
        for cert in getattr(batch, "verified_certificates", []):
            metrics_payload = [
                {
                    "metric_type": m.metric_type,
                    "metric_type_label": m.get_metric_type_display(),
                    "title": m.metric_title,
                    "value": str(m.value),
                    "unit": m.unit,
                    "min_standard_limit": str(m.min_standard_limit) if m.min_standard_limit is not None else None,
                    "max_standard_limit": str(m.max_standard_limit) if m.max_standard_limit is not None else None,
                    "test_date": m.test_date.isoformat(),
                    "reference_method": m.reference_method,
                }
                for m in getattr(cert, "ordered_metrics", [])
            ]
            certs_payload.append(
                {
                    "public_id": str(cert.public_id),
                    "lab_name": cert.lab_name,
                    "certificate_number": cert.certificate_number,
                    "issue_date": cert.issue_date.isoformat(),
                    "expiry_date": cert.expiry_date.isoformat() if cert.expiry_date else None,
                    "standard_reference": cert.standard_reference,
                    "quality_grade_result": cert.quality_grade_result,
                    "document_url": cert.document_file.url if cert.document_file else None,
                    "metrics": metrics_payload,
                }
            )

        variants_payload.append(
            {
                "public_id": str(variant.public_id),
                "sku": variant.sku,
                "sale_type": variant.sale_type,
                "sale_type_label": variant.get_sale_type_display(),
                "net_weight_grams": str(variant.net_weight_grams),
                "gross_weight_grams": str(variant.gross_weight_grams),
                "weight_label": variant.weight_label,
                "packaging": {
                    "public_id": str(variant.packaging_type.public_id),
                    "name": variant.packaging_type.name,
                    "slug": variant.packaging_type.slug,
                    "material": variant.packaging_type.material,
                    "is_gift_suitable": variant.packaging_type.is_gift_suitable,
                },
                "pricing": {
                    "base_price_rial": variant.base_price_rial,
                    "base_price_toman": variant.base_price_toman,
                    "formatted_base_price_toman": variant.formatted_base_price_toman,
                    "discounted_price_rial": variant.discounted_price_rial,
                    "discounted_price_toman": variant.discounted_price_toman,
                    "effective_price_rial": variant.effective_price_rial,
                    "effective_price_toman": variant.effective_price_toman,
                    "formatted_effective_price_toman": variant.formatted_effective_price_toman,
                    "has_discount": variant.has_discount,
                    "discount_percentage": variant.discount_percentage,
                },
                "inventory": {
                    "is_in_stock": variant.is_in_stock,
                    "stock_quantity": variant.stock_quantity,
                    "min_order_quantity": variant.min_order_quantity,
                    "max_order_quantity": variant.max_order_quantity,
                },
                "harvest_batch": {
                    "batch_code": batch.batch_code,
                    "origin_region": batch.origin_region,
                    "harvest_year": batch.harvest_year,
                    "harvest_date": batch.harvest_date.isoformat() if batch.harvest_date else None,
                    "drying_method": batch.drying_method,
                    "certificates": certs_payload,
                },
            }
        )

    images_payload = [
        {
            "public_id": str(img.public_id),
            "url": img.image.url if img.image else None,
            "alt_text": img.alt_text,
            "is_primary": img.is_primary,
            "variant_public_id": str(img.variant.public_id) if img.variant_id else None,
        }
        for img in getattr(product, "ordered_images", [])
    ]

    return JsonResponse(
        {
            "status": "ok",
            "product": {
                "public_id": str(product.public_id),
                "name": product.name,
                "slug": product.slug,
                "saffron_grade": {
                    "code": product.saffron_grade,
                    "label": product.get_saffron_grade_display(),
                },
                "short_description": product.short_description,
                "description": product.description,
                "origin_summary": product.origin_summary,
                "is_wholesale_available": product.is_wholesale_available,
                "is_featured": product.is_featured,
                "images": images_payload,
                "variants": variants_payload,
            },
        },
        status=200,
    )