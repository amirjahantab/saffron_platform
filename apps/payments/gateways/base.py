"""
Unified Abstract Payment Gateway Contract.
All payment gateway adapters (Zarinpal, Sandbox, or future Shaparak/IPG providers)
must inherit from `BasePaymentGateway` and return these immutable dataclasses.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PaymentRequestResult:
    """Result returned by a payment provider when initiating a payment session."""

    authority: str
    redirect_url: str
    fee_rial: int = 0
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentVerifyResult:
    """
    Authoritative server-side verification result returned by a payment provider.
    Note: `already_verified=True` indicates the gateway confirmed this transaction was
    previously verified (e.g. Zarinpal status code 101).
    """

    is_verified: bool
    reference_id: str = ""
    card_pan_masked: str = ""
    card_hash: str = ""
    fee_rial: int = 0
    already_verified: bool = False
    failure_code: str = ""
    failure_reason: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentRefundResult:
    """Result of a refund request submitted to the payment provider."""

    is_succeeded: bool
    provider_refund_id: str = ""
    failure_reason: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


class BasePaymentGateway(ABC):
    """Abstract base interface for all Iranian IPG payment adapters."""

    provider_code: str = ""

    @abstractmethod
    def request_payment(
        self,
        *,
        amount_rial: int,
        callback_url: str,
        description: str,
        order_number: str,
        customer_phone: str = "",
    ) -> PaymentRequestResult:
        """
        Initiate a payment request with the gateway for `amount_rial` (in integer Rials).
        Raises `PaymentGatewayCommunicationError` or `PaymentGatewayRejectionError` on failure.
        """

    @abstractmethod
    def verify_payment(
        self,
        *,
        authority: str,
        expected_amount_rial: int,
    ) -> PaymentVerifyResult:
        """
        Perform authoritative server-to-server verification of a payment callback.
        Must send `expected_amount_rial` (from the server database, NEVER from client query params)
        to the gateway's verification endpoint.
        """

    @abstractmethod
    def refund_payment(
        self,
        *,
        authority: str,
        reference_id: str,
        amount_rial: int,
        reason: str = "",
    ) -> PaymentRefundResult:
        """Initiate or record a refund for a previously verified payment."""