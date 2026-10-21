from pathlib import Path
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.core.models import DemoDataset
from apps.catalog.models import ProductImage
from apps.accounts.models import User
from apps.content.models import Article, Category, FAQ


class Command(BaseCommand):
    help = "Refresh demonstration imagery and editorial examples; forbidden outside DEMO_MODE."

    def handle(self, *args, **options):
        if not settings.DEMO_MODE:
            raise CommandError("Demo data is forbidden outside DEMO_MODE.")
        DemoDataset.objects.get_or_create(name="catalog")
        for index, image in enumerate(ProductImage.objects.filter(product__slug__in=["super-negin-export-qayenat", "negin-grade-one-torbat", "sargol-premium-ferdows", "pushal-authentic-birjand", "dokhtar-pich-traditional-gonabad"]).order_by("pk")):
            name = "demo-jar.webp" if index % 2 == 0 else "demo-box.webp"
            asset = Path(settings.BASE_DIR) / "static" / "images" / name
            if not asset.exists():
                raise CommandError("Build image assets first.")
            image.image.save(name, ContentFile(asset.read_bytes()), save=False)
            image.alt_text = "تصویر مفهومی بسته‌بندی؛ محصول محیط نمایشی"
            image.save()
        author = User.objects.filter(is_staff=True).first()
        if not author:
            author = User.objects.filter(phone_number="09000000000").first()
            if not author:
                author = User.objects.create_user("09000000000", full_name="تحریریه نمایشی جهانتاب", is_active=False)
        category, _ = Category.objects.get_or_create(slug="saffron-guide", defaults={"name": "راهنمای زعفران"})
        entries = [
            ("keeping-saffron", "رازِ نگهداری عطر زعفران", "با چند انتخاب ساده، از رنگ و عطر زعفران بهتر مراقبت کنیم.", "زعفران را در ظرف دربسته، دور از نور مستقیم، گرما و رطوبت نگهداری کنید.\nبرای مصرف روزمره فقط مقدار لازم را آماده کنید و باقی زعفران را در بسته اصلی و در شرایط درج‌شده روی آن نگه دارید.\nتاریخ برداشت و راهنمای نگهداری هر محصول را در صفحه مشخصات و روی بسته‌بندی بخوانید."),
            ("choosing-saffron", "از نگین تا سرگل؛ زبانِ رشته‌ها", "آشنایی با نام‌ها، اولین قدم برای انتخاب زعفران متناسب با مصرف شماست.", "نگین، سرگل، پوشال و دخترپیچ به شکل و ترکیب بخش‌های رشته اشاره می‌کنند. تنها از روی نام تجاری نمی‌توان درباره کیفیت یک محصول حکم قطعی داد.\nبرای مقایسه به وزن خالص، نوع بسته‌بندی، خاستگاه و اطلاعات آزمایشگاهی همان بچ مراجعه کنید.\nمقادیر آزمایشگاه را همراه واحد، تاریخ و مرجع بخوانید؛ هر ادعا باید به مدرک همان محصول متصل باشد."),
            ("saffron-gift", "هدیه‌ای کوچک، عطری ماندگار", "در انتخاب هدیه، جزئیات بسته‌بندی به اندازه انتخاب محصول اهمیت دارند.", "برای هدیه، وزن خالص زعفران و جنس ظرف را جداگانه بررسی کنید. وزن ظرف بخشی از وزن خالص زعفران نیست.\nبسته‌بندی مناسب هدیه، سلامت ظرف و اطلاعات قابل خواندن محصول، انتخاب شما را کامل‌تر می‌کند.\nپیش از ثبت سفارش، مشخصات گونه انتخاب‌شده و زمان‌بندی ارسال منتشرشده فروشگاه را بررسی کنید."),
        ]
        for slug, title, excerpt, body in entries:
            Article.objects.get_or_create(slug=slug, defaults={"title": title, "excerpt": excerpt, "body": body, "category": category, "author": author, "status": "published", "published_at": timezone.now()})
        FAQ.objects.get_or_create(question="تفاوت وزن خالص و وزن بسته‌بندی چیست؟", defaults={"answer": "وزن خالص، مقدار زعفران بدون وزن ظرف است. وزن ناخالص برای محاسبه ارسال شامل ظرف و محصول می‌شود.", "is_published": True})
        self.stdout.write("Design demonstration content prepared. No policies or contact facts fabricated.")
