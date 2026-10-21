from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.catalog.models import Product, SaffronGrade


class StorePagesSitemap(Sitemap):
    def items(self):
        return ["home", "product_list"] + list(SaffronGrade.values)

    def location(self, item):
        return reverse("storefront:" + item) if item in {"home", "product_list"} else reverse("storefront:category", args=[item])


class ProductsSitemap(Sitemap):
    limit = 1000

    def items(self):
        return Product.objects.filter(is_active=True).only("slug", "updated_at").order_by("pk")

    def location(self, item):
        return reverse("storefront:product_detail", args=[item.slug])

    def lastmod(self, item):
        return item.updated_at


class ArticlesSitemap(Sitemap):
    limit = 1000

    def items(self):
        from apps.content.models import Article
        return Article.objects.published().order_by("pk")

    def location(self, item):
        return item.get_absolute_url()

    def lastmod(self, item):
        return item.updated_at


class PoliciesSitemap(Sitemap):
    def items(self):
        from apps.content.models import PolicyPage
        return list(PolicyPage.objects.filter(is_published=True).values_list("slug", flat=True)) + ["journal", "faq"]

    def location(self, item):
        return reverse("content:" + item) if item in {"journal", "faq"} else reverse("content:policy", args=[item])
