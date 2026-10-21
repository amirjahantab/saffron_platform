"""
Abstract SMS Provider Interface and Sandbox Implementation.
Guarantees zero vendor lock-in and prevents plaintext OTP leakage in production logs.
"""
from abc import ABC, abstractmethod
import logging
import json
import re
from urllib.request import Request, urlopen
from urllib.parse import urlencode
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

    def send_message(self, phone_number: str, message: str) -> bool:
        raise SMSDeliveryError("This SMS provider does not implement notifications.")


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

        logger.info("[SANDBOX SMS] OTP dispatched to %s (code hidden)", masked)

        return True

    def send_message(self, phone_number: str, message: str) -> bool:
        if getattr(settings, "OTP_SANDBOX_STORE_OUTBOX", False):
            self.__class__.outbox.append({"phone_number": phone_number, "message": message})
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


class KavenegarSMSProvider(BaseSMSProvider):
    """Official HTTPS verify/lookup and sms/send REST endpoints; no secret logging."""

    def _send(self, method, payload):
        key = settings.KAVENEGAR_API_KEY
        if not key or not re.fullmatch(r"[A-Za-z0-9]+", key):
            raise SMSDeliveryError("SMS credentials are not configured.")
        request = Request(f"https://api.kavenegar.com/v1/{key}/{method}.json", data=urlencode(payload).encode(), method="POST")
        try:
            with urlopen(request, timeout=10) as response:
                result = json.loads(response.read(65536))
            if result.get("return", {}).get("status") != 200:
                raise SMSDeliveryError("SMS provider rejected the message.")
            return True
        except (OSError, ValueError) as exc:
            raise SMSDeliveryError("SMS provider communication failed.") from None

    def send_otp(self, phone_number, code):
        if not settings.KAVENEGAR_OTP_TEMPLATE:
            raise SMSDeliveryError("OTP template is not configured.")
        return self._send("verify/lookup", {"receptor": phone_number, "token": code, "template": settings.KAVENEGAR_OTP_TEMPLATE, "type": "sms"})

    def send_message(self, phone_number, message):
        if not settings.KAVENEGAR_SENDER:
            raise SMSDeliveryError("SMS sender is not configured.")
        return self._send("sms/send", {"receptor": phone_number, "sender": settings.KAVENEGAR_SENDER, "message": message})
