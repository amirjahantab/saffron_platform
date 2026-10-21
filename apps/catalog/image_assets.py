"""Precompute square WebP derivatives; never decode user images on web requests."""
import hashlib
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

SIZES = (400, 800, 1200)


def derivative_name(image, size):
    version = f"v1:{image.image.name}:{image.updated_at.isoformat()}"
    digest = hashlib.sha256(version.encode()).hexdigest()
    return f"catalog/optimized/{digest}-{size}.webp"


def generate_derivatives(image):
    storage = image.image.storage
    names = [derivative_name(image, size) for size in SIZES]
    if all(storage.exists(name) for name in names):
        return 0
    with storage.open(image.image.name, "rb") as source:
        with Image.open(source) as opened:
            if opened.width > 5000 or opened.height > 5000 or opened.width * opened.height > 25_000_000:
                raise ValueError("Image exceeds catalog pixel limit")
            oriented = ImageOps.exif_transpose(opened).convert("RGB")
            for size, name in zip(SIZES, names):
                if storage.exists(name):
                    continue
                resized = ImageOps.fit(oriented, (size, size), method=Image.Resampling.LANCZOS)
                result = BytesIO()
                resized.save(result, format="WEBP", quality=82, method=6)
                storage.save(name, ContentFile(result.getvalue()))
    return 1
