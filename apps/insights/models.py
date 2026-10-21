from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel


class Preference(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="communication_preferences")
    analytics = models.BooleanField(default=False, verbose_name="اجازه تحلیل رفتار")
    marketing = models.BooleanField(default=False, verbose_name="اجازه یادآوری سبد")

    class Meta:
        verbose_name = "رضایت ارتباطی"
        verbose_name_plural = "رضایت‌های ارتباطی"


class Event(models.Model):
    KINDS = [(s, label) for s, label in [("product_view", "مشاهده محصول"), ("search", "جست‌وجو"), ("add_to_cart", "افزودن به سبد"), ("checkout", "آغاز پرداخت"), ("purchase", "خرید موفق")]]
    kind = models.CharField(max_length=20, choices=KINDS, db_index=True)
    visitor = models.CharField(max_length=64, blank=True, db_index=True)
    product = models.ForeignKey("catalog.Product", on_delete=models.SET_NULL, null=True, blank=True)
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(max_length=64, blank=True)
    campaign = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["order"], condition=models.Q(kind="purchase"), name="single_purchase_event_per_order")]
        verbose_name = "رویداد فروشگاه"
        verbose_name_plural = "رویدادهای فروشگاه"


class Notification(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    recipient_phone = models.CharField(max_length=11, blank=True)
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, null=True, blank=True)
    key = models.CharField(max_length=180, unique=True)
    message = models.CharField(max_length=500)
    marketing = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=[("pending", "در صف"), ("sent", "ارسال‌شده"), ("failed", "ناموفق"), ("cancelled", "لغوشده")], default="pending", db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "پیام خروجی"
        verbose_name_plural = "پیام‌های خروجی"


class OrderAttribution(models.Model):
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE)
    visitor = models.CharField(max_length=64)
    source = models.CharField(max_length=64, blank=True)
    campaign = models.CharField(max_length=64, blank=True)
