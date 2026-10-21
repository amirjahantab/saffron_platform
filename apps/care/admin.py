from django.contrib import admin
from .models import Ticket, Reply, Review


class ReplyInline(admin.TabularInline):
    model = Reply
    extra = 1
    fields = ("body", "is_internal", "author", "created_at")
    readonly_fields = ("author", "created_at")


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("subject", "user", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("subject", "user__phone_number")
    readonly_fields = ("user", "order", "public_id")
    inlines = [ReplyInline]

    def has_add_permission(self, request):
        return False

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for deleted in formset.deleted_objects:
            deleted.delete()
        for item in instances:
            if not item.pk:
                item.author = request.user
            item.save()
        formset.save_m2m()


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("title", "product", "rating", "is_approved", "verified_purchase")
    list_filter = ("is_approved", "rating")
    readonly_fields = ("product", "user", "rating", "title", "body", "verified_purchase")
    actions = ["approve"]

    @admin.action(description="تأیید انتشار نظرات خریداران")
    def approve(self, request, queryset):
        for item in queryset:
            if item.verified_purchase:
                item.is_approved = True
                item.save(update_fields=["is_approved", "updated_at"])

    def has_add_permission(self, request):
        return False
