"""Custom infrastructure and monetary domain exceptions."""


class SaffronBaseError(Exception):
    """Base exception for all custom platform errors."""


class MonetaryPrecisionError(SaffronBaseError, ValueError):
    """Raised when a float or invalid monetary value violates the currency contract."""