"""Tests for SaffronGrade, PackagingType, HarvestBatch, LabCertificate, Product, and ProductVariant."""
import datetime
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from apps.catalog.models import (
    HarvestBatch,
    LabCertificate,
    LabTestMetric,
    PackagingType,
    Product,
    ProductVariant,
    SaffronGrade,
)


def create_minimal_valid_pdf(name: str = "cert.pdf") -> SimpleUploadedFile:
    content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    return SimpleUploadedFile(name, content, content_type="application/pdf")


class CatalogModelsAndPricingTests(TestCase):
    """Verify domain rules, Rial/Toman pricing contract, and harvest/lab integrity."""

    def setUp(self) -> None:
        self.packaging = PackagingType.objects.create(
            name="خاتم فلزی ممتاز",
            slug="khatam-metal-premium",
            material="فلزی گالوانیزه",
            tare_weight_grams=Decimal("35.50"),
            is_gift_suitable=True,
        )
        self.batch_super_negin = HarvestBatch.objects.create(
            batch_code="jht-1405-qay-01",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            origin_region="قائنات - خراسان جنوبی",
            harvest_year=1405,
        )
        self.batch_sargol = HarvestBatch.objects.create(
            batch_code="JHT-1405-TRB-02",
            saffron_grade=SaffronGrade.SARGOL,
            origin_region="تربت حیدریه",
            harvest_year=1405,
        )
        self.product = Product.objects.create(
            name="زعفران سوپر نگین صادراتی",
            slug="export-super-negin-saffron",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            short_description="زعفران سوپر نگین تمام‌قرمز با کروسین بالای ۲۷۰",
            description="توضیحات کامل زعفران سوپر نگین صادراتی برداشت قائنات.",
        )

    def test_all_five_required_saffron_grades_are_supported(self) -> None:
        expected = {"super_negin", "negin", "sargol", "pushal", "dokhtar_pich"}
        self.assertEqual(set(SaffronGrade.values), expected)

    def test_valid_variant_pricing_and_mesghal_weight_calculations(self) -> None:
        variant = ProductVariant(
            product=self.product,
            packaging_type=self.packaging,
            harvest_batch=self.batch_super_negin,
            sku="  sn-khatam-1m  ",
            net_weight_grams=Decimal("4.608"),  # 1 Mesghal
            weight_label="۱ مثقال (۴.۶۰۸ گرم)",
            base_price_rial=4_500_000,          # 450,000 Tomans
            discounted_price_rial=4_050_000,    # 405,000 Tomans (10% discount)
            stock_quantity=25,
        )
        variant.full_clean()
        variant.save()

        self.assertEqual(variant.sku, "SN-KHATAM-1M")
        self.assertTrue(variant.has_discount)
        self.assertEqual(variant.base_price_toman, 450_000)
        self.assertEqual(variant.discounted_price_toman, 405_000)
        self.assertEqual(variant.effective_price_rial, 4_050_000)
        self.assertEqual(variant.effective_price_toman, 405_000)
        self.assertEqual(variant.discount_percentage, 10)
        self.assertEqual(variant.formatted_effective_price_toman, "۴۰۵,۰۰۰ تومان")
        # Gross weight = 4.608 + 35.50 = 40.108g
        self.assertEqual(variant.gross_weight_grams, Decimal("40.108"))
        self.assertTrue(variant.is_in_stock)

    def test_non_multiple_of_ten_rial_price_is_rejected(self) -> None:
        variant = ProductVariant(
            product=self.product,
            packaging_type=self.packaging,
            harvest_batch=self.batch_super_negin,
            sku="SN-INVALID-RIAL",
            net_weight_grams=Decimal("1.000"),
            weight_label="۱ گرم",
            base_price_rial=1_000_005,  # Not divisible by 10
            stock_quantity=10,
        )
        with self.assertRaises(ValidationError) as ctx:
            variant.full_clean()
        self.assertIn("base_price_rial", ctx.exception.message_dict)

    def test_discounted_price_greater_or_equal_to_base_price_is_rejected(self) -> None:
        variant = ProductVariant(
            product=self.product,
            packaging_type=self.packaging,
            harvest_batch=self.batch_super_negin,
            sku="SN-BAD-DISCOUNT",
            net_weight_grams=Decimal("1.000"),
            weight_label="۱ گرم",
            base_price_rial=1_000_000,
            discounted_price_rial=1_000_000,  # Equal to base price -> invalid
            stock_quantity=10,
        )
        with self.assertRaises(ValidationError) as ctx:
            variant.full_clean()
        self.assertIn("discounted_price_rial", ctx.exception.message_dict)

    def test_mismatched_saffron_grade_between_product_and_batch_is_rejected(self) -> None:
        variant = ProductVariant(
            product=self.product,                # SUPER_NEGIN
            packaging_type=self.packaging,
            harvest_batch=self.batch_sargol,     # SARGOL -> mismatch!
            sku="SN-MISMATCH",
            net_weight_grams=Decimal("2.000"),
            weight_label="۲ گرم",
            base_price_rial=2_000_000,
            stock_quantity=5,
        )
        with self.assertRaises(ValidationError) as ctx:
            variant.full_clean()
        self.assertIn("harvest_batch", ctx.exception.message_dict)

    def test_lab_certificate_and_metrics_validation(self) -> None:
        cert = LabCertificate(
            harvest_batch=self.batch_super_negin,
            lab_name="آزمایشگاه مرجع استاندارد خراسان",
            certificate_number="iso-1405-9981",
            issue_date=datetime.date(2026, 10, 1),
            expiry_date=datetime.date(2027, 10, 1),
            document_file=create_minimal_valid_pdf(),
        )
        cert.full_clean()
        cert.save()
        self.assertEqual(cert.certificate_number, "ISO-1405-9981")

        metric = LabTestMetric(
            certificate=cert,
            metric_type=LabTestMetric.MetricType.CROCIN,
            metric_title="کروسین (قدرت رنگ‌دهی)",
            value=Decimal("275.40"),
            unit="A1% 1cm (440nm)",
            min_standard_limit=Decimal("200.00"),
            test_date=datetime.date(2026, 10, 1),
        )
        metric.full_clean()
        metric.save()
        self.assertEqual(cert.metrics.count(), 1)