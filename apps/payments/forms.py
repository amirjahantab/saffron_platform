"""Forms for validating payment initiation and refund requests."""
from django import forms
from django.utils.translation import gettext_lazy as _
from apps.payments.models import PaymentProvider


class PaymentInitiateForm(forms.Form):
    provider = forms.ChoiceField(
        choices=PaymentProvider.choices,
        required=False,
        error_messages={"invalid_choice": _("درگاه پرداخت انتخاب‌شده معتبر نیست.")},
    )
    idempotency_key = forms.CharField(
        max_length=64,
        required=False,
    )


class PaymentRefundForm(forms.Form):
    reason = forms.CharField(
        max_length=255,
        required=True,
        error_messages={"required": _("ذکر علت بازگشت وجه الزامی است.")},
    )
    amount_rial = forms.IntegerField(
        required=False,
        min_value=10,
        error_messages={"min_value": _("مبلغ بازگشت وجه باید حداقل ۱۰ ریال باشد.")},
    )