"""
Forms for Storefront HTML views (Sub-phase 6.2):
- Profile update form (full_name, email)
"""
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from apps.accounts.models import User


class UserProfileUpdateForm(forms.ModelForm):
    """Allows authenticated customers to update their name and email in the account dashboard."""

    class Meta:
        model = User
        fields = ("full_name", "email")
        labels = {
            "full_name": _("نام و نام خانوادگی"),
            "email": _("نشانی ایمیل (اختیاری)"),
        }
        error_messages = {
            "email": {
                "invalid": _("فرمت ایمیل واردشده معتبر نیست."),
                "unique": _("این ایمیل قبلاً برای حساب دیگری ثبت شده است."),
            }
        }

    def clean_full_name(self) -> str:
        return (self.cleaned_data.get("full_name") or "").strip()

    def clean_email(self) -> str | None:
        raw_email = (self.cleaned_data.get("email") or "").strip().lower()
        if not raw_email:
            return None
        qs = User.objects.filter(email=raw_email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(_("این ایمیل قبلاً در سیستم ثبت شده است."))
        return raw_email