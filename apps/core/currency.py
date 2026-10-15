"""
Strict Monetary & Currency Contract Module (IRR / IRT).

Rules enforced across the entire platform:
1. All prices and monetary values are stored in the database as integer Rials (IRR).
2. All user-facing prices are displayed in Tomans (IRT), where 1 Toman = 10 Rials.
3. Floating-point numbers (`float`) are strictly rejected in all monetary functions.
4. Any Rial amount representing a Toman price must be a non-negative multiple of 10.
"""
from decimal import Decimal, ROUND_HALF_UP
from apps.core.exceptions import MonetaryPrecisionError

RIAL_TO_TOMAN_FACTOR: int = 10
PERSIAN_DIGITS_MAP = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _reject_float(value: object) -> None:
    """Ensure floats are never passed into monetary calculations."""
    if isinstance(value, float):
        raise MonetaryPrecisionError(
            "Floating-point numbers are strictly forbidden in monetary calculations. "
            "Use int or Decimal instead."
        )


def validate_rial_amount(amount_rial: int) -> int:
    """
    Validate that an amount in Rials is a non-negative integer and a multiple of 10.
    Returns the validated integer amount.
    """
    _reject_float(amount_rial)
    if isinstance(amount_rial, bool) or not isinstance(amount_rial, int):
        raise MonetaryPrecisionError(
            f"Rial amount must be an integer, got {type(amount_rial).__name__}."
        )
    if amount_rial < 0:
        raise MonetaryPrecisionError("Monetary amount in Rials cannot be negative.")
    if amount_rial % RIAL_TO_TOMAN_FACTOR != 0:
        raise MonetaryPrecisionError(
            f"Rial amount ({amount_rial}) must be a multiple of {RIAL_TO_TOMAN_FACTOR} "
            "to guarantee lossless conversion to Toman."
        )
    return amount_rial


def toman_to_rial(amount_toman: int) -> int:
    """Convert an integer Toman amount to integer Rials for database storage or payment gateways."""
    _reject_float(amount_toman)
    if isinstance(amount_toman, bool) or not isinstance(amount_toman, int):
        raise MonetaryPrecisionError(
            f"Toman amount must be an integer, got {type(amount_toman).__name__}."
        )
    if amount_toman < 0:
        raise MonetaryPrecisionError("Monetary amount in Tomans cannot be negative.")
    return amount_toman * RIAL_TO_TOMAN_FACTOR


def rial_to_toman(amount_rial: int) -> int:
    """Convert a validated Rial amount to integer Tomans for presentation."""
    validated_rial = validate_rial_amount(amount_rial)
    return validated_rial // RIAL_TO_TOMAN_FACTOR


def apply_percentage_discount_rial(amount_rial: int, discount_percent: int | Decimal | str) -> int:
    """
    Safely calculate discounted price in Rials using Decimal arithmetic without floats.
    Rounds to the nearest 10 Rials (1 Toman) using ROUND_HALF_UP.
    """
    validated_rial = validate_rial_amount(amount_rial)
    _reject_float(discount_percent)

    try:
        pct = Decimal(str(discount_percent))
    except Exception as exc:
        raise MonetaryPrecisionError(f"Invalid discount percentage: {discount_percent}") from exc

    if pct < Decimal("0") or pct > Decimal("100"):
        raise MonetaryPrecisionError("Discount percentage must be between 0 and 100.")

    amount_toman_dec = Decimal(validated_rial // RIAL_TO_TOMAN_FACTOR)
    multiplier = (Decimal("100") - pct) / Decimal("100")
    discounted_toman = int(
        (amount_toman_dec * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    return discounted_toman * RIAL_TO_TOMAN_FACTOR


def to_persian_digits(text: str) -> str:
    """Convert ASCII digits in a string to Persian digits."""
    return text.translate(PERSIAN_DIGITS_MAP)


def format_price_toman(amount_rial: int, use_persian_digits: bool = True, with_unit: bool = True) -> str:
    """
    Format a Rial database value into a human-readable Toman string with thousands separators.
    Example: 1250000 (Rials) -> '۱۲۵,۰۰۰ تومان'
    """
    toman_value = rial_to_toman(amount_rial)
    formatted_number = f"{toman_value:,}"
    if use_persian_digits:
        formatted_number = to_persian_digits(formatted_number)
    if with_unit:
        return f"{formatted_number} تومان"
    return formatted_number