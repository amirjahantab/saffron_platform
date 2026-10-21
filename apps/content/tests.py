from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.core.tests.factories import user, catalog
from .models import Article, Category, PolicyPage


class ContentTests(TestCase):
    def setUp(self):
        self.author = user(full_name="نویسنده تست")
        self.category = Category.objects.create(name="راهنما", slug="guide")

    def article(self, **kwargs):
        data = dict(title="راهنمای واقعی", slug="guide", category=self.category, author=self.author, excerpt="چکیده واقعی", body='<script>alert("x")</script>\nمتن مقاله', status="published", published_at=timezone.now())
        data.update(kwargs)
        return Article.objects.create(**data)

    def test_drafts_future_and_unpublished_policies_are_not_public(self):
        draft = self.article(status="draft")
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)
        future = self.article(slug="future", published_at=timezone.now()+timedelta(days=1))
        self.assertEqual(self.client.get(future.get_absolute_url()).status_code, 404)
        PolicyPage.objects.create(slug="terms", title="Draft", body="x")
        self.assertEqual(self.client.get("/pages/terms/").status_code, 404)
        self.assertNotContains(self.client.get("/sitemap-articles.xml"), "/journal/future/")

    def test_published_article_safe_body_metadata_and_links(self):
        article = self.article()
        product, _ = catalog()
        article.products.add(product)
        response = self.client.get(article.get_absolute_url())
        self.assertContains(response, "چکیده واقعی")
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")
        self.assertContains(response, '"@type": "Article"')
        self.assertContains(response, "/shop/completion-saffron/")
        self.assertNotIn("X-Robots-Tag", response.headers)

    def test_renaming_slug_redirects_to_latest_without_chains(self):
        article = self.article()
        article.slug = "second"
        article.save()
        article.slug = "third"
        article.save()
        for slug in ["guide", "second"]:
            response = self.client.get(f"/journal/{slug}/")
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response.headers["Location"], "/journal/third/")
        article.status = "draft"
        article.save()
        self.assertEqual(self.client.get("/journal/guide/").status_code, 404)

    def test_reserved_old_slug_cannot_be_stolen(self):
        article = self.article()
        article.slug = "new"
        article.save()
        with self.assertRaises(ValidationError):
            self.article(slug="guide")

    def test_publish_requires_date(self):
        with self.assertRaises(ValidationError):
            self.article(published_at=None)

    def test_archive_filters_and_bad_pagination(self):
        self.article()
        self.assertContains(self.client.get("/journal/?category=guide"), "راهنمای واقعی")
        self.assertIn("noindex", self.client.get("/journal/?category=guide").headers["X-Robots-Tag"])
        self.assertEqual(self.client.get("/journal/?page=0").status_code, 404)
