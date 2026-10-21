"""
Storefront HTML views for Phase 6 (Sub-phases 6.1 & 6.2):
- Home Page (`/`)
- Catalog / Category & Search Page (`/shop/`)
- Product Detail Page with Interactive Variant & Laboratory Authenticity Inspector (`/shop/<slug>/`)
- Interactive Shopping Cart Page & Actions (`/cart/`, `/cart/add/`, `/cart/update/`, `/cart/remove/`, `/cart/clear/`)
- Two-Step OTP Login & Registration Page (`/auth/login/`) and Secure POST Logout (`/auth/logout/`)
- Checkout & Shipping Address Page (`/checkout/`)
- Browser Sandbox Payment Gateway Simulator (`/payments/sandbox-gateway/<authority>/`)
- Server-Verified Payment Result / Receipt Page (`/payments/result/<provider>/`)
- Customer Account Dashboard, Order History, Order Detail & Cancellation (`/account/orders/...`)
"""
import secrets
from typing import Any
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.db import transaction
from django.db.models import Prefetch, Q
from django.core.paginator import InvalidPage, Paginator
from django.db.models import Min, F
from django.db.models.functions import Coalesce
from django.http import Http404
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from apps.accounts.forms import OTPRequestForm, OTPVerifyForm
from apps.accounts.models import User
from apps.accounts.services.otp_service import (
    OTPInvalidError,
    OTPRateLimitError,
    OTPService,
)
from apps.accounts.services.sms_provider import SMSDeliveryError
from apps.accounts.signals import user_logged_in_via_otp
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
from apps.core.currency import format_price_toman, rial_to_toman, to_persian_digits, validate_rial_amount
from apps.orders.exceptions import (
    CartError,
    EmptyCartCheckoutError,
    InsufficientStockError,
    InvalidOrderStateTransitionError,
    OrderError,
)
from apps.orders.forms import (
    CartAddItemForm,
    CartRemoveItemForm,
    CartUpdateItemForm,
    CheckoutForm,
    OrderCancelForm,
)
from apps.orders.models import Order, ShippingAddress
from apps.orders.services.cart_service import CartService
from apps.orders.services.checkout_service import CheckoutService
from apps.orders.services.reservation_service import OrderStateAndReservationService
from apps.payments.exceptions import (
    InvalidPaymentStateError,
    PaymentConfigurationError,
    PaymentError,
    PaymentGatewayCommunicationError,
    PaymentVerificationFailedError,
)
from apps.payments.models import PaymentProvider, PaymentTransaction
from apps.payments.services.payment_service import PaymentService
from apps.storefront.forms import UserProfileUpdateForm
from apps.content.models import Article


def _get_safe_redirect_url(request: HttpRequest, fallback_url_name: str = "storefront:home") -> str:
    """Validate `next` URL against Open Redirect attacks."""
    candidate = (
        request.POST.get("next")
        or request.GET.get("next")
        or request.META.get("HTTP_REFERER")
        or ""
    ).strip()
    if candidate and url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse(fallback_url_name)


def _extract_client_ip(request: HttpRequest) -> str:
    from apps.core.client_ip import client_ip
    return client_ip(request)


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


