"""Domain exceptions for shopping cart, inventory, and order operations."""
from apps.core.exceptions import SaffronBaseError


class CartError(SaffronBaseError):
    """Base exception for shopping cart operations."""

    default_code = "cart_error"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code


class CartItemUnavailableError(CartError):
    """Raised when a requested product or variant is inactive or does not exist."""

    default_code = "variant_unavailable"


class InsufficientStockError(CartError):
    """Raised when requested quantity exceeds available variant stock."""

    default_code = "insufficient_stock"


class CartQuantityBoundsError(CartError):
    """Raised when requested quantity violates min_order_quantity or max_order_quantity."""

    default_code = "invalid_quantity_bounds"