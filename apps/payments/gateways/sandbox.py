"""
Deterministic In-Memory Sandbox Payment Gateway Adapter.
Designed for local engineering and automated testing without external network calls.
"""
import hashlib
import secrets
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from apps.core.currency import validate_rial_amount
from apps.payments.exceptions import PaymentGatewayRejectionError
from apps.payments.gateways.base import (
    BasePaymentGateway,
    PaymentRefundResult,
    PaymentRequestResult,
    PaymentVerifyResult,
)
from apps.payments.models import PaymentProvider


class SandboxPaymentGateway(BasePaymentGateway):
    """
    Local sandbox payment provider.
    Allows tests and local developers to simulate successful, failed, tampered,
    or duplicate payment verifications deterministically.
    """

    provider_code = PaymentProvider.SANDBOX

    # In-memory registry of issued sandbox authorities:
    # {authority: {"amount_rial": int, "order_number": str, "verified_ref_id": str | None, "force_fail": bool}}
    _issued_authorities: dict[str, dict[str, object]] = {}

    @classmethod
    def clear_state(cls) -> None:
        """Reset in-memory sandbox state between tests."""
        cls._issued_authorities.clear()

    @classmethod
    def mark_authority_to_fail_verification(cls, authority: str) -> None:
        """Helper for security tests to simulate a payment where browser says OK but server verify fails."""
        if authority in cls._issued_authorities:
            cls._issued_authorities[authority]["force_fail"] = True

    def request_payment(
        self,
        *,
        amount_rial: int,
        callback_url: str,
        description: str,
        order_number: str,
        customer_phone: str = "",
    ) -> PaymentRequestResult:
        validated_amount = validate_rial_amount(amount_rial)
        if validated_amount <= 0:
            raise PaymentGatewayRejectionError(_("مبلغ تراکنش باید بزرگ‌تر از صفر باشد."))

        authority = f"SBX-{secrets.token_hex(12).upper()}"
        self.__class__._issued_authorities[authority] = {
            "amount_rial": validated_amount,
            "order_number": order_number,
            "verified_ref_id": None,
            "force_fail": False,
        }

        base_url = getattr(settings, "PAYMENT_CALLBACK_BASE_URL", "http://127.0.0.1:8000")
        redirect_url = f"{base_url}/payments/sandbox-gateway/{authority}/"

        return PaymentRequestResult(
            authority=authority,
            redirect_url=redirect_url,
            fee_rial=0,
            raw_response={
                "provider": "sandbox",
                "code": 100,
                "authority": authority,
                "amount_rial": validated_amount,
            },
        )

    def verify_payment(
        self,
        *,
        authority: str,
        expected_amount_rial: int,
    ) -> PaymentVerifyResult:
        validated_expected = validate_rial_amount(expected_amount_rial)
        cleaned_authority = authority.strip()
        record = self.__class__._issued_authorities.get(cleaned_authority)

        if record is None:
            return PaymentVerifyResult(
                is_verified=False,
                failure_code="-54",
                failure_reason=str(_("شناسه مرجع (Authority) در درگاه آزمایشی یافت نشد.")),
                raw_response={"code": -54, "message": "Invalid authority"},
            )

        if record.get("force_fail"):
            return PaymentVerifyResult(
                is_verified=False,
                failure_code="-51",
                failure_reason=str(_("تراکنش در استعلام سمت سرور توسط بانک تأیید نشد.")),
                raw_response={"code": -51, "message": "Session is not valid or payment failed"},
            )

        recorded_amount = int(record["amount_rial"])  # type: ignore[arg-type]
        if recorded_amount != validated_expected:
            return PaymentVerifyResult(
                is_verified=False,
                failure_code="-50",
                failure_reason=str(_("مبلغ تراکنش با مبلغ پرداخت‌شده در درگاه مطابقت ندارد.")),
                raw_response={
                    "code": -50,
                    "message": "Amount mismatch",
                    "expected": validated_expected,
                    "recorded": recorded_amount,
                },
            )

        existing_ref = record.get("verified_ref_id")
        already_verified = existing_ref is not None
        if existing_ref:
            ref_id = str(existing_ref)
        else:
            digest = hashlib.sha256(cleaned_authority.encode("utf-8")).hexdigest()[:10].upper()
            ref_id = f"SBX-REF-{digest}"
            record["verified_ref_id"] = ref_id

        card_hash = hashlib.sha256(f"603799******1234:{cleaned_authority}".encode("utf-8")).hexdigest()
        return PaymentVerifyResult(
            is_verified=True,
            reference_id=ref_id,
            card_pan_masked="603799******1234",
            card_hash=card_hash,
            fee_rial=0,
            already_verified=already_verified,
            raw_response={
                "code": 101 if already_verified else 100,
                "ref_id": ref_id,
                "card_pan": "603799******1234",
            },
        )

    def refund_payment(
        self,
        *,
        authority: str,
        reference_id: str,
        amount_rial: int,
        reason: str = "",
    ) -> PaymentRefundResult:
        validate_rial_amount(amount_rial)
        if not reference_id:
            return PaymentRefundResult(
                is_succeeded=False,
                failure_reason=str(_("شماره پیگیری تراکنش برای استرداد الزامی است.")),
            )
        refund_id = f"SBX-RFD-{secrets.token_hex(6).upper()}"
        return PaymentRefundResult(
            is_succeeded=True,
            provider_refund_id=refund_id,
            raw_response={
                "code": 100,
                "refund_id": refund_id,
                "amount_rial": amount_rial,
                "reason": reason,
            },
        )