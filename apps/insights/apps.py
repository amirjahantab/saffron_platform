from django.apps import AppConfig


class InsightsConfig(AppConfig):
    name = "apps.insights"
    verbose_name = "تحلیل و ارتباط با مشتری"

    def ready(self):
        from . import signals  # noqa
