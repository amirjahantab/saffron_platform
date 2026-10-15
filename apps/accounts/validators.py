"""
Iranian mobile phone number normalization, validation, and PII masking utilities.
"""
import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

DIGIT_TRANSLATION_MAP = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

IRAN_MOBILE_REGEX = re.compile(r"^09\d{9}$")


def normalize_digits_to_ascii(value: str) -> str:
    """Convert Persian and Arabic numerals in a string to standard ASCII digits."""
    if not isinstance(value, str):
        return ""
    return value.translate(DIGIT_TRANSLATION_MAP)


def normalize_iranian_phone(raw_phone: str) -> str:
    """
    Normalize various Iranian mobile phone representations to canonical '09XXXXXXXXX' format.
    Supported inputs:
      - 09123456789 -> 09123456789
      - +989123456789 -> 09123456789
      - 00989123456789 -> 09123456789
      - 989123456789 -> 09123456789
      - 9123456789 -> 09123456789
      - Strings with Persian/Arabic digits, spaces, or hyphens.
    Raises ValidationError if the resulting string is not a valid 11-digit Iranian mobile number.
    """
    if not isinstance(raw_phone, str):
        raise ValidationError(_("شماره موبایل باید یک رشته متنی معتبر باشد."))

    cleaned = normalize_digits_to_ascii(raw_phone).strip()
    cleaned = re.sub(r"[\s\-\(\)]+", "", cleaned)

    if cleaned.startswith("+98"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("0098"):
        cleaned = "0" + cleaned[4:]
    elif cleaned.startswith("98") and len(cleaned) == 12:
        cleaned = "0" + cleaned[2:]
    elif cleaned.startswith("9") and len(cleaned) == 10:
        cleaned = "0" + cleaned

    validate_iranian_phone(cleaned)
    return cleaned


def validate_iranian_phone(value: str) -> None:
    """Django field/form validator enforcing canonical 09XXXXXXXXX Iranian mobile format."""
    if not isinstance(value, str) or not IRAN_MOBILE_REGEX.match(value):
        raise ValidationError(
            _("شماره موبایل واردشده معتبر نیست. شماره باید ۱۱ رقم و با ۰۹ شروع شود."),
            code="invalid_iranian_phone",
        )


def mask_phone_number(phone_number: str) -> str:
    """Mask middle digits of a phone number for safe audit logging (e.g. 0912***6789)."""
    if not isinstance(phone_number, str) or len(phone_number) < 11:
        return "***"
    return f"{phone_number[:4]}***{phone_number[-4:]}"