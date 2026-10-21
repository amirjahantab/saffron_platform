from django.core.paginator import Paginator, InvalidPage
from django.http import Http404, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from .models import Article, ArticleRedirect, Category, FAQ, PolicyPage, StoreProfile


@require_GET
def journal(request):
    articles = Article.objects.published().select_related("category", "author")
    if request.GET.get("category"):
        articles = articles.filter(category__slug=request.GET["category"])
    if request.GET.get("tag"):
        articles = articles.filter(tags__slug=request.GET["tag"])
    try:
        page = Paginator(articles, 9).page(request.GET.get("page", 1))
    except InvalidPage as exc:
        raise Http404 from exc
    return render(request, "content/journal.html", {"page_title": "مجله جهانتاب | قصه‌ها و دانستنی‌های زعفران", "page_obj": page, "categories": Category.objects.all()})


@require_GET
def article(request, slug):
    item = Article.objects.published().select_related("author", "category").filter(slug=slug).first()
    if not item:
        old = get_object_or_404(ArticleRedirect.objects.filter(article__in=Article.objects.published()).select_related("article"), old_slug=slug)
        return HttpResponsePermanentRedirect(old.article.get_absolute_url())
    from apps.storefront.views import _build_active_variant_queryset, _enrich_product_cards
    from django.db.models import Prefetch
    from apps.catalog.models import ProductImage
    products = item.products.filter(is_active=True).prefetch_related(Prefetch("variants", queryset=_build_active_variant_queryset(), to_attr="active_variants"), Prefetch("images", queryset=ProductImage.objects.order_by("-is_primary", "sort_order"), to_attr="ordered_images"))[:4]
    return render(request, "content/article.html", {"article": item, "page_title": item.meta_title or item.title, "product_cards": _enrich_product_cards(list(products))})


@require_GET
def policy(request, slug):
    item = get_object_or_404(PolicyPage, slug=slug, is_published=True)
    return render(request, "content/policy.html", {"policy": item, "profile": StoreProfile.objects.first(), "page_title": item.title})


@require_GET
def faq(request):
    return render(request, "content/faq.html", {"faqs": FAQ.objects.filter(is_published=True), "page_title": "پرسش‌های متداول"})
