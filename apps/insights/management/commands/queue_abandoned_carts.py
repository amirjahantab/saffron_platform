from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from apps.orders.models import Cart
from apps.insights.models import Notification


class Command(BaseCommand):
    help = "Queue one consented reminder per idle active cart (no external delivery)."

    def handle(self, *args, **options):
        cutoff = timezone.now()-timedelta(hours=24)
        carts = Cart.objects.filter(status="active", user__communication_preferences__marketing=True, items__isnull=False).annotate(last_item=Max("items__updated_at")).filter(last_item__lt=cutoff).values_list("pk", flat=True)
        count = 0
        for pk in carts:
            with transaction.atomic():
                cart = Cart.objects.select_for_update().filter(pk=pk, status="active", user__communication_preferences__marketing=True).first()
                if cart and cart.items.exists():
                    _, created = Notification.objects.get_or_create(key=f"cart:{cart.pk}:reminder", defaults={"user_id": cart.user_id, "marketing": True, "message": "جهانتاب | سبد انتخاب‌های شما هنوز در حساب کاربری در دسترس است. قیمت و موجودی هنگام خرید دوباره بررسی می‌شود. لغو یادآوری در بخش ترجیحات حساب."})
                    count += int(created)
        self.stdout.write(f"Queued {count} reminder(s).")
