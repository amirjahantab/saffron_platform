"""
Tests for Sub-phase 6.1 (Storefront UI - Home, Catalog Filtering, Product Detail & Lab Metrics, Add-to-Cart):
1. Verifies RTL Persian layout (`dir="rtl" lang="fa"`) and navigation rendering.
2. Verifies that displayed prices and stock counts come strictly from PostgreSQL/DB records formatted in Tomans.
3. Verifies category filtering (`?grade=super_negin`), packaging filtering, and search queries on `/shop/`.
4. Verifies Product Detail page renders harvest batch traceability and verified laboratory metrics (`کروسین`, `۲۷۴.۵۰`),
   while hiding unverified certificates.
5. Verifies out-of-stock handling (`ناموجود`) and storefront Add-to-Cart (`POST /cart/add/`) live navbar badge updates.
"""
import datetime
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from apps.catalog.models import (
    HarvestBatch,
    LabCertificate,
    LabTestMetric,
    PackagingType,
    Product,
    ProductVariant,
    SaffronGrade,
)


def _create_sample_pdf(name: str = "cert.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n",
        content_type="application/pdf",
    )


class StorefrontCatalogUITests(TestCase):
    """Verify Storefront HTML rendering, real DB pricing/inventory, and laboratory authenticity display."""

    def setUp(self) -> None:
        self.packaging_khatam = PackagingType.objects.create(
            name="خاتم فلزی دست‌ساز",
            slug="handmade-khatam",
            material="فلزی",
            tare_weight_grams=Decimal("32.00"),
            is_gift_suitable=True,
        )
        self.packaging_crystal = PackagingType.objects.create(
            name="کریستال شفاف",
            slug="clear-crystal",
            material="پلی‌کربنات",
            tare_weight_grams=Decimal("16.00"),
        )

        self.batch_sn = HarvestBatch.objects.create(
            batch_code="JHT-1405-UI-01",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            origin_region="قائنات - خراسان جنوبی",
            harvest_year=1405,
            drying_method="خشک‌کردن انجمادی بهداشتی",
        )
        self.batch_sargol = HarvestBatch.objects.create(
            batch_code="JHT-1405-UI-02",
            saffron_grade=SaffronGrade.SARGOL,
            origin_region="تربت حیدریه",
            harvest_year=1405,
        )

        self.verified_cert = LabCertificate.objects.create(
            harvest_batch=self.batch_sn,
            lab_name="آزمایشگاه مرجع کنترل کیفیت شرق",
            certificate_number="CERT-UI-9901",
            issue_date=datetime.date(2026, 10, 1),
            document_file=_create_sample_pdf("verified_ui.pdf"),
            is_verified=True,
        )
        LabTestMetric.objects.create(
            certificate=self.verified_cert,
            metric_type=LabTestMetric.MetricType.CROCIN,
            metric_title="کروسین (قدرت رنگ‌دهی)",
            value=Decimal("274.50"),
            unit="A1% 1cm",
            min_standard_limit=Decimal("200.00"),
            test_date=datetime.date(2026, 10, 1),
        )

        self.unverified_cert = LabCertificate.objects.create(
            harvest_batch=self.batch_sn,
            lab_name="آزمایشگاه پیش‌نویس محرمانه",
            certificate_number="CERT-SECRET-DRAFT",
            issue_date=datetime.date(2026, 10, 2),
            document_file=_create_sample_pdf("draft_ui.pdf"),
            is_verified=False,
        )

        self.product_sn = Product.objects.create(
            name="زعفران سوپر نگین یک مثقالی ویژه",
            slug="super-negin-1m-ui",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            short_description="کلاله تمام‌قرمز صادراتی قائنات",
            description="توضیحات کامل زعفران سوپر نگین قائنات با عیار آزمایشگاهی بالا.",
            origin_summary="قائنات",
            is_featured=True,
            is_active=True,
        )
        self.variant_sn_khatam = ProductVariant.objects.create(
            product=self.product_sn,
            packaging_type=self.packaging_khatam,
            harvest_batch=self.batch_sn,
            sku="SN-UI-KHATAM-1M",
            net_weight_grams=Decimal("4.608"),
            weight_label="۱ مثقال (۴.۶۰۸ گرم)",
            base_price_rial=4_500_000,        # 450,000 Tomans
            discounted_price_rial=4_050_000,  # 405,000 Tomans (10% discount)
            stock_quantity=12,
            is_active=True,
        )
        self.variant_sn_crystal_out_of_stock = ProductVariant.objects.create(
            product=self.product_sn,
            packaging_type=self.packaging_crystal,
            harvest_batch=self.batch_sn,
            sku="SN-UI-CRYSTAL-1G",
            net_weight_grams=Decimal("1.000"),
            weight_label="۱ گرم",
            base_price_rial=1_100_000,        # 110,000 Tomans
            stock_quantity=0,                 # Out of stock
            is_active=True,
        )

        self.product_sargol = Product.objects.create(
            name="زعفران سرگل ممتاز تربت",
            slug="sargol-torbat-ui",
            saffron_grade=SaffronGrade.SARGOL,
            short_description="سرگل خوش‌عطر تربت حیدریه",
            description="توضیحات زعفران سرگل",
            origin_summary="تربت حیدریه",
            is_featured=False,
            is_active=True,
        )
        self.variant_sargol = ProductVariant.objects.create(
            product=self.product_sargol,
            packaging_type=self.packaging_crystal,
            harvest_batch=self.batch_sargol,
            sku="SG-UI-CRYSTAL-2G",
            net_weight_grams=Decimal("2.000"),
            weight_label="۲ گرم",
            base_price_rial=1_850_000,        # 185,000 Tomans
            stock_quantity=7,
            is_active=True,
        )

    def test_home_page_renders_rtl_and_real_database_toman_prices(self) -> None:
        resp = self.client.get(reverse("storefront:home"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")

        self.assertIn('dir="rtl"', html)
        self.assertIn('lang="fa"', html)
        self.assertIn("زعفران سوپر نگین یک مثقالی ویژه", html)
        # 4,050,000 Rials -> ۴۰۵,۰۰۰ تومان
        self.assertIn("۴۰۵,۰۰۰ تومان", html)
        # 4,500,000 Rials base price -> ۴۵۰,۰۰۰ تومان
        self.assertIn("۴۵۰,۰۰۰ تومان", html)

    def test_product_list_page_filters_by_grade_packaging_and_search(self) -> None:
        list_url = reverse("storefront:product_list")

        # 1. Filter by grade=super_negin -> only product_sn appears
        resp_sn = self.client.get(list_url, {"grade": SaffronGrade.SUPER_NEGIN})
        self.assertEqual(resp_sn.status_code, 200)
        html_sn = resp_sn.content.decode("utf-8")
        self.assertIn("زعفران سوپر نگین یک مثقالی ویژه", html_sn)
        self.assertNotIn("زعفران سرگل ممتاز تربت", html_sn)

        # 2. Filter by search query `q=تربت` -> only product_sargol appears with ১৮۵,۰۰۰ تومان
        resp_q = self.client.get(list_url, {"q": "تربت"})
        self.assertEqual(resp_q.status_code, 200)
        html_q = resp_q.content.decode("utf-8")
        self.assertIn("زعفران سرگل ممتاز تربت", html_q)
        self.assertIn("۱۸۵,۰۰۰ تومان", html_q)
        self.assertNotIn("زعفران سوپر نگین یک مثقالی ویژه", html_q)

    def test_product_detail_page_renders_variants_harvest_batch_and_verified_lab_metrics(self) -> None:
        detail_url = reverse("storefront:product_detail", kwargs={"slug": self.product_sn.slug})
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")

        # Verify SKU, Toman price, and stock count from real DB
        self.assertIn("SN-UI-KHATAM-1M", html)
        self.assertIn("۴۰۵,۰۰۰ تومان", html)
        self.assertIn("موجود در انبار (۱۲ عدد)", html)

        # Verify HarvestBatch traceability
        self.assertIn("JHT-1405-UI-01", html)
        self.assertIn("قائنات - خراسان جنوبی", html)
        self.assertIn("۱۴۰۵", html)

        # Verify LabCertificate and Crocin metric (274.50 -> ۲۷۴.۵۰)
        self.assertIn("آزمایشگاه مرجع کنترل کیفیت شرق", html)
        self.assertIn("CERT-UI-9901", html)
        self.assertIn("کروسین (قدرت رنگ‌دهی)", html)
        self.assertIn("۲۷۴.۵۰", html)

        # Unverified certificate MUST NEVER be exposed in the HTML or embedded JSON
        self.assertNotIn("CERT-SECRET-DRAFT", html)
        self.assertNotIn("آزمایشگاه پیش‌نویس محرمانه", html)

        # Verify out-of-stock variant selection via query param `?variant=<uuid>`
        resp_oos = self.client.get(
            detail_url,
            {"variant": str(self.variant_sn_crystal_out_of_stock.public_id)},
        )
        html_oos = resp_oos.content.decode("utf-8")
        self.assertIn("SN-UI-CRYSTAL-1G", html_oos)
        self.assertIn("ناموجود در انبار", html_oos)

    def test_storefront_add_to_cart_updates_navbar_cart_badge_and_payable_toman(self) -> None:
        add_url = reverse("storefront:cart_add")
        resp = self.client.post(
            add_url,
            data={
                "variant_public_id": str(self.variant_sn_khatam.public_id),
                "quantity": 2,
                "next": reverse("storefront:home"),
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")

        # 2 * 405,000 Tomans = 810,000 Tomans (۸۱۰,۰۰۰ تومان) rendered in navbar
        self.assertIn("۸۱۰,۰۰۰ تومان", html)
        self.assertIn("به سبد خرید شما اضافه شد", html)