def _compute_cart_checkout_preview(cart_summary: dict[str, Any]) -> dict[str, Any]:
    """
    Compute authoritative shipping cost, free-shipping progress, and final payable amount
    in Rials and Tomans for Cart and Checkout pages.
    """
    items_payable_rial = validate_rial_amount(int(cart_summary["pricing"]["payable_rial"]))
    free_threshold_rial = validate_rial_amount(
        int(getattr(settings, "ORDER_FREE_SHIPPING_THRESHOLD_RIAL", 15_000_000))
    )

    if items_payable_rial > 0:
        shipping_cost_rial = CheckoutService.calculate_shipping_cost_rial(items_payable_rial)
    else:
        shipping_cost_rial = 0

    final_payable_rial = validate_rial_amount(items_payable_rial + shipping_cost_rial)
    remaining_for_free_rial = max(0, free_threshold_rial - items_payable_rial)
    is_free_shipping = items_payable_rial >= free_threshold_rial and items_payable_rial > 0

    if free_threshold_rial > 0:
        progress_pct = min(100, int((items_payable_rial * 100) // free_threshold_rial))
    else:
        progress_pct = 100

    return {
        "shipping_cost_rial": shipping_cost_rial,
        "shipping_cost_toman": rial_to_toman(shipping_cost_rial),
        "formatted_shipping_cost_toman": (
            "رایگان" if is_free_shipping else format_price_toman(shipping_cost_rial)
        ),
        "final_payable_rial": final_payable_rial,
        "final_payable_toman": rial_to_toman(final_payable_rial),
        "formatted_final_payable_toman": format_price_toman(final_payable_rial),
        "is_free_shipping": is_free_shipping,
        "remaining_for_free_formatted": format_price_toman(remaining_for_free_rial),
        "free_shipping_progress_pct": progress_pct,
    }


# ==============================================================================
# Sub-phase 6.1 Views: Home, Catalog Listing, Product Detail
# ==============================================================================

@require_GET
def home_page_view(request: HttpRequest) -> HttpResponse:
    """Storefront Home Page (`GET /`)."""
    variant_qs = _build_active_variant_queryset()
    image_qs = ProductImage.objects.order_by("-is_primary", "sort_order", "id")

    featured_products_qs = (
        Product.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch("variants", queryset=variant_qs, to_attr="active_variants"),
            Prefetch("images", queryset=image_qs, to_attr="ordered_images"),
        )
        .order_by("-is_featured", "-created_at")[:4]
    )

    product_cards = _enrich_product_cards(list(featured_products_qs))

    grade_metadata = {
        SaffronGrade.SUPER_NEGIN: {
            "subtitle": "رشته‌های درشت و یکدست؛ انتخابی برای سلیقه‌های خاص",
            "badge": "ممتاز صادراتی",
        },
        SaffronGrade.NEGIN: {
            "subtitle": "کلاله‌های درشت و خوش‌رنگ بدون سفیدی، مناسب مصرف خانگی اعلا و هدیه",
            "badge": "درجه یک",
        },
        SaffronGrade.SARGOL: {
            "subtitle": "سرگل خالص و معطر خراسان با رنگ‌دهی عالی برای آشپزی و زعفران‌دم‌کرده",
            "badge": "برای آشپزی",
        },
        SaffronGrade.PUSHAL: {
            "subtitle": "کلاله قرمز همراه بخش کوتاهی از خامه",
            "badge": "اصالت سنتی",
        },
        SaffronGrade.DOKHTAR_PICH: {
            "subtitle": "رشته کامل زعفران (کلاله و ریشه) با عطر ماندگار و فرآوری کاملاً طبیعی",
            "badge": "کامل و طبیعی",
        },
    }

    grade_showcase = []
    for code, label in SaffronGrade.choices:
        meta = grade_metadata.get(code, {"subtitle": "", "badge": ""})
        grade_showcase.append(
            {
                "code": code,
                "label": label,
                "subtitle": meta["subtitle"],
                "badge": meta["badge"],
            }
        )

    context = {
        "page_title": "فروشگاه تخصصی زعفران جهانتاب | مشخصات و خرید زعفران",
        "product_cards": product_cards,
        "grade_showcase": grade_showcase,
        "journal_articles": Article.objects.published().select_related("category")[:3],
    }
    return render(request, "storefront/home.html", context)


@require_GET
def product_list_page_view(request: HttpRequest, grade: str | None = None) -> HttpResponse:
    """Storefront Catalog & Category Filtering Page (`GET /shop/`)."""
    if grade is not None and grade not in SaffronGrade.values:
        raise Http404
    selected_grade = grade or request.GET.get("grade", "").strip()
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

    eligible = Q(variants__is_active=True, variants__packaging_type__is_active=True,
                 variants__harvest_batch__is_active=True)
    if selected_packaging:
        eligible &= Q(variants__packaging_type__slug=selected_packaging)
    if selected_sale_type in SaleChannelType.values:
        eligible &= Q(variants__sale_type=selected_sale_type)
    if selected_packaging or selected_sale_type:
        products_qs = products_qs.filter(eligible).distinct()
    if sort_by in {"price_asc", "price_desc"}:
        price = Coalesce("variants__discounted_price_rial", "variants__base_price_rial")
        products_qs = products_qs.annotate(
            available_price=Min(price, filter=eligible & Q(variants__stock_quantity__gte=F("variants__min_order_quantity"))),
            any_price=Min(price, filter=eligible),
        ).annotate(sort_price=Coalesce("available_price", "any_price"))
        ordering = F("sort_price").asc(nulls_last=True) if sort_by == "price_asc" else F("sort_price").desc(nulls_last=True)
        products_qs = products_qs.order_by(ordering, "pk")
    else:
        products_qs = products_qs.order_by(*products_qs.query.order_by, "pk")
    paginator = Paginator(products_qs, 24)
    try:
        page_obj = paginator.page(request.GET.get("page", "1"))
    except InvalidPage as exc:
        raise Http404("Invalid catalog page") from exc
    all_cards = _enrich_product_cards(list(page_obj.object_list))

    packaging_options = PackagingType.objects.filter(is_active=True).order_by("name")
    selected_grade_label = dict(SaffronGrade.choices).get(selected_grade, "")

    context = {
        "page_title": (
            f"خرید زعفران {selected_grade_label} | فروشگاه زعفران جهانتاب"
            if selected_grade_label
            else "کاتالوگ محصولات زعفران | فروشگاه زعفران جهانتاب"
        ),
        "product_cards": all_cards,
        "total_count": paginator.count,
        "page_obj": page_obj,
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
    """Storefront Product Detail Page (`GET /shop/<slug>/`)."""
    verified_certs_qs = (
        LabCertificate.objects.filter(is_verified=True).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.localdate()))
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
                    "document_url": cert.get_download_url() if cert.document_file else "",
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

    from apps.care.models import Review
    from apps.care.forms import ReviewForm
    from apps.orders.models import OrderItem
    from django.db.models import Exists, OuterRef
    purchases = OrderItem.objects.filter(order__user_id=OuterRef("user_id"), variant__product_id=OuterRef("product_id"), order__status__in=["paid", "processing", "shipped", "delivered"])

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
        "approved_reviews": Review.objects.filter(product=product, is_approved=True).annotate(is_verified_purchase=Exists(purchases))[:20],
        "review_form": ReviewForm(),
    }
    return render(request, "storefront/product_detail.html", context)


