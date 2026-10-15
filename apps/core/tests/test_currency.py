"""Unit tests for the monetary and currency contract (IRR / IRT)."""
from decimal import Decimal
from django.test import SimpleTestCase
from apps.core.currency import (
    apply_percentage_discount_rial,
    format_price_toman,
    rial_to_toman,
    toman_to_rial,
    validate_rial_amount,
)
from apps.core.exceptions import MonetaryPrecisionError


class CurrencyContractTests(SimpleTestCase):
    """Verify strict Rial/Toman conversions and float rejection."""

    def test_toman_to_rial_conversion(self) -> None:
        self.assertEqual(toman_to_rial(0), 0)
        self.assertEqual(toman_to_rial(185_000), 1_850_000)

    def test_rial_to_toman_conversion(self) -> None:
        self.assertEqual(rial_to_toman(0), 0)
        self.assertEqual(rial_to_toman(1_850_000), 185_000)

    def test_float_inputs_are_strictly_rejected(self) -> None:
        with self.assertRaises(MonetaryPrecisionError):
            toman_to_rial(100.0)  # type: ignore[arg-type]

        with self.assertRaises(MonetaryPrecisionError):
            rial_to_toman(1000.0)  # type: ignore[arg-type]

        with self.assertRaises(MonetaryPrecisionError):
            validate_rial_amount(2500.5)  # type: ignore[arg-type]

        with self.assertRaises(MonetaryPrecisionError):
            apply_percentage_discount_rial(1_000_000, 15.5)  # type: ignore[arg-type]

    def test_boolean_and_non_integer_inputs_are_rejected(self) -> None:
        with self.assertRaises(MonetaryPrecisionError):
            toman_to_rial(True)  # type: ignore[arg-type]

        with self.assertRaises(MonetaryPrecisionError):
            rial_to_toman("1000")  # type: ignore[arg-type]

    def test_negative_amounts_are_rejected(self) -> None:
        with self.assertRaises(MonetaryPrecisionError):
            toman_to_rial(-500)

        with self.assertRaises(MonetaryPrecisionError):
            validate_rial_amount(-10)

    def test_non_multiple_of_ten_rial_is_rejected(self) -> None:
        with self.assertRaises(MonetaryPrecisionError):
            validate_rial_amount(1505)

    def test_percentage_discount_calculation(self) -> None:
        # 20% discount on 1,000,000 Rials (100,000 Tomans) -> 800,000 Rials (80,000 Tomans)
        discounted = apply_percentage_discount_rial(1_000_000, Decimal("20"))
        self.assertEqual(discounted, 800_000)
        self.assertEqual( discounted % 10, 0)

        # Rounding to nearest Toman (10 Rials): 1,050 Rials (105 Tomans) with 10% discount -> 94.5 Tomans -> 95 Tomans (950 Rials)
        rounded_discount = apply_percentage_discount_rial(1_050, "10")
        self.assertEqual(rounded_discount, 950)

    def test_invalid_discount_percentage_rejected(self) -> None:
        with self.assertRaises(MonetaryPrecisionError):
            apply_percentage_discount_rial(1_000_000, -5)

        with self.assertRaises(MonetaryPrecisionError):
            apply_percentage_discount_rial(1_000_000, 105)

    def test_format_price_toman_persian_and_english(self) -> None:
        self.assertEqual(
            format_price_toman(1_250_000, use_persian_digits=True, with_unit=True),
            "۱۲۵,۰۰۰ تومان",
        )
        self.assertEqual(
            format_price_toman(1_250_000, use_persian_digits=False, with_unit=False),
            "125,000",
        )