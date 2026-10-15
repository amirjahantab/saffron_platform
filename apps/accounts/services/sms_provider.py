"""
Abstract SMS Provider Interface and Sandbox Implementation.
Guarantees zero vendor lock-in and prevents plaintext OTP leakage in production logs.
"""
from abc import ABC, abstractmethod
import logging
from django.conf import settings
from django.utils.module_loading import import_string
from apps.accounts.validators import mask_phone_number
from apps.core.exceptions import SaffronBaseError

logger = logging.getLogger(__name__)


class SMSDeliveryError(SaffronBaseError):
    """Raised when an SMS provider fails to dispatch a message."""


class BaseSMSProvider(ABC):
    """Abstract contract that all SMS gateway adapters must implement."""

    @abstractmethod
    def send_otp(self, phone_number: str, code: str) -> bool:
        """Send an OTP code to the normalized Iranian phone number."""


class SandboxSMSProvider(BaseSMSProvider):
    """
    Sandbox SMS provider for local development and automated testing.
    Security controls:
    - Never logs plaintext OTP codes when DEBUG is False.
    - Stores messages in `outbox` ONLY when `settings.OTP_SANDBOX_STORE_OUTBOX` is True (test environment).
    """

    outbox: list[dict[str, str]] = []

    def send_otp(self, phone_number: str, code: str) -> bool:
        masked = mask_phone_number(phone_number)

        if getattr(settings, "OTP_SANDBOX_STORE_OUTBOX", False):
            self.__class__.outbox.append({"phone_number": phone_number, "code": code})

        if settings.DEBUG:
            logger.info("[SANDBOX SMS] OTP dispatched to %s | Code: %s", masked, code)
        else:
            logger.info("[SANDBOX SMS] OTP dispatched to %s (code hidden in non-debug mode)", masked)

        return True

    @classmethod
    def clear_outbox(cls) -> None:
        """Clear the in-memory test outbox."""
        cls.outbox.clear()


def get_sms_provider() -> BaseSMSProvider:
    """Instantiate and return the configured SMS provider adapter."""
    provider_path = getattr(
        settings,
        "SMS_PROVIDER_CLASS",
        "apps.accounts.services.sms_provider.SandboxSMSProvider",
    )
    provider_cls = import_string(provider_path)
    provider = provider_cls()
    if not isinstance(provider, BaseSMSProvider):
        raise TypeError(f"Configured SMS_PROVIDER_CLASS '{provider_path}' must inherit from BaseSMSProvider.")
    return provider