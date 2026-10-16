"""Django Admin configuration for Carts and CartItems."""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from apps.orders.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("public_id", "display_line_total_toman", "created_at", "updated_at")
    fields = ("variant", "quantity", "display_line_total_toman", "created_at")

    @admin.display(description=_("جمع ردیف (تومان)"))
    def display_line_total_toman(self, obj: CartItem) -> str:
        if not obj.pk or not obj.variant_id:
            return "-"
        return obj.formatted_line_effective_total_toman


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("public_id", "user", "session_key", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__phone_number", "user__full_name", "session_key")
    readonly_fields = ("public_id", "created_at", "updated_at")
    inlines = [CartItemInline]