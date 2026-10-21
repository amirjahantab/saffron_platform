from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.orders.models import Order
from .models import Event, Notification, OrderAttribution


@receiver(post_save, sender=Order, dispatch_uid="insights_order_lifecycle")
def order_lifecycle(sender, instance, raw=False, **kwargs):
    if raw:
        return
    # In the payment transaction: rollback also removes the event and outbox row.
    if instance.paid_at:
        attribution = OrderAttribution.objects.filter(order=instance).first()
        defaults = {"visitor": attribution.visitor, "source": attribution.source, "campaign": attribution.campaign} if attribution else {}
        Event.objects.get_or_create(kind="purchase", order=instance, defaults=defaults)
    if instance.status in {"paid", "shipped", "delivered", "cancelled", "refunded"}:
        Notification.objects.get_or_create(key=f"order:{instance.pk}:{instance.status}", defaults={
            "user_id": instance.user_id, "order": instance, "recipient_phone": instance.recipient_phone,
            "message": f"جهانتاب | سفارش {instance.order_number}: {instance.get_status_display()}. جزئیات در حساب کاربری شما در دسترس است.",
        })
