"""Forms for validating cart mutations, checkout submission, and order cancellation."""
from typing import Any
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from apps.accounts.validators import normalize_iranian_phone
from apps.orders.models import Order
from apps.orders.validators import normalize_iranian_postal_code


class CartAddItemForm(forms.Form):
    variant_public_id = forms.UUIDField(
        required=True,
        error_messages={
            "required": _("انتخاب گونه محصول الزامی است."),
            "invalid": _("شناسه گونه محصول معتبر نیست."),
        },
    )
    quantity = forms.IntegerField(
        required=False,
        initial=1,
        min_value=1,
        max_value=1000,
        error_messages={
            "min_value": _("تعداد باید حداقل ۱ عدد باشد."),
            "max_value": _("تعداد واردشده بیش از حد مجاز است."),
            "invalid": _("تعداد باید یک عدد صحیح معتبر باشد."),
        },
    )

    def clean_quantity(self) -> int:
        val = self.cleaned_data.get("quantity")
        return int(val) if val is not None else 1


class CartUpdateItemForm(forms.Form):
    variant_public_id = forms.UUIDField(
        required=True,
        error_messages={
            "required": _("انتخاب گونه محصول الزامی است."),
            "invalid": _("شناسه گونه محصول معتبر نیست."),
        },
    )
    quantity = forms.IntegerField(
        required=True,
        min_value=0,
        max_value=1000,
        error_messages={
            "required": _("وارد کردن تعداد جدید الزامی است."),
            "min_value": _("تعداد نمی‌تواند منفی باشد."),
            "max_value": _("تعداد واردشده بیش از حد مجاز است."),
            "invalid": _("تعداد باید یک عدد صحیح معتبر باشد."),
        },
    )


class CartRemoveItemForm(forms.Form):
    variant_public_id = forms.UUIDField(
        required=True,
        error_messages={
            "required": _("انتخاب گونه محصول الزامی است."),
            "invalid": _("شناسه گونه محصول معتبر نیست."),
        },
    )


class CheckoutForm(forms.Form):
    """
    Validates checkout payload.
    Supports either selecting an existing `shipping_address_public_id`
    OR providing full recipient and address fields directly.
    """

    shipping_address_public_id = forms.UUIDField(
        required=False,
        error_messages={"invalid": _("شناسه آدرس انتخابی معتبر نیست.")},
    )
    recipient_full_name = forms.CharField(max_length=150, required=False)
    recipient_phone = forms.CharField(max_length=20, required=False)
    province = forms.CharField(max_length=80, required=False)
    city = forms.CharField(max_length=80, required=False)
    address_line = forms.CharField(max_length=500, required=False)
    postal_code = forms.CharField(max_length=20, required=False)
    save_address = forms.BooleanField(required=False, initial=False)

    shipping_method = forms.ChoiceField(
        choices=Order.ShippingMethod.choices,
        required=False,
        initial=Order.ShippingMethod.POST_PISHTAZ,
        error_messages={"invalid_choice": _("روش ارسال انتخاب‌شده معتبر نیست.")},
    )
    customer_note = forms.CharField(max_length=500, required=False)
    idempotency_key = forms.CharField(max_length=64, required=False)

    def clean_shipping_method(self) -> str:
        val = self.cleaned_data.get("shipping_method")
        return val if val else Order.ShippingMethod.POST_PISHTAZ

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        addr_id = cleaned_data.get("shipping_address_public_id")

        if not addr_id:
            required_fields = {
                "recipient_full_name": _("نام و نام خانوادگی گیرنده الزامی است."),
                "recipient_phone": _("شماره موبایل گیرنده الزامی است."),
                "province": _("انتخاب استان الزامی است."),
                "city": _("انتخاب شهر الزامی است."),
                "address_line": _("وارد کردن نشانی پستی الزامی است."),
                "postal_code": _("وارد کردن کد پستی ۱۰ رقمی الزامی است."),
            }
            for field, msg in required_fields.items():
                val = str(cleaned_data.get(field) or "").strip()
                if not val:
                    self.add_error(field, ValidationError(msg))

            raw_phone = cleaned_data.get("recipient_phone")
            if raw_phone and not self.has_error("recipient_phone"):
                try:
                    cleaned_data["recipient_phone"] = normalize_iranian_phone(raw_phone)
                except ValidationError as exc:
                    self.add_error("recipient_phone", exc)

            raw_postal = cleaned_data.get("postal_code")
            if raw_postal and not self.has_error("postal_code"):
                try:
                    cleaned_data["postal_code"] = normalize_iranian_postal_code(raw_postal)
                except ValidationError as exc:
                    self.add_error("postal_code", exc)

        return cleaned_data


class OrderCancelForm(forms.Form):
    cancel_reason = forms.CharField(
        max_length=250,
        required=False,
    )