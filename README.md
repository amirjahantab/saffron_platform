# فروشگاه زعفران جهانتاب

فروشگاه ماژولار Django با PostgreSQL، Redis، رابط فارسی راست‌چین، کاتالوگ، خرید
مهمان و حساب کاربری، پرداخت، مجله، پشتیبانی، گزارش فروش و دستیار اختیاری.
فونت متغیر وزیرمتن به‌صورت محلی و با مجوز OFL ارائه می‌شود.

- [گزارش تکمیل و وضعیت پذیرش](docs/COMPLETION.md)
- [راهنمای مدیریت فارسی](docs/STORE_ADMIN.md)
- [استقرار، پشتیبان‌گیری، بازیابی و rollback](docs/OPERATIONS.md)
- [منشأ تصاویر و مجوز فونت](docs/ASSET_PROVENANCE.md)
- [گزارش تاریخی فاز ۷](docs/PHASE7.md)

## اجرای محلی در Windows PowerShell

پیش‌نیازها: Python 3.12، Node.js 20+، Docker Desktop با Linux containers.
فرمان‌ها را از پوشه پروژه اجرا کنید. فایل محیطی موجود را بازنویسی نکنید.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements/development.txt
if (!(Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

در `.env`، کلید Django و رمز دیتابیس را مستقل و تصادفی انتخاب کنید. برای ساخت
یک مقدار محلی می‌توانید `python -c "import secrets; print(secrets.token_urlsafe(48))"`
را اجرا کنید. کلیدها نباید وارد مخزن یا چت شوند. تنظیمات سرویس‌های محلی:

```dotenv
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=55432
REDIS_URL=redis://127.0.0.1:56379/1
SITE_URL=http://127.0.0.1:8765
PAYMENT_CALLBACK_BASE_URL=http://127.0.0.1:8765
DEMO_MODE=True
```

```powershell
docker compose -p jahantab-verify -f compose.verify.yml up -d --wait
.\.venv\Scripts\python.exe -X utf8 manage.py migrate --noinput
.\.venv\Scripts\python.exe -X utf8 manage.py verify_infrastructure
npm.cmd ci --ignore-scripts
npm.cmd run build:css
# فقط روی دیتابیس دمو بدون سفارش؛ موجودی دیتابیس دارای سفارش بازنویسی نمی‌شود:
.\.venv\Scripts\python.exe -X utf8 manage.py seed_demo_catalog
.\.venv\Scripts\python.exe -X utf8 manage.py seed_design_demo
.\.venv\Scripts\python.exe -X utf8 manage.py optimize_catalog_images
.\.venv\Scripts\python.exe -X utf8 manage.py createsuperuser
.\.venv\Scripts\python.exe -X utf8 manage.py runserver 127.0.0.1:8765
```

فروشگاه: <http://127.0.0.1:8765/> و پنل مدیریت: <http://127.0.0.1:8765/admin/>.
دیتابیس محلی این محیط قبلاً آماده و داده دمو وارد شده است؛ seed را دوباره اجرا
نکنید. سرویس‌های `compose.verify.yml` فقط به localhost متصل‌اند و دیتابیس آن‌ها
موقتی است؛ توقف یا بازسازی کانتینر می‌تواند داده دمو را از بین ببرد. برای داده
پایدار از پیکربندی استقرار و حجم‌های مجزا استفاده کنید.

ورود OTP واقعی به تنظیم سرویس پیامک نیاز دارد. پیامک آزمایشی هیچ کدی در log
نمایش نمی‌دهد؛ تست‌های خودکار از outbox حافظه‌ای استفاده می‌کنند. برای مرور محلی
مسیر کامل خرید بدون پیامک، خرید مهمان و پرداخت Sandbox در دسترس است. هیچ حساب
مدیر یا رمز ثابت ساخته نشده است؛ `createsuperuser` رمز دلخواه خودتان را می‌گیرد.

## تست و ساخت

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py check
.\.venv\Scripts\python.exe -X utf8 manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -X utf8 manage.py migrate --check
.\.venv\Scripts\python.exe -X utf8 manage.py test apps --settings=config.settings.test --noinput
$env:USE_EXTERNAL_TEST_SERVICES='True'
.\.venv\Scripts\python.exe -X utf8 manage.py test apps --settings=config.settings.test --noinput
Remove-Item Env:USE_EXTERNAL_TEST_SERVICES
npm.cmd run build:css
npm.cmd run test:browser
.\.venv\Scripts\python.exe -m pip_audit -r requirements/production.txt
npm.cmd audit
```

مرورگرهای تست روی پورت **8766** اجرا می‌شوند تا با پیش‌نمایش 8765 تداخل نکنند.
Chrome نصب‌شده به‌صورت پیش‌فرض استفاده می‌شود؛ برای Edge متغیر
`PLAYWRIGHT_CHANNEL=msedge` را تنظیم کنید. برای Chromium نصب‌شده Playwright مقدار
`chromium` قابل استفاده است. تست مرورگر به داده دمو نیاز دارد و سفارش‌های پرداخت
آزمایشی می‌سازد؛ روی دیتابیس واقعی اجرا نشود. تصویر و اندازه‌گیری منابع در
`test-results/` و نتیجه HTTPS/بازیابی در `artifacts/verification/` ذخیره می‌شود.

پس از تغییر کلاس‌های قالب/JS، CSS را دوباره بسازید. اصل تصاویر تولیدشده در
`assets/source-images/` نگهداری شده؛ بازسازی WebP با
`python scripts/build_image_assets.py` انجام می‌شود. تصاویر و فونت وابستگی CDN ندارند.

## قراردادها و محدودیت فعال‌سازی

مبالغ در دیتابیس **ریال صحیح** هستند؛ هر تومان ۱۰ ریال است. UI تومان و اسکیما و
درگاه IRR نمایش/ارسال می‌کنند. از float برای مبلغ استفاده نمی‌شود.

دستیار و پیام‌های اختیاری پیش‌فرض خاموش‌اند. `.env.example` پارامترهای توسعه و
`.env.production.example` تنظیمات استقرار را معرفی می‌کنند. محیط HTTPS آزمایشی
روی 8443 فقط برای تست محلی است. دامنه عمومی، TLS معتبر عمومی، اطلاعات واقعی
کسب‌وکار و حساب‌های درگاه/پیامک ارائه نشده‌اند؛ انتشار واقعی انجام نشده است.
فرمان `verify_launch` تا تکمیل آن‌ها فروش عمومی را مسدود گزارش می‌کند.
