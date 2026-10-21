import json
import re
from decimal import Decimal
from unittest.mock import patch
from xml.etree import ElementTree

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.catalog.models import HarvestBatch, PackagingType, Product, ProductVariant, SaffronGrade


@override_settings(SITE_URL="https://saffron.example")
class SearchVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            name="زعفران تست", slug="زعفران-تست", saffron_grade=SaffronGrade.SUPER_NEGIN,
            short_description='ویژگی واقعی </script><script>alert("x")</script>', description="توضیحات",
        )
        cls.packaging = PackagingType.objects.create(name="بسته", slug="box")
        cls.batch = HarvestBatch.objects.create(
            batch_code="SEO-01", saffron_grade=SaffronGrade.SUPER_NEGIN, origin_region="قائنات", harvest_year=1405,
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, packaging_type=cls.packaging, harvest_batch=cls.batch,
            sku="SEO-1", net_weight_grams=Decimal("1"), weight_label="۱ گرم",
            base_price_rial=500000, discounted_price_rial=400000, stock_quantity=4,
        )

    def schema(self, response):
        return json.loads(re.search(r'<script id="seo-structured-data" type="application/ld\+json">(.*?)</script>', response.content.decode(), re.S)[1])["@graph"]

    def detail_url(self):
        return reverse("storefront:product_detail", args=[self.product.slug])

    def test_public_pages_have_canonical_and_index_metadata(self):
        for url in ["/", "/shop/", "/shop/category/super_negin/", self.detail_url()]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'name="robots" content="index, follow"')
                self.assertNotIn("X-Robots-Tag", response.headers)
                self.assertContains(response, 'rel="canonical" href="https://saffron.example')

    def test_filters_search_tracking_and_duplicate_parameters_are_noindex(self):
        for query in ["q=secret", "grade=super_negin", "sort=newest", "utm_source=ads", "page=1&page=1"]:
            with self.subTest(query=query):
                response = self.client.get("/shop/?" + query)
                self.assertEqual(response.headers["X-Robots-Tag"], "noindex, follow")
                self.assertContains(response, 'name="robots" content="noindex, follow"')
        response = self.client.get("/shop/?grade=super_negin")
        self.assertContains(response, 'rel="canonical" href="https://saffron.example/shop/category/super_negin/"')

    def test_private_api_error_and_redirect_responses_are_noindex(self):
        for url in ["/cart/", "/auth/login/", "/checkout/", "/account/orders/", "/catalog/products/", "/missing/", "/shop/missing/"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn("noindex", response.headers["X-Robots-Tag"])

    def test_product_schema_matches_visible_price_stock_and_sku(self):
        response = self.client.get(self.detail_url())
        product = next(item for item in self.schema(response) if item["@type"] == "Product")
        self.assertEqual(product["sku"], "SEO-1")
        self.assertEqual(product["offers"]["priceCurrency"], "IRR")
        self.assertEqual(product["offers"]["price"], "400000")
        self.assertEqual(product["offers"]["availability"], "https://schema.org/InStock")
        self.assertContains(response, self.variant.formatted_effective_price_toman)
        self.assertNotIn("aggregateRating", product)
        self.assertNotIn("review", product)

    def test_selected_variant_schema_and_unavailable_stock(self):
        second = ProductVariant.objects.create(
            product=self.product, packaging_type=self.packaging, harvest_batch=self.batch,
            sku="SEO-2", net_weight_grams=Decimal("2"), weight_label="۲ گرم",
            base_price_rial=900000, stock_quantity=0,
        )
        response = self.client.get(self.detail_url(), {"variant": str(second.public_id)})
        product = next(item for item in self.schema(response) if item["@type"] == "Product")
        self.assertEqual(product["offers"]["price"], "900000")
        self.assertEqual(product["sku"], "SEO-2")
        self.assertEqual(product["offers"]["availability"], "https://schema.org/OutOfStock")
        self.assertIn("noindex", response.headers["X-Robots-Tag"])

    def test_no_active_variant_has_no_fabricated_offer(self):
        self.variant.is_active = False
        self.variant.save()
        response = self.client.get(self.detail_url())
        product = next(item for item in self.schema(response) if item["@type"] == "Product")
        self.assertNotIn("offers", product)

    def test_breadcrumb_schema_and_visible_links_agree(self):
        response = self.client.get(self.detail_url())
        breadcrumb = next(item for item in self.schema(response) if item["@type"] == "BreadcrumbList")
        self.assertEqual([item["position"] for item in breadcrumb["itemListElement"]], [1, 2, 3, 4])
        for item in breadcrumb["itemListElement"]:
            self.assertContains(response, item["name"])
        self.assertContains(response, 'href="/shop/category/super_negin/"')

    def test_canonical_does_not_use_request_host(self):
        response = self.client.get(self.detail_url(), HTTP_HOST="localhost")
        self.assertContains(response, 'href="https://saffron.example/shop/')
        self.assertNotContains(response, 'rel="canonical" href="http://localhost')

    def test_json_ld_cannot_break_out_of_script(self):
        self.product.name = '</script><script id="injected">bad()</script>'
        self.product.save()
        response = self.client.get(self.detail_url())
        self.assertNotContains(response, '<script id="injected">')
        self.assertEqual(next(item for item in self.schema(response) if item["@type"] == "Product")["name"], self.product.name)

    def test_sitemap_only_contains_active_public_urls_and_uses_canonical_host(self):
        Product.objects.create(name="Hidden", slug="hidden", saffron_grade=SaffronGrade.SARGOL, short_description="x", description="x", is_active=False)
        for url in ["/sitemap.xml", "/sitemap-pages.xml", "/sitemap-products.xml"]:
            response = self.client.get(url, HTTP_HOST="localhost")
            self.assertEqual(response.status_code, 200)
            root = ElementTree.fromstring(response.content)
            locations = [node.text for node in root.iter() if node.tag.endswith("}loc")]
            self.assertTrue(all(loc.startswith("https://saffron.example/") for loc in locations))
            self.assertFalse(any("hidden" in loc or "/cart/" in loc or "/account/" in loc for loc in locations))
        self.assertContains(self.client.get("/sitemap-products.xml"), self.detail_url())

    def test_sitemap_sections_paginate(self):
        Product.objects.create(name="Second", slug="second", saffron_grade=SaffronGrade.SARGOL, short_description="x", description="x")
        with patch("apps.storefront.sitemaps.ProductsSitemap.limit", 1):
            self.assertContains(self.client.get("/sitemap.xml"), "sitemap-products.xml?p=2")
            self.assertEqual(self.client.get("/sitemap-products.xml?p=2").status_code, 200)
            self.assertEqual(self.client.get("/sitemap-products.xml?p=3").status_code, 404)

    def test_robots_exposes_sitemap_without_hiding_noindex_pages_from_crawlers(self):
        response = self.client.get("/robots.txt")
        self.assertContains(response, "Sitemap: https://saffron.example/sitemap.xml")
        self.assertNotContains(response, "Disallow: /cart/")

    def test_pagination_bounds_work_and_second_page_has_own_canonical(self):
        for i in range(26):
            Product.objects.create(name=f"Item {i}", slug=f"item-{i}", saffron_grade=SaffronGrade.SARGOL, short_description="x", description="x")
        response = self.client.get("/shop/")
        self.assertEqual(len(response.context["product_cards"]), 24)
        self.assertEqual(response.context["total_count"], 27)
        response = self.client.get("/shop/?page=2")
        self.assertEqual(len(response.context["product_cards"]), 3)
        self.assertContains(response, 'rel="canonical" href="https://saffron.example/shop/?page=2"')
        self.assertContains(response, 'rel="prev"')
        for page in ["0", "-1", "999", "abc"]:
            self.assertEqual(self.client.get("/shop/", {"page": page}).status_code, 404)

    def test_catalog_queries_are_bounded_for_full_page(self):
        for i in range(25):
            product = Product.objects.create(name=f"Query {i}", slug=f"query-{i}", saffron_grade=SaffronGrade.SARGOL, short_description="x", description="x")
            ProductVariant.objects.create(product=product, packaging_type=self.packaging, harvest_batch=self.batch,
                sku=f"QUERY-{i}", net_weight_grams=1, weight_label="۱ گرم", base_price_rial=100000, stock_quantity=1)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get("/shop/")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(captured), 10)

    def test_price_sorting_and_filter_pagination(self):
        response = self.client.get("/shop/?sort=price_asc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product_cards"][0]["default_variant"].sku, "SEO-1")
        self.assertEqual(self.client.get("/shop/?sort=price_desc").status_code, 200)
        self.assertEqual(self.client.get("/shop/?packaging=missing").context["total_count"], 0)

    def test_unknown_category_is_404(self):
        self.assertEqual(self.client.get("/shop/category/missing/").status_code, 404)

    def test_assets_are_local_and_runtime_tailwind_is_removed(self):
        response = self.client.get("/")
        self.assertContains(response, "/static/css/tailwind.css")
        self.assertNotContains(response, "cdn.tailwindcss.com")
        self.assertNotContains(response, "cdn.jsdelivr.net")
