from io import BytesIO, StringIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from PIL import Image

from apps.catalog.image_assets import derivative_name
from apps.catalog.models import Product, ProductImage, SaffronGrade


class CatalogImageOptimizationTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.directory.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        product = Product.objects.create(name="Image", slug="image", saffron_grade=SaffronGrade.SARGOL, short_description="x", description="x")
        buffer = BytesIO()
        Image.new("RGB", (1600, 1200), "red").save(buffer, "PNG")
        self.image = ProductImage.objects.create(product=product, image=SimpleUploadedFile("source.png", buffer.getvalue(), "image/png"), alt_text="تصویر محصول")

    def test_optimization_preserves_original_is_idempotent_and_renders_responsive_images(self):
        storage = self.image.image.storage
        original = storage.open(self.image.image.name).read()
        call_command("optimize_catalog_images", stdout=StringIO())
        for size in [400, 800, 1200]:
            with storage.open(derivative_name(self.image, size), "rb") as generated:
                with Image.open(generated) as opened:
                    self.assertEqual(opened.format, "WEBP")
                    self.assertEqual(opened.size, (size, size))
        self.assertEqual(storage.open(self.image.image.name).read(), original)
        output = StringIO()
        call_command("optimize_catalog_images", stdout=output)
        self.assertIn("Optimized 0", output.getvalue())
        response = self.client.get("/shop/image/")
        self.assertContains(response, 'type="image/webp"')
        self.assertContains(response, 'fetchpriority="high"')
        self.assertContains(response, 'width="800" height="800"')
        self.assertContains(self.client.get("/shop/"), 'loading="lazy"')

    def test_missing_derivatives_use_original_and_failed_conversion_is_reported(self):
        response = self.client.get("/shop/image/")
        self.assertContains(response, self.image.image.url)
        self.assertNotContains(response, 'type="image/webp"')
        self.image.image.storage.delete(self.image.image.name)
        with self.assertRaises(CommandError):
            call_command("optimize_catalog_images", stdout=StringIO())
