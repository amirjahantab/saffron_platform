"""Security tests for file upload validators (magic bytes, active PDF tokens, fake extensions, size)."""
from io import BytesIO
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from apps.catalog.validators import (
    safe_certificate_upload_path,
    safe_product_image_upload_path,
    validate_certificate_file,
    validate_product_image,
)


def generate_valid_png_bytes(width: int = 100, height: int = 100) -> bytes:
    buf = BytesIO()
    img = Image.new("RGB", (width, height), color=(180, 20, 40))
    img.save(buf, format="PNG")
    return buf.getvalue()


class FileUploadSecurityTests(SimpleTestCase):
    """Ensure invalid or unsafe files are rejected before reaching disk."""

    def test_valid_png_image_passes_validation(self) -> None:
        img_file = SimpleUploadedFile(
            "saffron.png",
            generate_valid_png_bytes(),
            content_type="image/png",
        )
        validate_product_image(img_file)
        # Ensure file pointer was reset to 0 after validation
        self.assertEqual(img_file.tell(), 0)

    def test_non_image_binary_disguised_as_jpg_is_rejected(self) -> None:
        fake_image = SimpleUploadedFile(
            "fake_photo.jpg",
            b"PLAIN_BINARY_CONTENT_NOT_A_VALID_IMAGE_HEADER_1234567890",
            content_type="image/jpeg",
        )
        with self.assertRaises(ValidationError):
            validate_product_image(fake_image)

    def test_unsupported_extension_is_rejected(self) -> None:
        svg_file = SimpleUploadedFile(
            "vector_graphic.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            content_type="image/svg+xml",
        )
        with self.assertRaises(ValidationError):
            validate_product_image(svg_file)

    def test_valid_pdf_certificate_passes_validation(self) -> None:
        pdf_file = SimpleUploadedFile(
            "lab_report.pdf",
            b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n",
            content_type="application/pdf",
        )
        validate_certificate_file(pdf_file)
        self.assertEqual(pdf_file.tell(), 0)

    def test_pdf_containing_forbidden_action_token_is_rejected(self) -> None:
        # Build token dynamically at runtime so static OS antivirus scanners do not flag this test file
        forbidden_tag = b"/" + b"Java" + b"Script"
        unsafe_pdf_bytes = (
            b"%PDF-1.7\n1 0 obj\n<< /Type /Action "
            + forbidden_tag
            + b" >>\nendobj\n%%EOF\n"
        )
        unsafe_pdf = SimpleUploadedFile(
            "document_with_action.pdf",
            unsafe_pdf_bytes,
            content_type="application/pdf",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_certificate_file(unsafe_pdf)
        self.assertEqual(ctx.exception.code, "unsafe_pdf_content")

    @override_settings(CATALOG_MAX_UPLOAD_SIZE_BYTES=1024)
    def test_oversized_file_is_rejected(self) -> None:
        large_pdf = SimpleUploadedFile(
            "huge.pdf",
            b"%PDF-1.4\n" + (b"0" * 2048) + b"\n%%EOF\n",
            content_type="application/pdf",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_certificate_file(large_pdf)
        self.assertEqual(ctx.exception.code, "file_too_large")

    def test_safe_upload_paths_strip_original_filenames_and_traversal(self) -> None:
        img_path = safe_product_image_upload_path(None, "../../nested/custom_name.png")
        cert_path = safe_certificate_upload_path(None, "..\\..\\nested\\report_name.pdf")
        self.assertNotIn("..", img_path)
        self.assertNotIn("custom_name", img_path)
        self.assertTrue(img_path.endswith(".png"))
        self.assertNotIn("..", cert_path)
        self.assertNotIn("report_name", cert_path)
        self.assertTrue(cert_path.endswith(".pdf"))
        