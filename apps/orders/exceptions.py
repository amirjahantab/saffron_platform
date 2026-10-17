"""Domain exceptions for shopping cart, inventory reservation, and order operations."""
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


class OrderError(SaffronBaseError):
    """Base exception for order lifecycle and reservation operations."""

    default_code = "order_error"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code


class EmptyCartCheckoutError(OrderError):
    """Raised when attempting to checkout with an empty or non-existent cart."""

    default_code = "empty_cart"


class InvalidOrderStateTransitionError(OrderError):
    """Raised when an illegal order status transition is attempted."""

    default_code = "invalid_state_transition"


class StockReservationError(OrderError):
    """Raised when stock reservation creation, commitment, or release fails."""

    default_code = "stock_reservation_error"


class OrderAccessDeniedError(OrderError):
    """Raised when a user attempts to access an order belonging to another user."""

    default_code = "order_access_denied"