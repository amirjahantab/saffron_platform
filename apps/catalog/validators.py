"""
Security validators and randomized path generators for uploaded product images
and laboratory certificate files.

Enforces:
1. Strict file size limits.
2. Whitelisted file extensions.
3. Binary magic-byte inspection and Pillow structural verification.
4. Decompression bomb protection (maximum pixel resolution).
5. Active script rejection inside PDF documents (/JavaScript, /JS, /Launch).
6. UUID-based randomized storage filenames to prevent Path Traversal and overwrites.
"""
from pathlib import Path
import uuid
from typing import Any
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_CERTIFICATE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}

MAX_IMAGE_WIDTH = 5000
MAX_IMAGE_HEIGHT = 5000
MAX_IMAGE_PIXELS = 25_000_000  # 25 Megapixels limit against decompression bombs

FORBIDDEN_PDF_TOKENS = (
    b"/JavaScript",
    b"/JS",
    b"/Launch",
    b"/SubmitForm",
    b"/ImportData",
)


def _get_max_upload_size() -> int:
    return int(getattr(settings, "CATALOG_MAX_UPLOAD_SIZE_BYTES", 5 * 1024 * 1024))


def _validate_file_size(file_obj: Any) -> None:
    max_bytes = _get_max_upload_size()
    file_size = getattr(file_obj, "size", None)
    if file_size is None:
        raise ValidationError(_("امکان بررسی حجم فایل وجود ندارد."))
    if file_size <= 0:
        raise ValidationError(_("فایل بارگذاری‌شده خالی است."))
    if file_size > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise ValidationError(
            _("حجم فایل بیش از حد مجاز (%(max_mb)d مگابایت) است."),
            params={"max_mb": max_mb},
            code="file_too_large",
        )


def _validate_image_content(file_obj: Any) -> None:
    """Verify that the file is a genuine, non-corrupted JPEG, PNG, or WEBP image."""
    initial_pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        with Image.open(file_obj) as img:
            img_format = (img.format or "").upper()
            width, height = img.size
            if img_format not in ALLOWED_IMAGE_FORMATS:
                raise ValidationError(
                    _("فرمت واقعی تصویر معتبر نیست. فقط JPEG، PNG و WEBP مجاز هستند."),
                    code="invalid_image_format",
                )
            if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT or (width * height) > MAX_IMAGE_PIXELS:
                raise ValidationError(
                    _("ابعاد تصویر بیش از حد مجاز است (حداکثر ۵۰۰۰×۵۰۰۰ پیکسل)."),
                    code="image_dimensions_exceeded",
                )
            img.verify()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError(
            _("محتوای فایل تصویر معتبر نیست یا آسیب دیده است."),
            code="corrupted_image",
        ) from exc
    finally:
        if hasattr(file_obj, "seek"):
            file_obj.seek(initial_pos)


def _validate_pdf_content(file_obj: Any) -> None:
    """Verify PDF magic header (%PDF-) and reject embedded executable actions."""
    initial_pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        content = file_obj.read()
        if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
            raise ValidationError(
                _("ساختار فایل PDF معتبر نیست (هدر استاندارد PDF یافت نشد)."),
                code="invalid_pdf_signature",
            )
        if b"%%EOF" not in content[-1024:]:
            raise ValidationError(
                _("فایل PDF ناقص یا دستکاری شده است (پایان استاندارد EOF یافت نشد)."),
                code="incomplete_pdf",
            )
        for token in FORBIDDEN_PDF_TOKENS:
            if token in content:
                raise ValidationError(
                    _("فایل PDF حاوی اسکریپت یا دستور غیرمجاز است و به دلایل امنیتی پذیرفته نمی‌شود."),
                    code="unsafe_pdf_content",
                )
    finally:
        if hasattr(file_obj, "seek"):
            file_obj.seek(initial_pos)


def validate_product_image(file_obj: Any) -> None:
    """Validator for product and variant images."""
    _validate_file_size(file_obj)
    ext = Path(getattr(file_obj, "name", "")).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            _("پسوند فایل تصویر مجاز نیست. پسوندهای مجاز: jpg، jpeg، png، webp."),
            code="invalid_image_extension",
        )
    _validate_image_content(file_obj)


def validate_certificate_file(file_obj: Any) -> None:
    """Validator for laboratory authenticity certificates (PDF or verified Image)."""
    _validate_file_size(file_obj)
    ext = Path(getattr(file_obj, "name", "")).suffix.lower()
    if ext not in ALLOWED_CERTIFICATE_EXTENSIONS:
        raise ValidationError(
            _("پسوند فایل گواهی مجاز نیست. فقط فایل‌های PDF یا تصاویر (JPG, PNG, WEBP) مجاز هستند."),
            code="invalid_certificate_extension",
        )
    if ext == ".pdf":
        _validate_pdf_content(file_obj)
    else:
        _validate_image_content(file_obj)


def safe_product_image_upload_path(instance: Any, filename: str) -> str:
    """Generate a sanitized UUID path for product images."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = ".jpg"
    now = timezone.now()
    return f"catalog/products/{now:%Y/%m}/{uuid.uuid4().hex}{ext}"


def safe_certificate_upload_path(instance: Any, filename: str) -> str:
    """Generate a sanitized UUID path for laboratory certificates."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_CERTIFICATE_EXTENSIONS:
        ext = ".pdf"
    now = timezone.now()
    return f"catalog/certificates/{now:%Y/%m}/{uuid.uuid4().hex}{ext}"