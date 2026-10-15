"""Forms for validating OTP request and verification payloads."""
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from apps.accounts.validators import normalize_digits_to_ascii, normalize_iranian_phone


class OTPRequestForm(forms.Form):
    phone_number = forms.CharField(
        max_length=20,
        required=True,
        error_messages={"required": _("وارد کردن شماره موبایل الزامی است.")},
    )

    def clean_phone_number(self) -> str:
        raw_phone = self.cleaned_data.get("phone_number", "")
        return normalize_iranian_phone(raw_phone)


class OTPVerifyForm(forms.Form):
    phone_number = forms.CharField(
        max_length=20,
        required=True,
        error_messages={"required": _("وارد کردن شماره موبایل الزامی است.")},
    )
    code = forms.CharField(
        max_length=10,
        required=True,
        error_messages={"required": _("وارد کردن کد تایید الزامی است.")},
    )

    def clean_phone_number(self) -> str:
        raw_phone = self.cleaned_data.get("phone_number", "")
        return normalize_iranian_phone(raw_phone)

    def clean_code(self) -> str:
        raw_code = self.cleaned_data.get("code", "")
        cleaned = normalize_digits_to_ascii(str(raw_code)).strip()
        expected_len = int(getattr(settings, "OTP_CODE_LENGTH", 6))
        if not cleaned.isdigit() or len(cleaned) != expected_len:
            raise ValidationError(
                _("کد تایید باید یک عدد %(length)d رقمی باشد."),
                params={"length": expected_len},
                code="invalid_otp_format",
            )
        return cleaned