# ==============================================================================
# Sub-phase 6.2 Views: Shopping Cart & Mutations
# ==============================================================================

@never_cache
@require_GET
def cart_page_view(request: HttpRequest) -> HttpResponse:
    """
    Interactive Shopping Cart Page (`GET /cart/`).
    Displays real database line items, weights, discounts, shipping threshold progress,
    and final payable amount in Tomans.
    """
    cart = CartService.get_active_cart(request, create=False)
    cart_summary = CartService.serialize_cart(cart)
    checkout_preview = _compute_cart_checkout_preview(cart_summary)

    context = {
        "page_title": "سبد خرید | فروشگاه تخصصی زعفران جهانتاب",
        "cart": cart_summary,
        "preview": checkout_preview,
    }
    return render(request, "storefront/cart.html", context)


@never_cache
@require_POST
def storefront_cart_add_view(request: HttpRequest) -> HttpResponse:
    """Form POST endpoint (`POST /cart/add/`) for adding a variant to the cart."""
    form = CartAddItemForm(data=request.POST)
    next_url = _get_safe_redirect_url(request, fallback_url_name="storefront:product_list")

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


@never_cache
@require_POST
def storefront_cart_update_view(request: HttpRequest) -> HttpResponse:
    """Form POST endpoint (`POST /cart/update/`) for updating item quantity in `/cart/`."""
    form = CartUpdateItemForm(data=request.POST)
    if not form.is_valid():
        messages.error(request, _("تعداد واردشده معتبر نیست."))
        return redirect("storefront:cart_page")

    try:
        updated_item = CartService.update_item_quantity(
            request=request,
            variant_public_id=form.cleaned_data["variant_public_id"],
            new_quantity=form.cleaned_data["quantity"],
        )
        if updated_item is None:
            messages.info(request, _("آیتم از سبد خرید حذف شد."))
        else:
            messages.success(request, _("تعداد محصول در سبد خرید به‌روزرسانی شد."))
    except CartError as exc:
        messages.error(request, str(exc))

    return redirect("storefront:cart_page")


@never_cache
@require_POST
def storefront_cart_remove_view(request: HttpRequest) -> HttpResponse:
    """Form POST endpoint (`POST /cart/remove/`) for removing a variant from `/cart/`."""
    form = CartRemoveItemForm(data=request.POST)
    if form.is_valid():
        removed = CartService.remove_item(
            request=request,
            variant_public_id=form.cleaned_data["variant_public_id"],
        )
        if removed:
            messages.info(request, _("محصول از سبد خرید شما حذف شد."))
    return redirect("storefront:cart_page")


