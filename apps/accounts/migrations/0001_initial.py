"""Initial migration for custom User model."""
import uuid
from django.db import migrations, models
import apps.accounts.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(blank=True, null=True, verbose_name="last login"),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text="Designates that this user has all permissions without explicitly assigning them.",
                        verbose_name="superuser status",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                        verbose_name="تاریخ ایجاد",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="تاریخ آخرین ویرایش",
                    ),
                ),
                (
                    "public_id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                        verbose_name="شناسه عمومی",
                    ),
                ),
                (
                    "phone_number",
                    models.CharField(
                        db_index=True,
                        max_length=11,
                        unique=True,
                        validators=[apps.accounts.validators.validate_iranian_phone],
                        verbose_name="شماره موبایل",
                    ),
                ),
                (
                    "full_name",
                    models.CharField(
                        blank=True,
                        max_length=150,
                        verbose_name="نام و نام خانوادگی",
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        blank=True,
                        max_length=254,
                        null=True,
                        unique=True,
                        verbose_name="ایمیل",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="فعال")),
                (
                    "is_staff",
                    models.BooleanField(default=False, verbose_name="دسترسی پنل مدیریت"),
                ),
                (
                    "is_phone_verified",
                    models.BooleanField(default=False, verbose_name="شماره تأیید شده"),
                ),
                (
                    "last_otp_verified_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="آخرین زمان تأیید OTP",
                    ),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "کاربر",
                "verbose_name_plural": "کاربران",
                "ordering": ["-created_at"],
            },
        ),
    ]