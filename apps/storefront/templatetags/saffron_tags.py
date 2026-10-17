"""
Template filters enforcing the Rial-to-Toman presentation contract and Persian numerals.
"""
from django import template
from apps.core.currency import format_price_toman, to_persian_digits
from apps.core.exceptions import MonetaryPrecisionError

register = template.Library()


@register.filter(name="toman")
def toman_filter(amount_rial: object, with_unit: bool = True) -> str:
    """
    Convert an integer Rial database value into a formatted Persian Toman string.
    Usage: {{ variant.effective_price_rial|toman }}
    """
    if amount_rial is None or amount_rial == "":
        return ""
    try:
        validated_int = int(str(amount_rial))
        return format_price_toman(validated_int, use_persian_digits=True, with_unit=bool(with_unit))
    except (ValueError, TypeError, MonetaryPrecisionError):
        return str(amount_rial)


@register.filter(name="persian_digits")
def persian_digits_filter(value: object) -> str:
    """
    Convert ASCII digits in any value to Persian digits (۰-۹).
    Usage: {{ variant.stock_quantity|persian_digits }}
    """
    if value is None:
        return ""
    return to_persian_digits(str(value))