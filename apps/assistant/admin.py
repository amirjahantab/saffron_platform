from django.contrib import admin
from .models import Usage


@admin.register(Usage)
class UsageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "status", "reserved_tokens", "input_tokens", "output_tokens")
    readonly_fields = tuple(field.name for field in Usage._meta.fields)

    def has_add_permission(self, request):
        return False
