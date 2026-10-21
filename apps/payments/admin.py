"""Django Admin configuration for PaymentTransactions and PaymentRefunds."""
from django.contrib import admin
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.shortcuts import render, redirect
from django.urls import path
from django.utils.translation import gettext_lazy as _
from apps.payments.models import PaymentRefund, PaymentTransaction


class PaymentRefundInline(admin.TabularInline):
    model = PaymentRefund
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False
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

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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

    change_list_template = "admin/payments/refund_list.html"

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [path("record-bank/", self.admin_site.admin_view(self.record_bank), name="payments_record_bank_refund")] + super().get_urls()

    def record_bank(self, request):
        from apps.orders.models import Order
        from apps.payments.refunds import record_bank_refund
        from apps.payments.exceptions import PaymentError
        if not request.user.has_perm("payments.change_paymentrefund"):
            raise PermissionDenied
        class RefundForm(forms.Form):
            order = forms.ModelChoiceField(label="سفارش", queryset=Order.objects.filter(paid_at__isnull=False).exclude(status="refunded"))
            reference = forms.CharField(label="شناسه واقعی رسید بانکی", min_length=6, max_length=128)
            amount_rial = forms.IntegerField(label="مبلغ استرداد به ریال", min_value=10)
            reason = forms.CharField(label="علت", max_length=255)
            evidence_note = forms.CharField(label="مستند بررسی رسید", min_length=12, max_length=1000, widget=forms.Textarea)
            confirmed = forms.BooleanField(label="تأیید می‌کنم وجه واقعاً از مسیر بانکی مسترد شده و رسید را بررسی کرده‌ام.")
        form = RefundForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                data = form.cleaned_data.copy()
                data.pop("confirmed")
                record_bank_refund(actor=request.user, **data)
                self.message_user(request, "رسید استرداد انجام‌شده ثبت شد.")
                return redirect("admin:payments_paymentrefund_changelist")
            except (PaymentError, ValidationError, IntegrityError) as exc:
                form.add_error(None, "رسید تکراری یا اطلاعات استرداد نامعتبر است؛ مبلغ، وضعیت سفارش و رسید را بررسی کنید.")
        return render(request, "admin/payments/record_refund.html", {**self.admin_site.each_context(request), "form": form, "title": "ثبت استرداد انجام‌شده در بانک"})


from .models import BankRefundReceipt


@admin.register(BankRefundReceipt)
class BankReceiptAdmin(admin.ModelAdmin):
    list_display = ("reference", "operator", "refund", "created_at")
    readonly_fields = tuple(field.name for field in BankRefundReceipt._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
