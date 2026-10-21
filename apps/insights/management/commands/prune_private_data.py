from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.insights.models import Event, Notification, OrderAttribution
from apps.care.models import Ticket


class Command(BaseCommand):
    help = "Apply configured analytics, sent-message and closed-ticket retention (not financial records)."

    def handle(self, *args, **options):
        now = timezone.now()
        events = Event.objects.filter(created_at__lt=now-timedelta(days=settings.ANALYTICS_RETENTION_DAYS)).delete()[0]
        OrderAttribution.objects.filter(order__created_at__lt=now-timedelta(days=settings.ANALYTICS_RETENTION_DAYS)).delete()
        notifications = Notification.objects.filter(updated_at__lt=now-timedelta(days=settings.MESSAGE_RETENTION_DAYS)).delete()[0]
        from apps.assistant.models import Usage
        Usage.objects.filter(created_at__lt=now-timedelta(days=settings.ANALYTICS_RETENTION_DAYS)).delete()
        tickets = Ticket.objects.filter(status="closed", updated_at__lt=now-timedelta(days=settings.SUPPORT_RETENTION_DAYS)).delete()[0]
        self.stdout.write(f"Deleted analytics={events}, notifications={notifications}, closed-support rows={tickets}.")