@never_cache
@require_POST
def storefront_cart_clear_view(request: HttpRequest) -> HttpResponse:
    """Form POST endpoint (`POST /cart/clear/`) for emptying the cart."""
    CartService.clear_cart(request)
    messages.info(request, _("سبد خرید شما خالی شد."))
    return redirect("storefront:cart_page")


# ==============================================================================
# Sub-phase 6.2 Views: Two-Step OTP Login & Logout
# ==============================================================================

@never_cache
@require_http_methods(["GET", "POST"])
def login_page_view(request: HttpRequest) -> HttpResponse:
    """
    Two-step OTP Authentication Page (`GET | POST /auth/login/`).
    Step 1 (`action=request_otp`): Validates Iranian mobile number and dispatches 6-digit OTP.
    Step 2 (`action=verify_otp`): Verifies OTP, logs user in, rotates session key,
    fires `user_logged_in_via_otp` (merging guest cart automatically), and redirects to `next`.
    """
    next_url = _get_safe_redirect_url(request, fallback_url_name="storefront:account_orders")
    if request.user.is_authenticated:
        return redirect(next_url)

    step = request.GET.get("step", "phone").strip()
    pending_phone = request.session.get("otp_pending_phone", "")
    cooldown_seconds = int(getattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 120))
    request_form = OTPRequestForm(initial={"phone_number": pending_phone})
    verify_form = OTPVerifyForm(initial={"phone_number": pending_phone})

    if request.method == "POST":
        action = request.POST.get("action", "request_otp").strip()
        client_ip = _extract_client_ip(request)

        if action == "change_phone":
            request.session.pop("otp_pending_phone", None)
            return redirect(f"{reverse('storefront:login_page')}?next={next_url}")

        if action == "request_otp":
            request_form = OTPRequestForm(data=request.POST)
            if request_form.is_valid():
                normalized_phone = request_form.cleaned_data["phone_number"]
                try:
                    dispatch_res = OTPService.request_otp(
                        raw_phone=normalized_phone,
                        client_ip=client_ip,
                    )
                    request.session["otp_pending_phone"] = dispatch_res.phone_number
                    cooldown_seconds = dispatch_res.cooldown_seconds
                    step = "verify"
                    verify_form = OTPVerifyForm(initial={"phone_number": dispatch_res.phone_number})
                    messages.success(
                        request,
                        _("کد تایید ۶ رقمی به شماره %(phone)s ارسال شد.")
                        % {"phone": to_persian_digits(dispatch_res.phone_number)},
                    )
                except OTPRateLimitError as exc:
                    request.session["otp_pending_phone"] = normalized_phone
                    cooldown_seconds = exc.retry_after
                    step = "verify"
                    verify_form = OTPVerifyForm(initial={"phone_number": normalized_phone})
                    messages.error(request, str(exc))
                except SMSDeliveryError as exc:
                    messages.error(request, str(exc))
            else:
                step = "phone"

        elif action == "verify_otp":
            verify_form = OTPVerifyForm(data=request.POST)
            step = "verify"
            if verify_form.is_valid():
                phone_number = verify_form.cleaned_data["phone_number"]
                code = verify_form.cleaned_data["code"]
                try:
                    verified_phone = OTPService.verify_otp(
                        raw_phone=phone_number,
                        raw_code=code,
                        client_ip=client_ip,
                    )
                    with transaction.atomic():
                        user, _created = User.objects.select_for_update().get_or_create(
                            phone_number=verified_phone,
                            defaults={"is_active": True, "is_phone_verified": True},
                        )
                        if not user.is_active:
                            messages.error(request, _("حساب کاربری شما غیرفعال شده است."))
                            return redirect("storefront:login_page")

                        user.is_phone_verified = True
                        user.last_otp_verified_at = timezone.now()
                        user.save(update_fields=["is_phone_verified", "last_otp_verified_at", "updated_at"])

                    pre_login_session_key = request.session.session_key
                    request.session.pop("otp_pending_phone", None)

                    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                    request.session.set_expiry(settings.SESSION_COOKIE_AGE)

                    user_logged_in_via_otp.send(
                        sender=User,
                        user=user,
                        request=request,
                        pre_login_session_key=pre_login_session_key,
                    )

                    messages.success(request, _("خوش آمدید! ورود شما با موفقیت انجام شد."))
                    return redirect(next_url)
                except (OTPInvalidError, OTPRateLimitError) as exc:
                    verify_form.add_error("code", str(exc))

    if step == "verify" and not request.session.get("otp_pending_phone") and not verify_form.data.get("phone_number"):
        step = "phone"

    active_phone = (
        verify_form.data.get("phone_number")
        or request.session.get("otp_pending_phone")
        or ""
    )

    context = {
        "page_title": "ورود / ثبت‌نام با شماره موبایل | زعفران جهانتاب",
        "step": step,
        "active_phone": active_phone,
        "cooldown_seconds": cooldown_seconds,
        "request_form": request_form,
        "verify_form": verify_form,
        "next_url": next_url,
    }
    return render(request, "storefront/login.html", context)


