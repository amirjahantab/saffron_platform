"""
Base Django settings for Saffron E-commerce Platform.
Common configuration shared across development, test, and production environments.
"""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def get_env_variable(var_name: str, default: str | None = None, required: bool = False) -> str:
    """Retrieve an environment variable or raise ImproperlyConfigured if required and missing."""
    value = os.environ.get(var_name, default)
    if required and (value is None or str(value).strip() == ""):
        raise ImproperlyConfigured(f"Required environment variable '{var_name}' is not set.")
    return str(value) if value is not None else ""


def get_env_bool(var_name: str, default: bool = False) -> bool:
    """Parse boolean environment variables safely."""
    val = os.environ.get(var_name)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")


def get_env_list(var_name: str, default: list[str] | None = None) -> list[str]:
    """Parse comma-separated environment variables into a clean list of strings."""
    val = os.environ.get(var_name)
    if not val:
        return default if default is not None else []
    return [item.strip() for item in val.split(",") if item.strip()]


# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS: list[str] = []

LOCAL_APPS = [
    "apps.core.apps.CoreConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.payments.apps.PaymentsConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Custom User Model (Phase 2)
AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database configuration (PostgreSQL by default)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": get_env_variable("POSTGRES_DB", default="saffron_db"),
        "USER": get_env_variable("POSTGRES_USER", default="saffron_user"),
        "PASSWORD": get_env_variable("POSTGRES_PASSWORD", default=""),
        "HOST": get_env_variable("POSTGRES_HOST", default="127.0.0.1"),
        "PORT": get_env_variable("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": int(get_env_variable("POSTGRES_CONN_MAX_AGE", default="60")),
        "OPTIONS": {
            "connect_timeout": 5,
        },
    }
}

# Redis Cache Configuration
REDIS_URL = get_env_variable("REDIS_URL", default="redis://127.0.0.1:6379/1")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "IGNORE_EXCEPTIONS": False,
        },
        "KEY_PREFIX": "saffron",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization & Localization (Persian / Iran)
LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# Static & Media Files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# File Upload Security Limits (5 MB max upload size for certificates/images)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o644
CATALOG_MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Global Baseline Security & Session Settings
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 days

# Currency Contract Constants
CURRENCY_STORAGE_UNIT = "IRR"
CURRENCY_DISPLAY_UNIT = "IRT"
RIAL_TO_TOMAN_FACTOR = 10

# OTP & SMS Authentication Settings (Phase 2)
OTP_CODE_LENGTH = int(get_env_variable("OTP_CODE_LENGTH", default="6"))
OTP_EXPIRY_SECONDS = int(get_env_variable("OTP_EXPIRY_SECONDS", default="120"))
OTP_RESEND_COOLDOWN_SECONDS = int(get_env_variable("OTP_RESEND_COOLDOWN_SECONDS", default="120"))
OTP_MAX_VERIFY_ATTEMPTS = int(get_env_variable("OTP_MAX_VERIFY_ATTEMPTS", default="5"))
OTP_MAX_REQUESTS_PER_HOUR_PHONE = int(get_env_variable("OTP_MAX_REQUESTS_PER_HOUR_PHONE", default="5"))
OTP_MAX_REQUESTS_PER_HOUR_IP = int(get_env_variable("OTP_MAX_REQUESTS_PER_HOUR_IP", default="10"))
SMS_PROVIDER_CLASS = get_env_variable(
    "SMS_PROVIDER_CLASS",
    default="apps.accounts.services.sms_provider.SandboxSMSProvider",
)
OTP_SANDBOX_STORE_OUTBOX = False

# Order & Inventory Reservation Settings (Phase 4)
ORDER_RESERVATION_EXPIRY_MINUTES = int(
    get_env_variable("ORDER_RESERVATION_EXPIRY_MINUTES", default="15")
)
ORDER_DEFAULT_SHIPPING_COST_RIAL = int(
    get_env_variable("ORDER_DEFAULT_SHIPPING_COST_RIAL", default="450000")
)
ORDER_FREE_SHIPPING_THRESHOLD_RIAL = int(
    get_env_variable("ORDER_FREE_SHIPPING_THRESHOLD_RIAL", default="15000000")
)

# Payment Gateway Settings (Phase 5)
PAYMENT_DEFAULT_GATEWAY = get_env_variable("PAYMENT_DEFAULT_GATEWAY", default="sandbox")
PAYMENT_CALLBACK_BASE_URL = get_env_variable(
    "PAYMENT_CALLBACK_BASE_URL",
    default="http://127.0.0.1:8000",
).rstrip("/")
ZARINPAL_MERCHANT_ID = get_env_variable(
    "ZARINPAL_MERCHANT_ID",
    default="00000000-0000-0000-0000-000000000000",
)
ZARINPAL_SANDBOX = get_env_bool("ZARINPAL_SANDBOX", default=True)
ZARINPAL_TIMEOUT_SECONDS = int(get_env_variable("ZARINPAL_TIMEOUT_SECONDS", default="10"))

# Structured Logging
LOG_LEVEL = get_env_variable("DJANGO_LOG_LEVEL", default="INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} [{name}:{lineno}] [PID:{process}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}