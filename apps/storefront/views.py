"""
Storefront HTML views for Sub-phase 6.1:
- Home Page (`/`)
- Catalog / Category & Search Page (`/shop/`)
- Product Detail Page with Interactive Variant & Laboratory Authenticity Inspector (`/shop/<slug>/`)
- Form-compatible Add-to-Cart action (`/cart/add/`)
- Route stubs for Sub-phase 6.2 pages (`/cart/`, `/checkout/`, `/auth/login/`, `/account/orders/`)
  so navigation links resolve cleanly in all templates.
"""
from typing import Any
from django.contrib import messages
from django.db.models import Prefetch, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from apps.catalog.models import (
    LabCertificate,
    LabTestMetric,
    PackagingType,
    Product,
    ProductImage,
    ProductVariant,
    SaffronGrade,
    SaleChannelType,
)
from apps.core.currency import to_persian_digits
from apps.orders.exceptions import CartError
from apps.orders.forms import CartAddItemForm
from apps.orders.services.cart_service import CartService


def _build_active_variant_queryset() -> Any:
    """Return optimized queryset for active ProductVariants with active packaging and batch."""
    return (
        ProductVariant.objects.filter(
            is_active=True,
            packaging_type__is_active=True,
            harvest_batch__is_active=True,
        )
        .select_related("packaging_type", "harvest_batch")
        .order_by("sort_order", "net_weight_grams", "id")
    )


def _enrich_product_cards(products: list[Product]) -> list[dict[str, Any]]:
    """
    Attach authoritative starting variant, stock status, and primary image to each Product
    for rendering in `_product_card.html` without any hardcoded or fake numbers.
    """
    cards: list[dict[str, Any]] = []
    for product in products:
        active_variants: list[ProductVariant] = getattr(product, "active_variants", [])
        ordered_images: list[ProductImage] = getattr(product, "ordered_images", [])
        primary_image = ordered_images[0] if ordered_images else None

        in_stock_variants = [v for v in active_variants if v.is_in_stock]
        if in_stock_variants:
            representative_variant = min(in_stock_variants, key=lambda v: v.effective_price_rial)
            is_available = True
        elif active_variants:
            representative_variant = min(active_variants, key=lambda v: v.effective_price_rial)
            is_available = False
        else:
            representative_variant = None
            is_available = False

        cards.append(
            {
                "product": product,
                "primary_image": primary_image,
                "default_variant": representative_variant,
                "variants_count": len(active_variants),
                "is_available": is_available,
            }
        )
    return cards


@require_GET
def home_page_view(request: HttpRequest) -> HttpResponse:
    """
    Storefront Home Page (`GET /`).
    Displays real featured saffron products, grade categories, and laboratory quality guarantees.
    """
    variant_qs = _build_active_variant_queryset()
    image_qs = ProductImage.objects.order_by("-is_primary", "sort_order", "id")

    featured_products_qs = (
        Product.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch("variants", queryset=variant_qs, to_attr="active_variants"),
            Prefetch("images", queryset=image_qs, to_attr="ordered_images"),
        )
        .order_by("-is_featured", "-created_at")[:8]
    )

    product_cards = _enrich_product_cards(list(featured_products_qs))

    grade_Metadata = {
        SaffronGrade.SUPER_NEGIN: {
            "subtitle": "بالاترین قدرت رنگ‌دهی (کروسین بالای ۲۶۰) و کلاله‌های تمام‌قرمز صادراتی",
            "badge": "ممتاز صادراتی",
        },
        SaffronGrade.NEGIN: {
            "subtitle": "کلاله‌های درشت و خوش‌رنگ بدون سفیدی، مناسب مصرف خانگی اعلا و هدیه",
            "badge": "درجه یک",
        },
        SaffronGrade.SARGOL: {
            "subtitle": "سرگل خالص و معطر خراسان با رنگ‌دهی عالی برای آشپزی و زعفران‌دم‌کرده",
            "badge": "پرفروش‌ترین",
        },
        SaffronGrade.PUSHAL: {
            "subtitle": "کلاله قرمز به همراه بخش کوتاهی از خامه جهت اطمینان صددرصدی از اصالت سنتی",
            "badge": "اصالت سنتی",
        },
        SaffronGrade.DOKHTAR_PICH: {
            "subtitle": "رشته کامل زعفران (کلاله و ریشه) با عطر ماندگار و فرآوری کاملاً طبیعی",
            "badge": "کامل و طبیعی",
        },
    }

    grade_showcase = []
    for code, label in SaffronGrade.choices:
        meta = grade_Metadata.get(code, {"subtitle": "", "badge": ""})
        grade_showcase.append(
            {
                "code": code,
                "label": label,
                "subtitle": meta["subtitle"],
                "badge": meta["badge"],
            }
        )

    context = {
        "page_title": "فروشگاه تخصصی زعفران جهان‌تاب | خرید مستقیم زعفران آزمایش‌شده با برگه اصالت",
        "product_cards": product_cards,
        "grade_showcase": grade_showcase,
    }
    return render(request, "storefront/home.html", context)


