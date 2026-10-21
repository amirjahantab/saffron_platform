"""One URL/indexing policy shared by HTML, response headers and sitemaps."""
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from django.utils.html import strip_tags

from apps.catalog.models import SaffronGrade


def absolute_url(path):
    # Never derive canonical URLs from a visitor-controlled Host header.
    return settings.SITE_URL + path


def indexing_policy(request):
    match = request.resolver_match
    name = match.view_name if match else ""
    public = name in {
        "storefront:home", "storefront:product_list",
        "storefront:category", "storefront:product_detail",
        "content:journal", "content:article", "content:policy", "content:faq",
    }
    allowed = {"page"} if name in {"storefront:product_list", "storefront:category", "content:journal"} else set()
    query_ok = all(key in allowed and len(request.GET.getlist(key)) == 1 for key in request.GET)
    page = request.GET.get("page", "1")
    query_ok = query_ok and len(page) <= 9 and page.isascii() and page.isdigit() and int(page) > 0
    return public and query_ok and request.method in {"GET", "HEAD"}


def metadata(context):
    request = context["request"]
    match = request.resolver_match
    name = match.view_name if match else ""
    canonical = None
    description = "خرید زعفران جهانتاب؛ مشاهده مشخصات، وزن، بسته‌بندی و قیمت محصولات."
    crumbs = [{"name": "صفحه اصلی", "path": reverse("storefront:home")}]
    if name == "storefront:home":
        canonical = absolute_url(reverse("storefront:home"))
    elif name.startswith("content:"):
        page = context.get("page_obj")
        canonical = absolute_url(request.path)
        if name == "content:journal" and page and page.number > 1:
            canonical += "?" + urlencode({"page": page.number})
        article = context.get("article")
        policy = context.get("policy")
        if article:
            description = article.meta_description or article.excerpt
            crumbs.extend([{"name": "مجله جهانتاب", "path": reverse("content:journal")}, {"name": article.title, "path": article.get_absolute_url()}])
        elif policy:
            description = strip_tags(policy.body)[:280]
            crumbs.append({"name": policy.title, "path": request.path})
    elif name in {"storefront:product_list", "storefront:category"}:
        grade = context.get("selected_grade")
        path = reverse("storefront:category", args=[grade]) if grade in SaffronGrade.values else reverse("storefront:product_list")
        page = context.get("page_obj")
        if page and page.number > 1:
            path += "?" + urlencode({"page": page.number})
        canonical = absolute_url(path)
        crumbs.append({"name": "کاتالوگ محصولات", "path": reverse("storefront:product_list")})
        if grade in SaffronGrade.values:
            label = str(dict(SaffronGrade.choices)[grade])
            crumbs.append({"name": "زعفران " + label, "path": reverse("storefront:category", args=[grade])})
            description = f"خرید زعفران {label}؛ مقایسه وزن، بسته‌بندی و قیمت محصولات موجود در کاتالوگ جهانتاب."
    elif name == "storefront:product_detail" and context.get("product"):
        product = context["product"]
        canonical = absolute_url(reverse("storefront:product_detail", args=[product.slug]))
        description = strip_tags(product.short_description)[:300]
        crumbs.extend([
            {"name": "کاتالوگ محصولات", "path": reverse("storefront:product_list")},
            {"name": "زعفران " + str(product.get_saffron_grade_display()), "path": reverse("storefront:category", args=[product.saffron_grade])},
            {"name": product.name, "path": reverse("storefront:product_detail", args=[product.slug])},
        ])

    graph = []
    if name == "content:article" and context.get("article"):
        article = context["article"]
        article_data = {"@type": "Article", "headline": article.title, "description": description, "url": canonical,
            "datePublished": article.published_at.isoformat(), "dateModified": article.updated_at.isoformat(),
            "author": {"@type": "Person", "name": article.author.full_name or "تحریریه جهانتاب"}}
        if article.cover:
            article_data["image"] = absolute_url(article.cover.url)
        graph.append(article_data)
    if canonical and len(crumbs) > 1:
        graph.append({
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": crumb["name"], "item": absolute_url(crumb["path"])}
                for i, crumb in enumerate(crumbs, 1)
            ],
        })
    if name == "storefront:product_detail" and context.get("product"):
        product = context["product"]
        data = {"@type": "Product", "name": product.name, "description": description, "url": canonical}
        images = context.get("images", [])
        if images:
            data["image"] = [absolute_url(img.image.url) if img.image.url.startswith("/") else img.image.url for img in images if img.image]
        # Schema describes exactly the server-rendered selected variant, including query selection.
        variant = context.get("selected_variant")
        if variant and (settings.STORE_OPEN or settings.DEMO_MODE):
            data["sku"] = variant.sku
            data["offers"] = {
                "@type": "Offer", "url": canonical + "?" + urlencode({"variant": str(variant.public_id)}),
                "priceCurrency": "IRR", "price": str(variant.effective_price_rial),
                "availability": "https://schema.org/InStock" if variant.is_in_stock else "https://schema.org/OutOfStock",
                "itemCondition": "https://schema.org/NewCondition",
            }
        graph.append(data)
    return {
        "canonical": canonical, "description": description,
        "robots": "index, follow" if indexing_policy(request) else "noindex, follow",
        "breadcrumbs": crumbs if len(crumbs) > 1 else [],
        "structured_data": {"@context": "https://schema.org", "@graph": graph} if graph else None,
    }
