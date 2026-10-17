"""
Payment Gateway Factory & Provider Registry.
Resolves gateway instances by provider code (`zarinpal`, `sandbox`).
"""
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from apps.payments.exceptions import PaymentConfigurationError
from apps.payments.gateways.base import BasePaymentGateway
from apps.payments.gateways.sandbox import SandboxPaymentGateway
from apps.payments.gateways.zarinpal import ZarinpalV4Gateway
from apps.payments.models import PaymentProvider

GATEWAY_REGISTRY: dict[str, type[BasePaymentGateway]] = {
    PaymentProvider.ZARINPAL: ZarinpalV4Gateway,
    PaymentProvider.SANDBOX: SandboxPaymentGateway,
}


def get_payment_gateway(provider_code: str | None = None) -> BasePaymentGateway:
    """
    Instantiate and return the requested payment gateway adapter.
    Defaults to `settings.PAYMENT_DEFAULT_GATEWAY`.
    """
    code = (
        provider_code
        if provider_code is not None
        else str(getattr(settings, "PAYMENT_DEFAULT_GATEWAY", PaymentProvider.SANDBOX))
    ).strip().lower()

    gateway_cls = GATEWAY_REGISTRY.get(code)
    if gateway_cls is None:
        raise PaymentConfigurationError(
            _("درگاه پرداخت درخواستی «%(provider)s» در سیستم تعریف نشده است.") % {"provider": code}
        )
    return gateway_cls()