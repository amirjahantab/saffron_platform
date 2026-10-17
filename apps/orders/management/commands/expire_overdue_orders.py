"""
Management command to sweep and expire overdue `PENDING_PAYMENT` orders
and atomically release their reserved stock back to the catalog.
Usage: python manage.py expire_overdue_orders
"""
from typing import Any
from django.core.management.base import BaseCommand
from apps.orders.services.reservation_service import OrderStateAndReservationService


class Command(BaseCommand):
    help = "Expire overdue PENDING_PAYMENT orders and release their active stock reservations."

    def handle(self, *args: Any, **options: Any) -> None:
        expired_count = OrderStateAndReservationService.expire_overdue_reservations()
        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] Swept overdue reservations: {expired_count} order(s) expired and stock restored."
            )
        )