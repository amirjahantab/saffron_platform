from django.core.management.base import BaseCommand, CommandError

from apps.catalog.image_assets import generate_derivatives
from apps.catalog.models import ProductImage


class Command(BaseCommand):
    help = "Generate versioned 400/800/1200px WebP catalog images without changing originals."

    def handle(self, *args, **options):
        count = 0
        for image in ProductImage.objects.filter(product__is_active=True).iterator():
            try:
                count += generate_derivatives(image)
            except (OSError, ValueError) as exc:
                raise CommandError(f"Image {image.pk}: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Optimized {count} image(s)."))
