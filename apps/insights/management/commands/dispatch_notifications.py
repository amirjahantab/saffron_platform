from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.insights.models import Notification, Preference
from apps.accounts.services.sms_provider import get_sms_provider, SMSDeliveryError


class Command(BaseCommand):
    help = "Deliver queued notifications; disabled unless NOTIFICATIONS_ENABLED=True."

    def handle(self, *args, **options):
        if not settings.NOTIFICATIONS_ENABLED:
            raise CommandError("Notifications are disabled; no messages sent.")
        from apps.orders.models import Cart
        count = 0
        for pk in Notification.objects.filter(status__in=["pending", "failed"], attempts__lt=3).order_by("created_at").values_list("pk", flat=True)[:100]:
            with transaction.atomic():
                item = Notification.objects.select_for_update(of=("self",)).select_related("user").get(pk=pk)
                if item.status not in {"pending", "failed"} or item.attempts >= 3:
                    continue
                if item.marketing:
                    cart_pk = item.key.split(":")[1]
                    eligible = Preference.objects.filter(user=item.user, marketing=True).exists() and Cart.objects.filter(pk=cart_pk, user=item.user, status="active", items__isnull=False).exists()
                    if not eligible:
                        item.status = "cancelled"
                        item.save(update_fields=["status", "updated_at"])
                        continue
                item.attempts += 1
                try:
                    phone = item.recipient_phone or (item.user.phone_number if item.user else "")
                    sent = bool(phone) and get_sms_provider().send_message(phone, item.message)
                except (SMSDeliveryError, OSError):
                    sent = False
                item.status = "sent" if sent else "failed"
                item.delivered_at = timezone.now() if sent else None
                item.save(update_fields=["status", "attempts", "delivered_at", "updated_at"])
                count += int(sent)
        self.stdout.write(f"Delivered {count} notification(s).")
