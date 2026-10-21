import json
import re
from django.utils import timezone
from apps.core.client_ip import client_ip
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils.crypto import salted_hmac
from apps.core.limits import enforce_limit
from apps.core.currency import format_price_toman
from apps.catalog.models import Product, ProductVariant
from apps.content.models import PolicyPage
from .models import Usage
from .provider import OpenAIResponsesProvider, AssistantProviderError


def handoff(message="این پرسش به بررسی پشتیبان نیاز دارد. از بخش پشتیبانی برای ما پیام بفرستید."):
    return {"message": message, "products": [], "support_url": reverse("care:inbox")}


def answer(request, message):
    if not settings.ASSISTANT_ENABLED:
        return handoff("دستیار در حال حاضر غیرفعال است. پشتیبانی جهانتاب در دسترس شماست.")
    identity = str(request.user.pk) if request.user.is_authenticated else client_ip(request)
    identity = salted_hmac("assistant-rate", identity).hexdigest()
    if not enforce_limit("assistant:" + identity, settings.ASSISTANT_HOURLY_LIMIT, 3600):
        return handoff("سقف استفاده ساعتی تکمیل شده است. کمی بعد دوباره تلاش کنید.")
    # Ownership is resolved server-side before the model; private data never leaves here.
    numbers = re.findall(r"JHT-[A-Z0-9-]{6,40}", message.upper())
    if numbers:
        if not request.user.is_authenticated:
            return handoff("برای مشاهده وضعیت سفارش، ابتدا وارد حساب خود شوید.")
        item = request.user.orders.filter(order_number=numbers[0]).first()
        if not item:
            return handoff("این سفارش در حساب شما پیدا نشد. شماره را بررسی کنید یا با پشتیبانی تماس بگیرید.")
        return {"message": f"وضعیت سفارش {item.order_number}: {item.get_status_display()}", "products": [], "order_url": reverse("storefront:account_order_detail", args=[item.order_number])}

    catalog = list(Product.objects.filter(is_active=True).order_by("-is_featured", "pk").values("slug", "name", "short_description")[:30])
    policies = list(PolicyPage.objects.filter(is_published=True).values("slug", "title"))
    provider = OpenAIResponsesProvider()
    payload = provider.build_payload(message, catalog, policies)
    reserve = len(json.dumps(payload).encode()) + 2400
    key = "assistant:daily:" + timezone.localdate().isoformat()
    cache.add(key, 0, timeout=90000)
    try:
        reserved = cache.incr(key, reserve)
    except ValueError:
        return handoff("سرویس موقتاً در دسترس نیست؛ لطفاً دوباره تلاش کنید.")
    if reserved > settings.ASSISTANT_DAILY_TOKEN_BUDGET:
        return handoff("ظرفیت امروز دستیار تکمیل شده است. پشتیبانی همچنان در دسترس است.")
    usage = Usage.objects.create(status="reserved", reserved_tokens=reserve)
    try:
        selection, tokens, response_id = provider.select(payload)
        allowed = {item["slug"] for item in catalog}
        if not isinstance(selection, dict) or set(selection) != {"intent", "product_slugs", "policy_slug"}:
            raise AssistantProviderError("Invalid intent schema")
        slugs = selection["product_slugs"]
        if not isinstance(slugs, list) or len(slugs) > 4 or any(not isinstance(slug, str) or slug not in allowed for slug in slugs):
            raise AssistantProviderError("Unknown products")
        intent = selection["intent"]
        if intent not in {"recommend", "compare", "policy", "order", "unclear", "handoff"}:
            raise AssistantProviderError("Unknown intent")
        usage.input_tokens = max(0, int(tokens.get("input_tokens", 0)))
        usage.output_tokens = max(0, int(tokens.get("output_tokens", 0)))
        usage.provider_response_id = str(response_id)[:100]
        usage.status = "completed"
        usage.save()
        if intent in {"recommend", "compare"} and slugs:
            products = []
            for slug in dict.fromkeys(slugs):
                product = Product.objects.filter(slug=slug, is_active=True).first()
                if not product:
                    continue
                variant = ProductVariant.objects.filter(product=product, is_active=True, packaging_type__is_active=True, harvest_batch__is_active=True).order_by("sort_order", "pk").first()
                products.append({"name": product.name, "url": reverse("storefront:product_detail", args=[slug]), "price": format_price_toman(variant.effective_price_rial) if variant else None,
                    "available": variant.is_in_stock if variant else False, "weight": variant.weight_label if variant else "", "origin": product.origin_summary})
            return {"message": "مشخصات زیر از کاتالوگ فعلی خوانده شده‌اند. برای مدارک آزمایشگاهی و انتخاب بسته‌بندی، صفحه محصول را باز کنید.", "products": products}
        if intent == "policy":
            policy = PolicyPage.objects.filter(slug=selection["policy_slug"], is_published=True).first()
            if policy:
                return {"message": policy.body[:1500], "products": [], "policy_url": reverse("content:policy", args=[policy.slug])}
        if intent == "order":
            return handoff("شماره سفارش خود را وارد کنید؛ وضعیت فقط پس از ورود و از حساب خودتان نمایش داده می‌شود.")
        if intent == "unclear":
            return handoff("برای راهنمایی دقیق‌تر، مصرف خانگی یا هدیه بودن، وزن دلخواه و بودجه‌تان را بگویید.")
        return handoff()
    except (AssistantProviderError, ValueError, TypeError, AttributeError):
        usage.status = "failed"
        usage.save(update_fields=["status"])
        return handoff("پاسخ قابل اطمینانی دریافت نشد. لطفاً پرسش را روشن‌تر بنویسید یا به پشتیبان پیام بدهید.")