@never_cache
@require_POST
def storefront_logout_view(request: HttpRequest) -> HttpResponse:
    """CSRF-protected POST logout view (`POST /auth/logout/`)."""
    logout(request)
    messages.info(request, _("شما با موفقیت از حساب کاربری خود خارج شدید."))
    return redirect("storefront:home")


# ==============================================================================
# Sub-phase 6.2 Views: Checkout, Sandbox Gateway & Payment Receipt
# ==============================================================================

@never_cache
@require_http_methods(["GET", "POST"])
def checkout_page_view(request: HttpRequest) -> HttpResponse:
    """
    Storefront Checkout Page (`GET | POST /checkout/`).
    Requires authentication (redirects guests to OTP login with `?next=/checkout/` so guest cart merges).
    Validates shipping address, creates Order + StockReservations atomically, and redirects to Order Detail.
    """
    if not request.user.is_authenticated:
        messages.info(
            request,
            _("لطفاً برای ثبت نهایی سفارش و آدرس گیرنده، ابتدا با شماره موبایل خود وارد شوید. سبد خرید شما حفظ خواهد شد."),
        )
        return redirect(f"{reverse('storefront:login_page')}?next={reverse('storefront:checkout_page')}")

    user: User = request.user  # type: ignore[assignment]
    cart = CartService.get_active_cart(request, create=False)
    cart_summary = CartService.serialize_cart(cart)

    if cart_summary["items_count"] == 0:
        messages.warning(request, _("سبد خرید شما خالی است. لطفاً ابتدا محصول موردنظر را به سبد اضافه کنید."))
        return redirect("storefront:cart_page")

    saved_addresses = list(ShippingAddress.objects.filter(user=user).order_by("-is_default", "-created_at"))
    default_addr = saved_addresses[0] if saved_addresses else None

    if request.method == "POST":
        form = CheckoutForm(data=request.POST)
        if form.is_valid():
            cleaned = form.cleaned_data
            try:
                order, _created = CheckoutService.create_order_from_cart(
                    user=user,
                    shipping_address_public_id=cleaned.get("shipping_address_public_id"),
                    address_data={
                        "recipient_full_name": cleaned.get("recipient_full_name"),
                        "recipient_phone": cleaned.get("recipient_phone"),
                        "province": cleaned.get("province"),
                        "city": cleaned.get("city"),
                        "address_line": cleaned.get("address_line"),
                        "postal_code": cleaned.get("postal_code"),
                    },
                    save_new_address=bool(cleaned.get("save_address")),
                    shipping_method=cleaned["shipping_method"],
                    customer_note=cleaned.get("customer_note") or "",
                    idempotency_key=cleaned.get("idempotency_key"),
                )
                from apps.insights.services import attach_order
                attach_order(request, order)
                messages.success(
                    request,
                    _("سفارش شماره %(num)s با موفقیت ثبت و موجودی کالا برای شما رزرو شد. اکنون می‌توانید پرداخت را انجام دهید.")
                    % {"num": order.order_number},
                )
                return redirect("storefront:account_order_detail", order_number=order.order_number)
            except (InsufficientStockError, EmptyCartCheckoutError, CartError, OrderError) as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, _("لطفاً خطاهای مشخص‌شده در فرم آدرس و اطلاعات گیرنده را بررسی و اصلاح کنید."))
    else:
        initial_data: dict[str, Any] = {
            "recipient_full_name": user.full_name,
            "recipient_phone": user.phone_number,
            "shipping_method": Order.ShippingMethod.POST_PISHTAZ,
            "idempotency_key": secrets.token_hex(16),
            "save_address": True,
        }
        if default_addr:
            initial_data["shipping_address_public_id"] = default_addr.public_id
        form = CheckoutForm(initial=initial_data)

    checkout_preview = _compute_cart_checkout_preview(cart_summary)

    context = {
        "page_title": "تسویه‌حساب و ثبت سفارش | فروشگاه زعفران جهانتاب",
        "cart": cart_summary,
        "preview": checkout_preview,
        "saved_addresses": saved_addresses,
        "shipping_methods": Order.ShippingMethod.choices,
        "form": form,
        "idempotency_key": form["idempotency_key"].value() or secrets.token_hex(16),
    }
    return render(request, "storefront/checkout.html", context)


