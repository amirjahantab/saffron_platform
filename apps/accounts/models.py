"""Custom User model based on Iranian mobile phone number authentication."""
from typing import Any
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.accounts.validators import normalize_iranian_phone, validate_iranian_phone
from apps.core.models import TimeStampedModel, UUIDModel


class UserManager(BaseUserManager["User"]):
    """Custom manager for phone-number-based User model."""

    def create_user(
        self,
        phone_number: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "User":
        if not phone_number:
            raise ValueError(_("وارد کردن شماره موبایل الزامی است."))

        normalized_phone = normalize_iranian_phone(phone_number)

        # Prevent mass-assignment privilege escalation in standard user creation
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)

        email = extra_fields.get("email")
        if email:
            extra_fields["email"] = self.normalize_email(email).strip().lower()
        else:
            extra_fields["email"] = None

        user = self.model(phone_number=normalized_phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.full_clean()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        phone_number: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "User":
        if not password:
            raise ValueError(_("کاربر ارشد (Superuser) باید دارای رمز عبور قوی باشد."))

        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        extra_fields["is_active"] = True
        extra_fields["is_phone_verified"] = True

        return self.create_user(phone_number=phone_number, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel, UUIDModel):
    """
    Primary User model for the Saffron E-commerce Platform.
    Uses normalized Iranian mobile phone number ('09XXXXXXXXX') as the unique identifier.
    """

    phone_number = models.CharField(
        max_length=11,
        unique=True,
        db_index=True,
        validators=[validate_iranian_phone],
        verbose_name=_("شماره موبایل"),
    )
    full_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name=_("نام و نام خانوادگی"),
    )
    email = models.EmailField(
        blank=True,
        null=True,
        unique=True,
        verbose_name=_("ایمیل"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("فعال"),
    )
    is_staff = models.BooleanField(
        default=False,
        verbose_name=_("دسترسی پنل مدیریت"),
    )
    is_phone_verified = models.BooleanField(
        default=False,
        verbose_name=_("شماره تأیید شده"),
    )
    last_otp_verified_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("آخرین زمان تأیید OTP"),
    )

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("کاربر")
        verbose_name_plural = _("کاربران")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        if self.full_name:
            return f"{self.full_name} ({self.phone_number})"
        return self.phone_number

    def clean(self) -> None:
        super().clean()
        if self.phone_number:
            self.phone_number = normalize_iranian_phone(self.phone_number)
        if self.email is not None:
            cleaned_email = self.email.strip().lower()
            self.email = cleaned_email if cleaned_email else None
        if self.is_superuser and not self.is_staff:
            raise ValidationError(_("کاربر ارشد باید دسترسی پنل مدیریت (is_staff) داشته باشد."))
        