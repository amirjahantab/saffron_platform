"""
Management command to verify database, cache, and currency contract readiness.
Usage: python manage.py verify_infrastructure
"""
from typing import Any
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apps.core.currency import format_price_toman, rial_to_toman, toman_to_rial
from apps.core.views import check_cache_health, check_database_health


class Command(BaseCommand):
    help = "Verify connectivity to PostgreSQL, Redis, and validate base platform contracts."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("Starting Phase 1 infrastructure verification...")

        # 1. Verify Database Connectivity
        db_engine = settings.DATABASES["default"]["ENGINE"]
        db_ok, db_detail = check_database_health()
        if not db_ok:
            raise CommandError(f"[FAIL] Database connection check failed ({db_engine}): {db_detail}")
        self.stdout.write(self.style.SUCCESS(f"[OK] Database connection verified ({db_engine})."))

        # 2. Verify Cache / Redis Connectivity
        cache_backend = settings.CACHES["default"]["BACKEND"]
        cache_ok, cache_detail = check_cache_health()
        if not cache_ok:
            raise CommandError(f"[FAIL] Cache connection check failed ({cache_backend}): {cache_detail}")
        self.stdout.write(self.style.SUCCESS(f"[OK] Cache connection verified ({cache_backend})."))

        # 3. Verify Currency Contract Self-Test
        sample_toman = 250_000
        sample_rial = toman_to_rial(sample_toman)
        if sample_rial != 2_500_000 or rial_to_toman(sample_rial) != sample_toman:
            raise CommandError("[FAIL] Currency conversion self-test failed.")
        formatted = format_price_toman(sample_rial)
        self.stdout.write(self.style.SUCCESS(f"[OK] Currency contract verified (Sample: {formatted})."))

        self.stdout.write(self.style.SUCCESS("All Phase 1 infrastructure checks passed successfully."))