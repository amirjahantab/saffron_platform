"""
Management command to populate the database with a rich, realistic Saffron catalog:
- 4 Packaging Types (Khatam, Crystal, Velvet Gift Box, Bulk Pack)
- 5 Harvest Batches covering all 5 Saffron Grades (Super Negin, Negin, Sargol, Pushal, Dokhtar Pich)
- Verified Laboratory Certificates (ISO 3632-2) with Crocin, Safranal, Picrocrocin, and Moisture metrics
- 5 Saffron Products with 11 diverse Variants (1g, 2g, 1 Mesghal 4.608g, 10g, 100g Wholesale)
- Auto-generated warm product images (via Pillow) and valid PDF lab certificates

Usage: python manage.py seed_demo_catalog
"""
import datetime
from decimal import Decimal
from io import BytesIO
from typing import Any
from PIL import Image, ImageDraw
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.catalog.models import (
    HarvestBatch,
    LabCertificate,
    LabTestMetric,
    PackagingType,
    Product,
    ProductImage,
    ProductVariant,
    SaffronGrade,
    SaleChannelType,
)


def _generate_product_image_bytes(bg_rgb: tuple[int, int, int], accent_rgb: tuple[int, int, int]) -> bytes:
    """Generate a clean, warm studio-like placeholder image using Pillow."""
    width, height = 800, 600
    img = Image.new("RGB", (width, height), color=bg_rgb)
    draw = ImageDraw.Draw(img)

    # Decorative golden border frame
    margin = 36
    draw.rectangle(
        [margin, margin, width - margin, height - margin],
        outline=accent_rgb,
        width=6,
    )
    # Inner saffron medallion circle
    cx, cy, r = width // 2, height // 2, 130
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent_rgb)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _generate_minimal_pdf_bytes(cert_number: str) -> bytes:
    return (
        f"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Certificate ({cert_number}) >>\nendobj\n%%EOF\n"
    ).encode("utf-8")


