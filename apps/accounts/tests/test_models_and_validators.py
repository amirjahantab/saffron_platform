"""Tests for Iranian phone normalization, validation, and custom User model."""
from django.core.exceptions import ValidationError
from django.test import TestCase
from apps.accounts.models import User
from apps.accounts.validators import mask_phone_number, normalize_iranian_phone


class PhoneValidatorTests(TestCase):
    """Test normalization and validation of Iranian mobile numbers."""

    def test_valid_phone_formats_normalize_to_canonical_09(self) -> None:
        cases = [
            "09123456789",
            "+989123456789",
            "00989123456789",
            "989123456789",
            "9123456789",
            "۰۹۱۲۳۴۵۶۷۸۹",
            "٠٩١٢٣٤٥٦٧٨٩",
            " +98 912-345-6789 ",
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_iranian_phone(raw), "09123456789")

    def test_invalid_phone_numbers_are_rejected(self) -> None:
        invalid_cases = [
            "",
            "02188776655",     # Landline
            "0912345678",      # Too short (10 digits)
            "091234567890",    # Too long (12 digits)
            "+14155552671",    # Non-Iranian country code
            "08123456789",     # Does not start with 09
            "0912345abcd",     # Contains letters
        ]
        for invalid in invalid_cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    normalize_iranian_phone(invalid)

    def test_mask_phone_number_hides_middle_digits(self) -> None:
        self.assertEqual(mask_phone_number("09151234567"), "0915***4567")
        self.assertEqual(mask_phone_number("short"), "***")


class CustomUserModelTests(TestCase):
    """Test User creation, superuser constraints, and empty email handling."""

    def test_create_user_with_persian_digits_and_unusable_password(self) -> None:
        user = User.objects.create_user(phone_number="۰۹۱۵۱۱۱۲۲۳۳", full_name="علی رضایی")
        self.assertEqual(user.phone_number, "09151112233")
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertIsNone(user.email)

    def test_multiple_users_without_email_do_not_violate_unique_constraint(self) -> None:
        u1 = User.objects.create_user(phone_number="09120000001", email="")
        u2 = User.objects.create_user(phone_number="09120000002", email="")
        self.assertIsNone(u1.email)
        self.assertIsNone(u2.email)

    def test_create_superuser_requires_password_and_sets_flags(self) -> None:
        with self.assertRaises(ValueError):
            User.objects.create_superuser(phone_number="09120000003", password=None)

        admin_user = User.objects.create_superuser(
            phone_number="09120000003",
            password="StrongAdminPassword!2026",
        )
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.is_phone_verified)
        self.assertTrue(admin_user.check_password("StrongAdminPassword!2026"))