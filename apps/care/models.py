from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.core.models import TimeStampedModel, UUIDModel


class Ticket(TimeStampedModel, UUIDModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.CharField("موضوع", max_length=180)
    status = models.CharField("وضعیت", max_length=15, choices=[("open", "باز"), ("answered", "پاسخ داده شده"), ("closed", "بسته")], default="open")

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "درخواست پشتیبانی"
        verbose_name_plural = "درخواست‌های پشتیبانی"

    def clean(self):
        if self.order_id and self.order.user_id != self.user_id:
            raise ValidationError({"order": "سفارش متعلق به این حساب نیست."})

    def __str__(self):
        return self.subject


class Reply(TimeStampedModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField("متن", max_length=5000)
    is_internal = models.BooleanField("یادداشت داخلی", default=False)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "پاسخ پشتیبانی"
        verbose_name_plural = "پاسخ‌های پشتیبانی"


class Review(TimeStampedModel):
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField("امتیاز")
    title = models.CharField("عنوان", max_length=120)
    body = models.TextField("متن نظر", max_length=3000)
    is_approved = models.BooleanField("تأیید انتشار", default=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["product", "user"], name="one_review_per_customer_product"), models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="review_rating_1_to_5")]
        verbose_name = "نظر مشتری"
        verbose_name_plural = "نظرات مشتریان"

    @property
    def verified_purchase(self):
        return self.user.orders.filter(status__in=["paid", "processing", "shipped", "delivered"], items__variant__product_id=self.product_id).exists()

    def clean(self):
        if self.rating is None or not 1 <= self.rating <= 5:
            raise ValidationError({"rating": "امتیاز باید بین ۱ تا ۵ باشد."})
        if self.user_id and self.product_id and not self.verified_purchase:
            raise ValidationError("ثبت نظر تنها پس از خرید پرداخت‌شده این محصول ممکن است.")