@require_GET
def product_list_page_view(request: HttpRequest) -> HttpResponse:
    """
    Storefront Catalog & Category Filtering Page (`GET /shop/`).
    Supports filtering by saffron grade, packaging slug, sale channel (retail/wholesale),
    search query (`q`), and sorting.
    """
    selected_grade = request.GET.get("grade", "").strip()
    selected_packaging = request.GET.get("packaging", "").strip()
    selected_sale_type = request.GET.get("sale_type", "").strip()
    search_query = request.GET.get("q", "").strip()
    sort_by = request.GET.get("sort", "featured").strip()

    variant_qs = _build_active_variant_queryset()
    if selected_packaging:
        variant_qs = variant_qs.filter(packaging_type__slug=selected_packaging)
    if selected_sale_type in SaleChannelType.values:
        variant_qs = variant_qs.filter(sale_type=selected_sale_type)

    image_qs = ProductImage.objects.order_by("-is_primary", "sort_order", "id")

    products_qs = Product.objects.filter(is_active=True).prefetch_related(
        Prefetch("variants", queryset=variant_qs, to_attr="active_variants"),
        Prefetch("images", queryset=image_qs, to_attr="ordered_images"),
    )

    if selected_grade in SaffronGrade.values:
        products_qs = products_qs.filter(saffron_grade=selected_grade)

    if search_query:
        products_qs = products_qs.filter(
            Q(name__icontains=search_query)
            | Q(short_description__icontains=search_query)
            | Q(origin_summary__icontains=search_query)
            | Q(variants__sku__icontains=search_query)
        ).distinct()

    if sort_by == "newest":
        products_qs = products_qs.order_by("-created_at")
    else:
        products_qs = products_qs.order_by("-is_featured", "-created_at")

    all_cards = _enrich_product_cards(list(products_qs))

    # If filtering by packaging or sale_type, exclude products that have zero matching active variants
    if selected_packaging or selected_sale_type:
        all_cards = [c for c in all_cards if c["variants_count"] > 0]

    if sort_by == "price_asc":
        all_cards.sort(
            key=lambda c: c["default_variant"].effective_price_rial if c["default_variant"] else 10**15
        )
    elif sort_by == "price_desc":
        all_cards.sort(
            key=lambda c: c["default_variant"].effective_price_rial if c["default_variant"] else -1,
            reverse=True,
        )

    packaging_options = PackagingType.objects.filter(is_active=True).order_by("name")
    selected_grade_label = dict(SaffronGrade.choices).get(selected_grade, "")

    context = {
        "page_title": (
            f"خرید زعفران {selected_grade_label} | فروشگاه زعفران جهان‌تاب"
            if selected_grade_label
            else "کاتالوگ محصولات زعفران | فروشگاه زعفران جهان‌تاب"
        ),
        "product_cards": all_cards,
        "total_count": len(all_cards),
        "packaging_options": packaging_options,
        "sale_type_choices": SaleChannelType.choices,
        "selected_grade": selected_grade,
        "selected_grade_label": selected_grade_label,
        "selected_packaging": selected_packaging,
        "selected_sale_type": selected_sale_type,
        "search_query": search_query,
        "sort_by": sort_by,
    }
    return render(request, "storefront/product_list.html", context)


