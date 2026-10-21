from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from apps.catalog.validators import validate_product_image, safe_product_image_upload_path
from apps.core.models import TimeStampedModel


class Category(models.Model):
    name = models.CharField("نام", max_length=100)
    slug = models.SlugField("نامک", unique=True, allow_unicode=True)

    class Meta:
        verbose_name = "دسته مقاله"
        verbose_name_plural = "دسته‌های مقاله"

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField("نام", max_length=60)
    slug = models.SlugField("نامک", unique=True, allow_unicode=True)

    def __str__(self):
        return self.name


class ArticleQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status="published", published_at__lte=timezone.now())


class Article(TimeStampedModel):
    title = models.CharField("عنوان", max_length=180)
    slug = models.SlugField("نامک", unique=True, max_length=200, allow_unicode=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name="دسته")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="نویسنده")
    tags = models.ManyToManyField(Tag, blank=True, verbose_name="برچسب‌ها")
    excerpt = models.CharField("چکیده", max_length=350)
    body = models.TextField("متن مقاله", help_text="متن ساده؛ هر پاراگراف را در خط جدا بنویسید. HTML اجرا نمی‌شود.")
    cover = models.ImageField("تصویر", upload_to=safe_product_image_upload_path, validators=[validate_product_image], blank=True)
    cover_alt = models.CharField("توضیح تصویر", max_length=180, blank=True)
    meta_title = models.CharField("عنوان سئو", max_length=180, blank=True)
    meta_description = models.CharField("توضیح سئو", max_length=300, blank=True)
    status = models.CharField("وضعیت", max_length=12, choices=[("draft", "پیش‌نویس"), ("published", "منتشرشده")], default="draft")
    published_at = models.DateTimeField("تاریخ انتشار", null=True, blank=True)
    products = models.ManyToManyField("catalog.Product", blank=True, related_name="articles", verbose_name="محصولات مرتبط")
    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-pk"]
        verbose_name = "مقاله"
        verbose_name_plural = "مقالات"

    def __str__(self):
        return self.title

    def clean(self):
        if self.status == "published" and not self.published_at:
            raise ValidationError({"published_at": "زمان انتشار را مشخص کنید."})
        if ArticleRedirect.objects.filter(old_slug=self.slug).exclude(article_id=self.pk).exists():
            raise ValidationError({"slug": "این نامک برای تغییر مسیر مقاله دیگری رزرو شده است."})

    @transaction.atomic
    def save(self, *args, **kwargs):
        old = type(self).objects.select_for_update().filter(pk=self.pk).values_list("slug", flat=True).first() if self.pk else None
        self.full_clean()
        super().save(*args, **kwargs)
        if old and old != self.slug:
            ArticleRedirect.objects.filter(old_slug=self.slug, article=self).delete()
            ArticleRedirect.objects.update_or_create(old_slug=old, defaults={"article": self})

    def get_absolute_url(self):
        return reverse("content:article", args=[self.slug])


class ArticleRedirect(models.Model):
    old_slug = models.SlugField(unique=True, max_length=200, allow_unicode=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE)


class PolicyPage(TimeStampedModel):
    SLUGS = [("about", "درباره جهانتاب"), ("contact", "تماس با ما"), ("terms", "قوانین خرید"), ("shipping", "ارسال سفارش"), ("returns", "بازگشت کالا"), ("privacy", "حریم خصوصی")]
    slug = models.SlugField("صفحه", unique=True, choices=SLUGS)
    title = models.CharField("عنوان", max_length=150)
    body = models.TextField("متن")
    is_published = models.BooleanField("انتشار", default=False)

    class Meta:
        verbose_name = "صفحه اطلاعات فروشگاه"
        verbose_name_plural = "صفحات اطلاعات فروشگاه"

    def __str__(self):
        return self.title


class FAQ(models.Model):
    question = models.CharField("پرسش", max_length=250)
    answer = models.TextField("پاسخ")
    is_published = models.BooleanField("انتشار", default=False)
    position = models.PositiveSmallIntegerField("ترتیب", default=0)

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = "پرسش متداول"
        verbose_name_plural = "پرسش‌های متداول"

    def __str__(self):
        return self.question


class StoreProfile(models.Model):
    name = models.CharField("نام فروشگاه", max_length=120, default="زعفران جهانتاب")
    phone = models.CharField("تلفن تماس عمومی", max_length=25, blank=True)
    email = models.EmailField("ایمیل عمومی", blank=True)
    address = models.TextField("نشانی عمومی", blank=True)
    hours = models.CharField("ساعات پاسخگویی", max_length=120, blank=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    class Meta:
        verbose_name = "اطلاعات تماس فروشگاه"
        verbose_name_plural = "اطلاعات تماس فروشگاه"

    def __str__(self):
        return self.name