@never_cache
@require_POST
def storefront_order_pay_view(request: HttpRequest, order_number: str) -> HttpResponse:
    """
    Initiates a payment transaction (`POST /account/orders/<order_number>/pay/`)
    and redirects the customer's browser to the payment gateway URL.
    """
    if not request.user.is_authenticated:
        return redirect(f"{reverse('storefront:login_page')}?next={request.path}")

    user: User = request.user  # type: ignore[assignment]
    order = get_object_or_404(
        Order.objects.filter(user=user),
        order_number=order_number.strip().upper(),
    )

    provider_code = request.POST.get("provider", "").strip() or None
    try:
        _tx, redirect_url, _created = PaymentService.initiate_payment(
            order=order,
            user=user,
            provider_code=provider_code,
        )
        return redirect(redirect_url)
    except (InvalidPaymentStateError, PaymentConfigurationError, PaymentGatewayCommunicationError, PaymentError) as exc:
        messages.error(request, str(exc))
        return redirect("storefront:account_order_detail", order_number=order.order_number)


@never_cache
@require_GET
def sandbox_gateway_page_view(request: HttpRequest, authority: str) -> HttpResponse:
    """
    Interactive Browser Simulator for the Sandbox Payment Gateway
    (`GET /payments/sandbox-gateway/<authority>/`).
    Allows testing both Successful (`Status=OK`) and Cancelled (`Status=NOK`) callbacks in the browser.
    """
    if not settings.ALLOW_SANDBOX_PAYMENTS:
        raise Http404
    tx = get_object_or_404(
        PaymentTransaction.objects.select_related("order"),
        provider=PaymentProvider.SANDBOX,
        authority=authority.strip(),
    )
    from apps.orders.access import owns_order
    if not owns_order(request, tx.order):
        raise Http404
    context = {
        "page_title": "درگاه پرداخت آزمایشی شاپرک (Sandbox)",
        "tx": tx,
        "order": tx.order,
    }
    return render(request, "storefront/sandbox_gateway.html", context)


@never_cache
@require_http_methods(["GET", "POST"])
def payment_result_page_view(request: HttpRequest, provider: str) -> HttpResponse:
    """
    Storefront Payment Receipt / Result Page (`GET | POST /payments/result/<provider>/`).
    Executes mandatory server-side verification via `PaymentService.process_callback`
    and renders an official payment receipt or failure explanation.
    """
    authority = (
        request.GET.get("Authority")
        or request.GET.get("authority")
        or request.POST.get("Authority")
        or request.POST.get("authority")
        or ""
    ).strip()

    callback_status = (
        request.GET.get("Status")
        or request.GET.get("status")
        or request.POST.get("Status")
        or request.POST.get("status")
        or ""
    ).strip()

    tx: PaymentTransaction | None = None
    is_success = False
    error_message = ""
    already_processed = False

    try:
        tx, already_processed = PaymentService.process_callback(
            provider_code=provider,
            authority=authority,
            callback_status_param=callback_status,
        )
        is_success = True
    except (PaymentVerificationFailedError, PaymentGatewayCommunicationError, PaymentError) as exc:
        error_message = str(exc)
        if authority:
            tx = (
                PaymentTransaction.objects.select_related("order")
                .filter(provider=provider.strip().lower(), authority=authority)
                .first()
            )

    from apps.orders.access import owns_order
    if tx and not owns_order(request, tx.order):
        tx = None
        is_success = False
        error_message = "برای مشاهده رسید، به حساب صاحب سفارش وارد شوید یا از مرورگر ثبت سفارش استفاده کنید."
    elif tx and tx.order.user_id is None:
        return redirect("storefront:guest_order", order_number=tx.order.order_number)

    context = {
        "page_title": "نتیجه تراکنش بانکی | فروشگاه زعفران جهانتاب",
        "is_success": is_success,
        "already_processed": already_processed,
        "error_message": error_message,
        "tx": tx,
        "order": tx.order if tx else None,
    }
    return render(request, "storefront/payment_result.html", context)