@require_GET
def product_detail_page_view(request: HttpRequest, slug: str) -> HttpResponse:
    """
    Storefront Product Detail Page (`GET /shop/<slug>/`).
    Renders interactive weight & packaging selector, real-time Rial/Toman pricing,
    stock availability, harvest batch traceability, and verified laboratory metrics.
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
        _build_active_variant_queryset()
        .prefetch_related(
            Prefetch(
                "harvest_batch__certificates",
                queryset=verified_certs_qs,
                to_attr="verified_certificates",
            )
        )
    )

    image_qs = ProductImage.objects.order_by("-is_primary", "sort_order", "id")

    product = get_object_or_404(
        Product.objects.filter(is_active=True).prefetch_related(
            Prefetch("variants", queryset=variant_qs, to_attr="active_variants"),
            Prefetch("images", queryset=image_qs, to_attr="ordered_images"),
        ),
        slug=slug,
    )

    active_variants: list[ProductVariant] = getattr(product, "active_variants", [])
    ordered_images: list[ProductImage] = getattr(product, "ordered_images", [])

    # Determine selected variant (either via `?variant=<public_id>` or first in-stock variant)
    requested_variant_id = request.GET.get("variant", "").strip()
    selected_variant: ProductVariant | None = None
    if requested_variant_id:
        selected_variant = next(
            (v for v in active_variants if str(v.public_id) == requested_variant_id),
            None,
        )
    if selected_variant is None and active_variants:
        in_stock_list = [v for v in active_variants if v.is_in_stock]
        selected_variant = in_stock_list[0] if in_stock_list else active_variants[0]

    # Build safe JSON payload for client-side interactive switching (zero fake prices)
    variants_client_data: list[dict[str, Any]] = []
    for v in active_variants:
        batch = v.harvest_batch
        certs_list = []
        for cert in getattr(batch, "verified_certificates", []):
            metrics_list = [
                {
                    "metric_type": m.metric_type,
                    "metric_type_label": str(m.get_metric_type_display()),
                    "title": m.metric_title,
                    "value": to_persian_digits(str(m.value)),
                    "unit": m.unit,
                    "min_standard_limit": (
                        to_persian_digits(str(m.min_standard_limit))
                        if m.min_standard_limit is not None
                        else "—"
                    ),
                    "max_standard_limit": (
                        to_persian_digits(str(m.max_standard_limit))
                        if m.max_standard_limit is not None
                        else "—"
                    ),
                    "test_date": to_persian_digits(m.test_date.isoformat()),
                    "reference_method": m.reference_method,
                }
                for m in getattr(cert, "ordered_metrics", [])
            ]
            certs_list.append(
                {
                    "public_id": str(cert.public_id),
                    "lab_name": cert.lab_name,
                    "certificate_number": cert.certificate_number,
                    "issue_date": to_persian_digits(cert.issue_date.isoformat()),
                    "standard_reference": cert.standard_reference,
                    "quality_grade_result": cert.quality_grade_result,
                    "document_url": cert.document_file.url if cert.document_file else "",
                    "metrics": metrics_list,
                }
            )

        max_selectable_qty = (
            min(v.max_order_quantity, v.stock_quantity) if v.is_in_stock else 0
        )

        variants_client_data.append(
            {
                "public_id": str(v.public_id),
                "sku": v.sku,
                "weight_label": v.weight_label,
                "net_weight_grams": to_persian_digits(str(v.net_weight_grams)),
                "gross_weight_grams": to_persian_digits(str(v.gross_weight_grams)),
                "sale_type": v.sale_type,
                "sale_type_label": str(v.get_sale_type_display()),
                "packaging_name": v.packaging_type.name,
                "packaging_material": v.packaging_type.material,
                "is_gift_suitable": v.packaging_type.is_gift_suitable,
                "has_discount": v.has_discount,
                "discount_percentage": to_persian_digits(str(v.discount_percentage)),
                "formatted_base_price_toman": v.formatted_base_price_toman,
                "formatted_effective_price_toman": v.formatted_effective_price_toman,
                "effective_price_rial": v.effective_price_rial,
                "is_in_stock": v.is_in_stock,
                "stock_quantity": v.stock_quantity,
                "stock_quantity_persian": to_persian_digits(str(v.stock_quantity)),
                "min_order_quantity": v.min_order_quantity,
                "max_order_quantity": max_selectable_qty,
                "batch": {
                    "batch_code": batch.batch_code,
                    "origin_region": batch.origin_region,
                    "harvest_year": to_persian_digits(str(batch.harvest_year)),
                    "drying_method": batch.drying_method,
                    "certificates": certs_list,
                },
            }
        )

    # Related products of the same saffron grade
    related_qs = (
        Product.objects.filter(is_active=True, saffron_grade=product.saffron_grade)
        .exclude(pk=product.pk)
        .prefetch_related(
            Prefetch("variants", queryset=_build_active_variant_queryset(), to_attr="active_variants"),
            Prefetch("images", queryset=image_qs, to_attr="ordered_images"),
        )[:4]
    )
    related_cards = _enrich_product_cards(list(related_qs))

    selected_batch = selected_variant.harvest_batch if selected_variant else None
    selected_certs = (
        getattr(selected_batch, "verified_certificates", []) if selected_batch else []
    )

    context = {
        "page_title": f"{product.name} | مشخصات، آزمایشگاه و خرید آنلاین",
        "product": product,
        "images": ordered_images,
        "primary_image": ordered_images[0] if ordered_images else None,
        "variants": active_variants,
        "selected_variant": selected_variant,
        "selected_batch": selected_batch,
        "selected_certificates": selected_certs,
        "variants_client_data": variants_client_data,
        "related_cards": related_cards,
    }
    return render(request, "storefront/product_detail.html", context)


@never_cache
@require_POST
def storefront_cart_add_view(request: HttpRequest) -> HttpResponse:
    """
    Form-friendly POST endpoint (`POST /cart/add/`) for adding a variant to the cart
    from product cards or the product detail page with accessible flash message feedback.
    """
    form = CartAddItemForm(data=request.POST)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("storefront:product_list")
    if not str(next_url).startswith("/"):
        next_url = reverse("storefront:product_list")

    if not form.is_valid():
        messages.error(request, _("اطلاعات گونه یا تعداد محصول معتبر نیست."))
        return redirect(next_url)

    try:
        item = CartService.add_item(
            request=request,
            variant_public_id=form.cleaned_data["variant_public_id"],
            quantity_to_add=form.cleaned_data["quantity"],
        )
        messages.success(
            request,
            _("«%(product)s (%(weight)s)» به سبد خرید شما اضافه شد.")
            % {
                "product": item.variant.product.name,
                "weight": item.variant.weight_label,
            },
        )
    except CartError as exc:
        messages.error(request, str(exc))

    return redirect(next_url)


# ==============================================================================
# Route Stubs for Sub-phase 6.2 (Cart, Checkout, Login, Account Orders)
# Provided so navigation links in `_navbar.html` and `_footer.html` resolve cleanly.
# Full interactive templates for these routes will be delivered in Sub-phase 6.2.
# ==============================================================================

@never_cache
@require_GET
def cart_page_stub_view(request: HttpRequest) -> HttpResponse:
    cart = CartService.get_active_cart(request, create=False)
    summary = CartService.serialize_cart(cart)
    return HttpResponse(
        f"صفحه سبد خرید (مبلغ قابل پرداخت: {summary['pricing']['formatted_payable_toman']})",
        content_type="text/html; charset=utf-8",
    )


@never_cache
@require_GET
def checkout_page_stub_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("صفحه تسویه‌حساب (تکمیل در زیرفاز ۶.۲)", content_type="text/html; charset=utf-8")


@never_cache
@require_GET
def login_page_stub_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("صفحه ورود با شماره موبایل OTP (تکمیل در زیرفاز ۶.۲)", content_type="text/html; charset=utf-8")


@never_cache
@require_GET
def account_orders_stub_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse("صفحه سفارش‌های حساب کاربری (تکمیل در زیرفاز ۶.۲)", content_type="text/html; charset=utf-8")