class Command(BaseCommand):
    help = "Seed the catalog with diverse saffron products, variants, batches, and lab certificates."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("Seeding diverse Saffron catalog data...")

        with transaction.atomic():
            # 1. Packaging Types
            pkg_khatam, _ = PackagingType.objects.update_or_create(
                slug="khatam-metal-royal",
                defaults={
                    "name": "خاتم فلزی سلطنتی",
                    "material": "فلزی لاک‌دار ضدزنگ",
                    "tare_weight_grams": Decimal("32.00"),
                    "is_gift_suitable": True,
                    "description": "ظرف فلزی با طرح خاتم‌کاری سنتی، مقاوم در برابر نور و رطوبت و مناسب هدیه.",
                    "is_active": True,
                },
            )
            pkg_crystal, _ = PackagingType.objects.update_or_create(
                slug="crystal-clear-export",
                defaults={
                    "name": "کریستال شفاف صادراتی",
                    "material": "پلی‌کربنات غذایی شفاف",
                    "tare_weight_grams": Decimal("16.50"),
                    "is_gift_suitable": False,
                    "description": "ظرف شفاف جهت مشاهده مستقیم درشتی و کیفیت کلاله‌های زعفران.",
                    "is_active": True,
                },
            )
            pkg_velvet, _ = PackagingType.objects.update_or_create(
                slug="velvet-gift-box",
                defaults={
                    "name": "جعبه مخمل کادویی",
                    "material": "چوب و روکش مخمل زرشکی",
                    "tare_weight_grams": Decimal("85.00"),
                    "is_gift_suitable": True,
                    "description": "پک نفیس مخملی ویژه سوغات و هدایای سازمانی.",
                    "is_active": True,
                },
            )
            pkg_bulk, _ = PackagingType.objects.update_or_create(
                slug="bulk-aluminum-pack",
                defaults={
                    "name": "پک متالایز عمده (فله بهداشتی)",
                    "material": "پاکت سه‌لایه آلومینیومی ضدنور",
                    "tare_weight_grams": Decimal("25.00"),
                    "is_gift_suitable": False,
                    "description": "بسته‌بندی استاندارد ویژه رستوران‌ها، بنکداران و صادرات عمده.",
                    "is_active": True,
                },
            )

            # 2. Harvest Batches & Verified Lab Certificates for all 5 Grades
            batches_config = [
                {
                    "code": "JHT-1405-SN-101",
                    "grade": SaffronGrade.SUPER_NEGIN,
                    "region": "قائنات - خراسان جنوبی",
                    "year": 1405,
                    "drying": "خشک‌کردن انجمادی (Freeze-Dried)",
                    "cert_no": "ISO-1405-SN901",
                    "crocin": Decimal("278.50"),
                    "safranal": Decimal("38.20"),
                    "picrocrocin": Decimal("96.40"),
                    "moisture": Decimal("7.80"),
                },
                {
                    "code": "JHT-1405-NG-102",
                    "grade": SaffronGrade.NEGIN,
                    "region": "تربت حیدریه - خراسان رضوی",
                    "year": 1405,
                    "drying": "خشک‌کردن سنتی بهینه",
                    "cert_no": "ISO-1405-NG902",
                    "crocin": Decimal("252.00"),
                    "safranal": Decimal("35.80"),
                    "picrocrocin": Decimal("91.00"),
                    "moisture": Decimal("8.40"),
                },
                {
                    "code": "JHT-1405-SG-103",
                    "grade": SaffronGrade.SARGOL,
                    "region": "فردوس - خراسان جنوبی",
                    "year": 1405,
                    "drying": "خشک‌کردن سنتی بهداشتی",
                    "cert_no": "ISO-1405-SG903",
                    "crocin": Decimal("236.00"),
                    "safranal": Decimal("34.10"),
                    "picrocrocin": Decimal("88.50"),
                    "moisture": Decimal("8.90"),
                },
                {
                    "code": "JHT-1405-PS-104",
                    "grade": SaffronGrade.PUSHAL,
                    "region": "بیرجند - خراسان جنوبی",
                    "year": 1405,
                    "drying": "خشک‌کردن سنتی",
                    "cert_no": "ISO-1405-PS904",
                    "crocin": Decimal("218.00"),
                    "safranal": Decimal("39.50"),
                    "picrocrocin": Decimal("85.00"),
                    "moisture": Decimal("9.20"),
                },
                {
                    "code": "JHT-1405-DP-105",
                    "grade": SaffronGrade.DOKHTAR_PICH,
                    "region": "گناباد - خراسان رضوی",
                    "year": 1405,
                    "drying": "خشک‌کردن سنتی رشته کامل",
                    "cert_no": "ISO-1405-DP905",
                    "crocin": Decimal("205.00"),
                    "safranal": Decimal("42.00"),
                    "picrocrocin": Decimal("84.00"),
                    "moisture": Decimal("9.50"),
                },
            ]

            batches_by_grade: dict[str, HarvestBatch] = {}
            for b_cfg in batches_config:
                batch, _ = HarvestBatch.objects.update_or_create(
                    batch_code=b_cfg["code"],
                    defaults={
                        "saffron_grade": b_cfg["grade"],
                        "origin_region": b_cfg["region"],
                        "harvest_year": b_cfg["year"],
                        "harvest_date": datetime.date(2026, 10, 10),
                        "drying_method": b_cfg["drying"],
                        "is_active": True,
                    },
                )
                batches_by_grade[b_cfg["grade"]] = batch

                cert, cert_created = LabCertificate.objects.get_or_create(
                    certificate_number=b_cfg["cert_no"],
                    defaults={
                        "harvest_batch": batch,
                        "lab_name": "آزمایشگاه مرجع کنترل کیفیت زعفران شرق (مشهد)",
                        "issue_date": datetime.date(2026, 10, 12),
                        "expiry_date": datetime.date(2028, 10, 12),
                        "standard_reference": "ISO 3632-2 / ISIRI 259-2",
                        "quality_grade_result": "درجه یک ممتاز (Grade I)",
                        "is_verified": True,
                    },
                )
                if cert_created or not cert.document_file:
                    cert.document_file.save(
                        f"{b_cfg['cert_no'].lower()}.pdf",
                        ContentFile(_generate_minimal_pdf_bytes(b_cfg["cert_no"])),
                        save=True,
                    )

                metrics_data = [
                    (
                        LabTestMetric.MetricType.CROCIN,
                        "کروسین (قدرت رنگ‌دهی در ۴۴۰ نانومتر)",
                        b_cfg["crocin"],
                        "A1% 1cm",
                        Decimal("200.00"),
                        None,
                    ),
                    (
                        LabTestMetric.MetricType.SAFRANAL,
                        "سافرانال (قدرت عطر در ۳۳۰ نانومتر)",
                        b_cfg["safranal"],
                        "A1% 1cm",
                        Decimal("20.00"),
                        Decimal("50.00"),
                    ),
                    (
                        LabTestMetric.MetricType.PICROCROCIN,
                        "پیکروکروسین (طعم و تلخی در ۲۵۷ نانومتر)",
                        b_cfg["picrocrocin"],
                        "A1% 1cm",
                        Decimal("70.00"),
                        None,
                    ),
                    (
                        LabTestMetric.MetricType.MOISTURE,
                        "درصد رطوبت و مواد فرار",
                        b_cfg["moisture"],
                        "درصد وزنی (%)",
                        None,
                        Decimal("12.00"),
                    ),
                ]
                for m_type, m_title, m_val, m_unit, m_min, m_max in metrics_data:
                    LabTestMetric.objects.update_or_create(
                        certificate=cert,
                        metric_type=m_type,
                        metric_title=m_title,
                        defaults={
                            "value": m_val,
                            "unit": m_unit,
                            "min_standard_limit": m_min,
                            "max_standard_limit": m_max,
                            "test_date": datetime.date(2026, 10, 12),
                            "reference_method": "ISO 3632-2",
                        },
                    )

            # 3. Products, Variants & Images
            products_spec = [
                {
                    "slug": "super-negin-export-qayenat",
                    "name": "زعفران سوپر نگین صادراتی قائنات",
                    "grade": SaffronGrade.SUPER_NEGIN,
                    "origin": "قائنات - خراسان جنوبی",
                    "short_desc": "کلاله‌های درشت تمام‌قرمز بدون هیچ‌گونه سفیدی با بالاترین قدرت رنگ‌دهی (کروسین ۲۷۸.۵).",
                    "desc": (
                        "زعفران سوپر نگین صادراتی جهانتاب از بهترین مزارع قائنات برداشت شده و به روش انجمادی "
                        "فرآوری شده است تا ساختار کلاله‌ها و عیار کروسین آن در بالاترین سطح استاندارد جهانی باقی بماند."
                    ),
                    "wholesale": True,
                    "featured": True,
                    "colors": ((136, 19, 55), (217, 119, 6)),
                    "variants": [
                        ("JHT-SN-CRYS-2G", pkg_crystal, Decimal("2.000"), "۲ گرم", SaleChannelType.RETAIL, 2_150_000, 1_950_000, 25),
                        ("JHT-SN-KHTM-1M", pkg_khatam, Decimal("4.608"), "۱ مثقال (۴.۶۰۸ گرم)", SaleChannelType.RETAIL, 4_800_000, 4_350_000, 18),
                        ("JHT-SN-VELV-2M", pkg_velvet, Decimal("9.216"), "۲ مثقال کادویی", SaleChannelType.RETAIL, 9_800_000, 8_900_000, 10),
                        ("JHT-SN-BULK-100G", pkg_bulk, Decimal("100.000"), "۱۰۰ گرم (عمده)", SaleChannelType.WHOLESALE, 92_000_000, 86_500_000, 8),
                    ],
                },
                {
                    "slug": "negin-grade-one-torbat",
                    "name": "زعفران نگین درجه یک تربت حیدریه",
                    "grade": SaffronGrade.NEGIN,
                    "origin": "تربت حیدریه",
                    "short_desc": "زعفران نگین خوش‌رنگ و معطر با کلاله‌های سالم و کشیده، انتخاب عالی برای مصرف خانگی و سوغات.",
                    "desc": (
                        "زعفران نگین تربت حیدریه دارای کلاله‌های سه‌شاخه یا جدا از هم بدون ریشه سفید است و تعادل فوق‌العاده‌ای "
                        "بین قدرت رنگ‌دهی و عطر طبیعی زعفران خراسان ایجاد می‌کند."
                    ),
                    "wholesale": True,
                    "featured": True,
                    "colors": ((159, 18, 57), (245, 158, 11)),
                    "variants": [
                        ("JHT-NG-CRYS-1M", pkg_crystal, Decimal("4.608"), "۱ مثقال (۴.۶۰۸ گرم)", SaleChannelType.RETAIL, 4_200_000, 3_850_000, 22),
                        ("JHT-NG-KHTM-10G", pkg_khatam, Decimal("10.000"), "۱۰ گرم", SaleChannelType.RETAIL, 8_900_000, None, 14),
                    ],
                },
                {
                    "slug": "sargol-premium-ferdows",
                    "name": "زعفران سرگل ممتاز فردوس",
                    "grade": SaffronGrade.SARGOL,
                    "origin": "فردوس - خراسان جنوبی",
                    "short_desc": "پرفروش‌ترین زعفران برای مصارف روزانه، دم‌نوش و آشپزی ایرانی با رنگ‌دهی سریع و قوی.",
                    "desc": (
                        "زعفران سرگل فردوس از سرریشه‌های خالص قرمز تشکیل شده و به دلیل آزادسازی سریع رنگ و عطر در آب جوش، "
                        "محبوب‌ترین گزینه برای آشپزی خانگی و زعفران‌دم‌کرده است."
                    ),
                    "wholesale": False,
                    "featured": True,
                    "colors": ((124, 45, 18), (217, 119, 6)),
                    "variants": [
                        ("JHT-SG-CRYS-1G", pkg_crystal, Decimal("1.000"), "۱ گرم", SaleChannelType.RETAIL, 950_000, 880_000, 40),
                        ("JHT-SG-KHTM-1M", pkg_khatam, Decimal("4.608"), "۱ مثقال (۴.۶۰۸ گرم)", SaleChannelType.RETAIL, 3_950_000, 3_600_000, 30),
                    ],
                },
                {
                    "slug": "pushal-authentic-birjand",
                    "name": "زعفران پوشال قلمدار بیرجند",
                    "grade": SaffronGrade.PUSHAL,
                    "origin": "بیرجند",
                    "short_desc": "کلاله قرمز به همراه ۱ تا ۲ میلی‌متر خامه زرد برای اطمینان ۱۰۰ درصدی از اصالت طبیعی.",
                    "desc": (
                        "در زعفران پوشال بیرجند، اتصال کلاله قرمز به بخش بسیار کوتاهی از خامه حفظ شده است که تقلب در آن را "
                        "غیرممکن می‌سازد و عطر ماندگاری به همراه دارد."
                    ),
                    "wholesale": True,
                    "featured": True,
                    "colors": ((113, 63, 18), (234, 179, 8)),
                    "variants": [
                        ("JHT-PS-CRYS-1M", pkg_crystal, Decimal("4.608"), "۱ مثقال (۴.۶۰۸ گرم)", SaleChannelType.RETAIL, 3_500_000, None, 20),
                        ("JHT-PS-BULK-50G", pkg_bulk, Decimal("50.000"), "۵۰ گرم (عمده)", SaleChannelType.WHOLESALE, 34_000_000, 31_500_000, 12),
                    ],
                },
                {
                    "slug": "dokhtar-pich-traditional-gonabad",
                    "name": "زعفران دخترپیچ سنتی گناباد",
                    "grade": SaffronGrade.DOKHTAR_PICH,
                    "origin": "گناباد - خراسان رضوی",
                    "short_desc": "رشته کامل زعفران شامل کلاله قرمز و ریشه سفید با بیشترین میزان سافرانال (عطر طبیعی).",
                    "desc": (
                        "زعفران دخترپیچ یا دسته، کامل‌ترین شکل سنتی زعفران است که بدون جدا کردن خامه از کلاله خشک می‌شود "
                        "و خواص دارویی و عطر کامل گیاه زعفران را در خود حفظ کرده است."
                    ),
                    "wholesale": False,
                    "featured": False,
                    "colors": ((87, 83, 78), (217, 119, 6)),
                    "variants": [
                        ("JHT-DP-KHTM-1M", pkg_khatam, Decimal("4.608"), "۱ مثقال (۴.۶۰۸ گرم)", SaleChannelType.RETAIL, 3_100_000, 2_850_000, 15),
                    ],
                },
            ]

            for p_spec in products_spec:
                product, _ = Product.objects.update_or_create(
                    slug=p_spec["slug"],
                    defaults={
                        "name": p_spec["name"],
                        "saffron_grade": p_spec["grade"],
                        "origin_summary": p_spec["origin"],
                        "short_description": p_spec["short_desc"],
                        "description": p_spec["desc"],
                        "is_wholesale_available": p_spec["wholesale"],
                        "is_featured": p_spec["featured"],
                        "is_active": True,
                    },
                )

                if not product.images.exists():
                    bg_color, accent_color = p_spec["colors"]
                    img_bytes = _generate_product_image_bytes(bg_color, accent_color)
                    prod_img = ProductImage(
                        product=product,
                        alt_text=p_spec["name"],
                        is_primary=True,
                        sort_order=0,
                    )
                    prod_img.image.save(f"{p_spec['slug']}.jpg", ContentFile(img_bytes), save=True)

                batch = batches_by_grade[p_spec["grade"]]
                for idx, (sku, pkg, weight_g, weight_lbl, s_type, base_rial, disc_rial, stock) in enumerate(
                    p_spec["variants"]
                ):
                    ProductVariant.objects.update_or_create(
                        sku=sku,
                        defaults={
                            "product": product,
                            "packaging_type": pkg,
                            "harvest_batch": batch,
                            "net_weight_grams": weight_g,
                            "weight_label": weight_lbl,
                            "sale_type": s_type,
                            "base_price_rial": base_rial,
                            "discounted_price_rial": disc_rial,
                            "stock_quantity": stock,
                            "min_order_quantity": 1,
                            "max_order_quantity": 20,
                            "is_active": True,
                            "sort_order": idx,
                        },
                    )

        self.stdout.write(
            self.style.SUCCESS(
                "[OK] Successfully seeded 4 packaging types, 5 harvest batches with lab certificates, 5 products, and 11 variants!"
            )
        )