# ==============================================================================
# Sub-phase 6.2 Views: Customer Account Dashboard & Order Management
# ==============================================================================

@never_cache
@require_http_methods(["GET", "POST"])
def account_orders_view(request: HttpRequest) -> HttpResponse:
    """
    Customer Account Dashboard & Order History (`GET | POST /account/orders/`).
    Allows updating profile info and viewing all personal orders and saved addresses.
    """
    if not request.user.is_authenticated:
        return redirect(f"{reverse('storefront:login_page')}?next={reverse('storefront:account_orders')}")

    user: User = request.user  # type: ignore[assignment]

    if request.method == "POST":
        profile_form = UserProfileUpdateForm(data=request.POST, instance=user)
        if profile_form.is_valid():
            profile_form.save()
            messages.success(request, _("اطلاعات حساب کاربری شما با موفقیت به‌روزرسانی شد."))
            return redirect("storefront:account_orders")
        messages.error(request, _("لطفاً خطاهای فرم مشخصات فردی را بررسی کنید."))
    else:
        profile_form = UserProfileUpdateForm(instance=user)

    orders = (
        Order.objects.filter(user=user)
        .prefetch_related("items")
        .order_by("-created_at")
    )
    saved_addresses = ShippingAddress.objects.filter(user=user).order_by("-is_default", "-created_at")

    context = {
        "page_title": "حساب کاربری و سفارش‌های من | فروشگاه زعفران جهانتاب",
        "profile_form": profile_form,
        "orders": orders,
        "saved_addresses": saved_addresses,
    }
    return render(request, "storefront/account_orders.html", context)


@never_cache
@require_GET
def account_order_detail_view(request: HttpRequest, order_number: str) -> HttpResponse:
    """
    Customer Order Detail & Invoice Page (`GET /account/orders/<order_number>/`).
    Strictly scoped to `request.user` (prevents IDOR).
    """
    if not request.user.is_authenticated:
        return redirect(f"{reverse('storefront:login_page')}?next={request.path}")

    user: User = request.user  # type: ignore[assignment]
    order = get_object_or_404(
        Order.objects.filter(user=user).prefetch_related(
            "items",
            "items__variant",
            "items__variant__product",
            "payments",
            "reservations",
        ),
        order_number=order_number.strip().upper(),
    )

    is_payable = (
        order.status == Order.Status.PENDING_PAYMENT
        and timezone.now() < order.reservation_expires_at
    )

    context = {
        "page_title": f"جزئیات سفارش {order.order_number} | زعفران جهانتاب",
        "order": order,
        "items": order.items.all(),
        "payments": order.payments.all().order_by("-created_at"),
        "is_payable": is_payable,
    }
    return render(request, "storefront/order_detail.html", context)


@never_cache
@require_POST
def storefront_order_cancel_view(request: HttpRequest, order_number: str) -> HttpResponse:
    """
    Customer Order Cancellation Action (`POST /account/orders/<order_number>/cancel/`).
    Cancels a `PENDING_PAYMENT` order owned by `request.user` and releases its reserved stock.
    """
    if not request.user.is_authenticated:
        return redirect("storefront:login_page")

    user: User = request.user  # type: ignore[assignment]
    order = get_object_or_404(
        Order.objects.filter(user=user),
        order_number=order_number.strip().upper(),
    )

    if order.status != Order.Status.PENDING_PAYMENT:
        messages.error(request, _("فقط سفارش‌های در وضعیت «در انتظار پرداخت» قابل لغو مستقیم هستند."))
        return redirect("storefront:account_order_detail", order_number=order.order_number)

    form = OrderCancelForm(data=request.POST)
    form.is_valid()
    reason = form.cleaned_data.get("cancel_reason") or _("لغو به درخواست مشتری در پنل کاربری")

    try:
        OrderStateAndReservationService.transition_order_status(
            order=order,
            target_status=Order.Status.CANCELLED,
            cancel_reason=str(reason),
        )
        messages.info(request, _("سفارش شما لغو شد و موجودی رزروشده به انبار بازگردانده شد."))
    except InvalidOrderStateTransitionError as exc:
        messages.error(request, str(exc))

    return redirect("storefront:account_order_detail", order_number=order.order_number)
