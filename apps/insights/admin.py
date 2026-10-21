from django.contrib import admin
from .models import Event, Notification, Preference


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("kind", "product", "source", "campaign", "created_at")
    list_filter = ("kind", "source", "created_at")
    readonly_fields = tuple(field.name for field in Event._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "marketing", "attempts", "created_at")
    list_filter = ("status", "marketing")
    readonly_fields = tuple(field.name for field in Notification._meta.fields)

    def has_add_permission(self, request):
        return False


admin.site.register(Preference)
