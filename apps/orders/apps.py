from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrdersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.orders"
    verbose_name = _("سبد خرید، موجودی و سفارش‌ها")

    def ready(self) -> None:
        # Register signal receivers (e.g. guest cart merge upon OTP login)
        import apps.orders.signals  # noqa: F401