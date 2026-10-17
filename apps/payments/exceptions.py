"""Domain exceptions for payment gateways, transaction verification, and refunds."""
from apps.core.exceptions import SaffronBaseError


class PaymentError(SaffronBaseError):
    """Base exception for all payment-related errors."""

    default_code = "payment_error"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code


class PaymentGatewayCommunicationError(PaymentError):
    """Raised when network/HTTP communication with the external payment gateway fails."""

    default_code = "gateway_communication_error"


class PaymentGatewayRejectionError(PaymentError):
    """Raised when the payment gateway rejects a payment creation or refund request."""

    default_code = "gateway_rejected"


class PaymentVerificationFailedError(PaymentError):
    """Raised when server-side payment verification fails or detects tampering."""

    default_code = "verification_failed"


class InvalidPaymentStateError(PaymentError):
    """Raised when an operation is attempted on a payment or order in an invalid state."""

    default_code = "invalid_payment_state"


class PaymentConfigurationError(PaymentError):
    """Raised when a requested payment provider is unknown or misconfigured."""

    default_code = "payment_configuration_error"