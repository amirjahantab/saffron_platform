"""Django Admin configuration for PaymentTransactions and PaymentRefunds."""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from apps.payments.models import PaymentRefund, PaymentTransaction


class PaymentRefundInline(admin.TabularInline):
    model = PaymentRefund
    extra = 0
    can_delete = False
    readonly_fields = (
        "public_id",
        "amount_rial",
        "display_amount_toman",
        "status",
        "reason",
        "provider_refund_id",
        "processed_by",
        "processed_at",
        "created_at",
    )

    @admin.display(description=_("مبلغ استرداد (تومان)"))
    def display_amount_toman(self, obj: PaymentRefund) -> str:
        if not obj.pk:
            return "-"
        return obj.formatted_amount_toman


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "order",
        "provider",
        "status",
        "display_amount_toman",
        "authority",
        "reference_id",
        "verified_at",
        "created_at",
    )
    list_filter = ("provider", "status", "created_at")
    search_fields = (
        "order__order_number",
        "authority",
        "reference_id",
        "idempotency_key",
        "card_pan_masked",
    )
    readonly_fields = (
        "public_id",
        "idempotency_key",
        "display_amount_toman",
        "raw_request_response",
        "raw_verify_response",
        "verified_at",
        "created_at",
        "updated_at",
    )
    inlines = [PaymentRefundInline]

    @admin.display(description=_("مبلغ تراکنش (تومان)"))
    def display_amount_toman(self, obj: PaymentTransaction) -> str:
        return obj.formatted_amount_toman


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "order",
        "payment",
        "display_amount_toman",
        "status",
        "provider_refund_id",
        "processed_by",
        "processed_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "payment__reference_id", "provider_refund_id")
    readonly_fields = ("public_id", "display_amount_toman", "created_at", "updated_at")

    @admin.display(description=_("مبلغ استرداد (تومان)"))
    def display_amount_toman(self, obj: PaymentRefund) -> str:
        return obj.formatted_amount_toman