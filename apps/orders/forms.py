"""Forms for validating cart mutation payloads."""
from django import forms
from django.utils.translation import gettext_lazy as _


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