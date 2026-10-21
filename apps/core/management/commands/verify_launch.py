from urllib.parse import urlsplit
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from apps.core.models import DemoDataset
from apps.catalog.models import ProductVariant
from apps.content.models import PolicyPage, StoreProfile


class Command(BaseCommand):
    help = "Fail closed on unsafe live-launch configuration, missing business facts or demo data."

    def handle(self, *args, **options):
        issues = []
        if settings.DEBUG or settings.DEMO_MODE:
            issues.append("DEBUG and DEMO_MODE must be false")
        if DemoDataset.objects.exists():
            issues.append("Database contains demo seed markers; use a fresh production database")
        if not settings.SITE_URL.startswith("https://") or urlsplit(settings.SITE_URL).hostname in {"localhost", "127.0.0.1", "shop.example.com", "saffron.example"}:
            issues.append("Configure the real public HTTPS origin")
        if settings.PAYMENT_DEFAULT_GATEWAY != "zarinpal" or settings.ZARINPAL_SANDBOX or "replace" in settings.ZARINPAL_MERCHANT_ID or settings.ZARINPAL_MERCHANT_ID == "00000000-0000-0000-0000-000000000000":
            issues.append("Configure live payment merchant credentials")
        if "Sandbox" in settings.SMS_PROVIDER_CLASS or not settings.KAVENEGAR_API_KEY or not settings.KAVENEGAR_OTP_TEMPLATE:
            issues.append("Configure and test the live SMS provider")
        published = set(PolicyPage.objects.filter(is_published=True).values_list("slug", flat=True))
        missing = {"contact", "terms", "shipping", "returns", "privacy"} - published
        if missing:
            issues.append("Publish actual business policies: " + ", ".join(sorted(missing)))
        profile = StoreProfile.objects.first()
        if not profile or not profile.phone or not profile.address:
            issues.append("Enter actual store contact phone and address")
        if not ProductVariant.objects.filter(is_active=True, product__is_active=True, packaging_type__is_active=True, harvest_batch__is_active=True, stock_quantity__gt=0).exists():
            issues.append("Load actual sellable product inventory")
        if settings.ASSISTANT_ENABLED and (not settings.OPENAI_API_KEY or not settings.OPENAI_MODEL):
            issues.append("Configure assistant key and model or disable assistant")
        if issues:
            raise CommandError("Live launch is blocked:\n- " + "\n- ".join(issues))
        call_command("verify_infrastructure")
        self.stdout.write(self.style.SUCCESS("Launch configuration and content checks passed. Verify provider transactions, TLS and restore rehearsal separately."))
