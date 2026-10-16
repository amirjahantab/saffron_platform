"""Django Admin configuration for Carts, ShippingAddresses, Orders, OrderItems, and StockReservations."""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from apps.orders.models import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    ShippingAddress,
    StockReservation,
)


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


@admin.register(ShippingAddress)
class ShippingAddressAdmin(admin.ModelAdmin):
    list_display = (
        "recipient_full_name",
        "recipient_phone",
        "province",
        "city",
        "postal_code",
        "user",
        "is_default",
    )
    list_filter = ("province", "is_default")
    search_fields = (
        "recipient_full_name",
        "recipient_phone",
        "postal_code",
        "user__phone_number",
    )
    readonly_fields = ("public_id", "created_at", "updated_at")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "public_id",
        "variant",
        "product_name_snapshot",
        "sku_snapshot",
        "weight_label_snapshot",
        "batch_code_snapshot",
        "quantity",
        "unit_base_price_rial",
        "unit_effective_price_rial",
        "line_effective_total_rial",
        "display_line_total_toman",
    )
    fields = (
        "sku_snapshot",
        "product_name_snapshot",
        "weight_label_snapshot",
        "batch_code_snapshot",
        "quantity",
        "unit_effective_price_rial",
        "display_line_total_toman",
    )

    @admin.display(description=_("جمع ردیف (تومان)"))
    def display_line_total_toman(self, obj: OrderItem) -> str:
        if not obj.pk:
            return "-"
        return obj.formatted_line_effective_total_toman


class StockReservationInline(admin.TabularInline):
    model = StockReservation
    extra = 0
    can_delete = False
    readonly_fields = (
        "public_id",
        "variant",
        "quantity",
        "status",
        "expires_at",
        "committed_at",
        "released_at",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "recipient_full_name",
        "status",
        "shipping_method",
        "display_payable_toman",
        "created_at",
    )
    list_filter = ("status", "shipping_method", "province", "created_at")
    search_fields = (
        "order_number",
        "user__phone_number",
        "recipient_full_name",
        "recipient_phone",
        "postal_code",
        "tracking_code",
    )
    readonly_fields = (
        "public_id",
        "order_number",
        "idempotency_key",
        "display_payable_toman",
        "created_at",
        "updated_at",
        "paid_at",
        "shipped_at",
        "delivered_at",
        "cancelled_at",
    )
    inlines = [OrderItemInline, StockReservationInline]

    @admin.display(description=_("مبلغ قابل پرداخت (تومان)"))
    def display_payable_toman(self, obj: Order) -> str:
        return obj.formatted_payable_toman


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "variant",
        "quantity",
        "status",
        "expires_at",
        "committed_at",
        "released_at",
    )
    list_filter = ("status", "expires_at")
    search_fields = ("order__order_number", "variant__sku")
    readonly_fields = ("public_id", "created_at", "updated_at")