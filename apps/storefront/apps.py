from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StorefrontConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.storefront"
    verbose_name = _("ویترین فروشگاه و رابط کاربری")