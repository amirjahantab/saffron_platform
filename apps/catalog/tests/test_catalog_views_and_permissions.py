"""Tests for public catalog views, inactive item filtering, and admin access control."""
import datetime
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from apps.accounts.models import User
from apps.catalog.models import (
    HarvestBatch,
    LabCertificate,
    LabTestMetric,
    PackagingType,
    Product,
    ProductVariant,
    SaffronGrade,
)
from apps.catalog.tests.test_models_and_pricing import create_minimal_valid_pdf


class CatalogViewsAndPermissionsTests(TestCase):
    """Verify real database responses on catalog endpoints and strict admin access control."""

    def setUp(self) -> None:
        self.packaging = PackagingType.objects.create(
            name="کریستال شفاف",
            slug="crystal-clear",
            material="پلی‌کربنات غذایی",
            tare_weight_grams=Decimal("18.00"),
        )
        self.batch = HarvestBatch.objects.create(
            batch_code="JHT-1405-001",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            origin_region="قائنات",
            harvest_year=1405,
        )
        self.verified_cert = LabCertificate.objects.create(
            harvest_batch=self.batch,
            lab_name="آزمایشگاه کنترل کیفیت توس",
            certificate_number="CERT-1405-VERIFIED",
            issue_date=datetime.date(2026, 9, 15),
            document_file=create_minimal_valid_pdf("verified.pdf"),
            is_verified=True,
        )
        LabTestMetric.objects.create(
            certificate=self.verified_cert,
            metric_type=LabTestMetric.MetricType.CROCIN,
            metric_title="کروسین",
            value=Decimal("268.00"),
            unit="A1% 1cm",
            min_standard_limit=Decimal("200.00"),
            test_date=datetime.date(2026, 9, 15),
        )
        self.unverified_cert = LabCertificate.objects.create(
            harvest_batch=self.batch,
            lab_name="آزمایشگاه داخلی",
            certificate_number="CERT-1405-DRAFT",
            issue_date=datetime.date(2026, 9, 16),
            document_file=create_minimal_valid_pdf("draft.pdf"),
            is_verified=False,
        )

        self.active_product = Product.objects.create(
            name="زعفران سوپر نگین یک مثقالی",
            slug="super-negin-1-mesghal",
            saffron_grade=SaffronGrade.SUPER_NEGIN,
            short_description="زعفران سوپر نگین خالص",
            description="توضیح کامل زعفران سوپر نگین.",
            is_active=True,
        )
        self.inactive_product = Product.objects.create(
            name="محصول غیرفعال آزمایشی",
            slug="inactive-test-product",
            saffron_grade=SaffronGrade.SARGOL,
            short_description="نباید نمایش داده شود",
            description="غیرفعال",
            is_active=False,
        )

        self.active_variant = ProductVariant.objects.create(
            product=self.active_product,
            packaging_type=self.packaging,
            harvest_batch=self.batch,
            sku="SN-CRYSTAL-1M",
            net_weight_grams=Decimal("4.608"),
            weight_label="۱ مثقال",
            base_price_rial=4_200_000,
            discounted_price_rial=3_900_000,
            stock_quantity=15,
            is_active=True,
        )
        self.inactive_variant = ProductVariant.objects.create(
            product=self.active_product,
            packaging_type=self.packaging,
            harvest_batch=self.batch,
            sku="SN-CRYSTAL-HIDDEN",
            net_weight_grams=Decimal("10.000"),
            weight_label="۱۰ گرم",
            base_price_rial=9_000_000,
            stock_quantity=5,
            is_active=False,
        )

    def test_product_list_returns_only_active_products_with_real_db_pricing(self) -> None:
        url = reverse("catalog:product_list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["count"], 1)
        prod = data["products"][0]
        self.assertEqual(prod["slug"], "super-negin-1-mesghal")
        self.assertEqual(prod["starting_price"]["amount_rial"], 3_900_000)
        self.assertEqual(prod["starting_price"]["amount_toman"], 390_000)
        self.assertEqual(prod["available_variants_count"], 1)

    def test_product_detail_returns_active_variants_and_only_verified_certificates(self) -> None:
        url = reverse("catalog:product_detail", kwargs={"slug": self.active_product.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        prod = resp.json()["product"]

        self.assertEqual(len(prod["variants"]), 1)
        variant_data = prod["variants"][0]
        self.assertEqual(variant_data["sku"], "SN-CRYSTAL-1M")
        self.assertEqual(variant_data["pricing"]["effective_price_toman"], 390_000)

        certs = variant_data["harvest_batch"]["certificates"]
        self.assertEqual(len(certs), 1)
        self.assertEqual(certs[0]["certificate_number"], "CERT-1405-VERIFIED")
        self.assertEqual(len(certs[0]["metrics"]), 1)
        self.assertEqual(certs[0]["metrics"][0]["value"], "268.00")

    def test_inactive_product_detail_returns_404(self) -> None:
        url = reverse("catalog:product_detail", kwargs={"slug": self.inactive_product.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_regular_customer_cannot_access_catalog_admin(self) -> None:
        customer = User.objects.create_user(phone_number="09125556677")
        self.client.force_login(customer)

        admin_url = reverse("admin:catalog_product_changelist")
        resp = self.client.get(admin_url)
        # Non-staff user is redirected to admin login (302)
        self.assertEqual(resp.status_code, 302)

    def test_staff_superuser_can_access_catalog_admin(self) -> None:
        admin_user = User.objects.create_superuser(
            phone_number="09125556688",
            password="StrongAdminPassword!2026",
        )
        self.client.force_login(admin_user)

        admin_url = reverse("admin:catalog_product_changelist")
        resp = self.client.get(admin_url)
        self.assertEqual(resp.status_code, 200)