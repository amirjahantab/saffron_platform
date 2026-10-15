"""Django Admin configuration for the custom User model."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django import forms
from django.utils.translation import gettext_lazy as _
from apps.accounts.models import User
from apps.accounts.validators import normalize_iranian_phone


class UserCreationAdminForm(forms.ModelForm):
    """Form for creating new users in the Django Admin."""

    password = forms.CharField(
        label=_("رمز عبور (اختیاری برای کاربران عادی OTP)"),
        widget=forms.PasswordInput,
        required=False,
    )

    class Meta:
        model = User
        fields = ("phone_number", "full_name", "email", "is_active", "is_staff", "is_superuser")

    def clean_phone_number(self) -> str:
        return normalize_iranian_phone(self.cleaned_data.get("phone_number", ""))

    def save(self, commit: bool = True) -> User:
        user: User = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        if commit:
            user.save()
        return user


class UserChangeAdminForm(forms.ModelForm):
    """Form for updating users in the Django Admin."""

    password = ReadOnlyPasswordHashField(
        label=_("رمز عبور"),
        help_text=_("رمزهای عبور به‌صورت هش ذخیره می‌شوند و قابل مشاهده نیستند."),
    )

    class Meta:
        model = User
        fields = (
            "phone_number",
            "password",
            "full_name",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "is_phone_verified",
            "groups",
            "user_permissions",
        )

    def clean_phone_number(self) -> str:
        return normalize_iranian_phone(self.cleaned_data.get("phone_number", ""))


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeAdminForm
    add_form = UserCreationAdminForm

    list_display = (
        "phone_number",
        "full_name",
        "is_phone_verified",
        "is_active",
        "is_staff",
        "created_at",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "is_phone_verified")
    search_fields = ("phone_number", "full_name", "email")
    ordering = ("-created_at",)
    readonly_fields = ("public_id", "created_at", "updated_at", "last_login", "last_otp_verified_at")

    fieldsets = (
        (_("اطلاعات شناسایی"), {"fields": ("phone_number", "public_id", "password")}),
        (_("اطلاعات فردی"), {"fields": ("full_name", "email")}),
        (
            _("وضعیت و دسترسی‌ها"),
            {
                "fields": (
                    "is_active",
                    "is_phone_verified",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            _("گزارش زمانی"),
            {"fields": ("last_otp_verified_at", "last_login", "created_at", "updated_at")},
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "phone_number",
                    "full_name",
                    "email",
                    "password",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )