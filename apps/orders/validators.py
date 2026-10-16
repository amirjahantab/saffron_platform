"""
Validators and normalizers for shipping addresses and Iranian 10-digit postal codes.
"""
import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from apps.accounts.validators import normalize_digits_to_ascii

IRAN_POSTAL_CODE_REGEX = re.compile(r"^\d{10}$")


def normalize_iranian_postal_code(raw_postal_code: str) -> str:
    """
    Normalize Persian/Arabic digits, strip spaces/hyphens, and validate 10-digit Iranian postal code.
    """
    if not isinstance(raw_postal_code, str):
        raise ValidationError(_("کد پستی باید یک رشته متنی معتبر باشد."))

    cleaned = normalize_digits_to_ascii(raw_postal_code).strip()
    cleaned = re.sub(r"[\s\-]+", "", cleaned)

    validate_iranian_postal_code(cleaned)
    return cleaned


def validate_iranian_postal_code(value: str) -> None:
    """
    Validate a canonical 10-digit Iranian postal code.
    Rejects non-10-digit strings and artificial repeated digits (e.g. '0000000000' or '1111111111').
    """
    if not isinstance(value, str) or not IRAN_POSTAL_CODE_REGEX.match(value):
        raise ValidationError(
            _("کد پستی معتبر نیست. کد پستی باید دقیقاً ۱۰ رقم عددی باشد."),
            code="invalid_postal_code",
        )
    if len(set(value)) == 1:
        raise ValidationError(
            _("کد پستی واردشده معتبر نیست (تکرار یک رقم یکسان مجاز نیست)."),
            code="invalid_postal_code_repeated",
        )