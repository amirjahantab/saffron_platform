"""
Official Zarinpal v4 REST API Adapter.

Implements Zarinpal's official v4 specification:
- Request Endpoint: `/pg/v4/payment/request.json` (with explicit `"currency": "IRR"`)
- Redirect URL: `/pg/StartPay/{authority}`
- Verify Endpoint: `/pg/v4/payment/verify.json` (sending authoritative `expected_amount_rial`)
- Status Code 100: First successful verification.
- Status Code 101: Already verified (idempotent success).
"""
import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from apps.core.currency import validate_rial_amount
from apps.payments.exceptions import (
    PaymentGatewayCommunicationError,
    PaymentGatewayRejectionError,
)
from apps.payments.gateways.base import (
    BasePaymentGateway,
    PaymentRefundResult,
    PaymentRequestResult,
    PaymentVerifyResult,
)
from apps.payments.models import PaymentProvider

logger = logging.getLogger(__name__)


class ZarinpalV4Gateway(BasePaymentGateway):
    """Production-ready Zarinpal v4 payment gateway adapter."""

    provider_code = PaymentProvider.ZARINPAL

    PRODUCTION_BASE_URL = "https://payment.zarinpal.com"
    SANDBOX_BASE_URL = "https://sandbox.zarinpal.com"

    def __init__(
        self,
        merchant_id: str | None = None,
        sandbox: bool | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.merchant_id = (
            merchant_id
            if merchant_id is not None
            else str(getattr(settings, "ZARINPAL_MERCHANT_ID", ""))
        ).strip()
        self.is_sandbox = (
            sandbox
            if sandbox is not None
            else bool(getattr(settings, "ZARINPAL_SANDBOX", True))
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else int(getattr(settings, "ZARINPAL_TIMEOUT_SECONDS", 10))
        )

    @property
    def base_url(self) -> str:
        return self.SANDBOX_BASE_URL if self.is_sandbox else self.PRODUCTION_BASE_URL

    @property
    def request_endpoint(self) -> str:
        return f"{self.base_url}/pg/v4/payment/request.json"

    @property
    def verify_endpoint(self) -> str:
        return f"{self.base_url}/pg/v4/payment/verify.json"

    def build_start_pay_url(self, authority: str) -> str:
        return f"{self.base_url}/pg/StartPay/{authority}"

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute an HTTPS POST request with JSON payload and strict timeout.
        Parses JSON body even on HTTP 4xx/5xx responses to capture Zarinpal's `errors` object.
        """
        body_bytes = json.dumps(payload).encode("utf-8")
        req = Request(
            url=url,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "SaffronPlatform-ZarinpalV4/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout_seconds) as resp:
                raw_text = resp.read().decode("utf-8")
                parsed = json.loads(raw_text) if raw_text else {}
                return parsed if isinstance(parsed, dict) else {}
        except HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8")
                parsed_err = json.loads(err_body) if err_body else {}
                if isinstance(parsed_err, dict) and ("errors" in parsed_err or "data" in parsed_err):
                    return parsed_err
            except Exception:
                pass
            logger.error("Zarinpal HTTP error (%s) on %s", exc.code, url)
            raise PaymentGatewayCommunicationError(
                _("خطا در برقراری ارتباط با درگاه پرداخت زرین‌پال (کد HTTP %(code)s).")
                % {"code": exc.code}
            ) from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            logger.error("Zarinpal network/timeout error on %s: %s", url, exc)
            raise PaymentGatewayCommunicationError(
                _("امکان برقراری ارتباط با سرور درگاه پرداخت وجود ندارد. لطفاً مجدداً تلاش کنید.")
            ) from exc

    @staticmethod
    def _extract_error_details(response_data: dict[str, Any]) -> tuple[str, str]:
        """Extract error code and message from Zarinpal v4 `errors` payload."""
        errors = response_data.get("errors")
        if isinstance(errors, dict) and errors:
            code = str(errors.get("code", "unknown"))
            message = str(errors.get("message", "Unknown gateway error"))
            return code, message
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                return str(first.get("code", "unknown")), str(first.get("message", "Unknown error"))
        return "unknown", "پاسخ نامعتبر از درگاه پرداخت دریافت شد."

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
        if validated_amount < 10_000:
            raise PaymentGatewayRejectionError(
                _("حداقل مبلغ مجاز برای ارسال به درگاه بانکی ۱۰,۰۰۰ ریال (۱,۰۰۰ تومان) است.")
            )

        metadata: dict[str, str] = {"order_id": order_number}
        if customer_phone:
            metadata["mobile"] = customer_phone

        payload: dict[str, Any] = {
            "merchant_id": self.merchant_id,
            "amount": validated_amount,
            "currency": "IRR",
            "description": description[:255],
            "callback_url": callback_url,
            "metadata": metadata,
        }

        response_data = self._post_json(self.request_endpoint, payload)
        data_block = response_data.get("data")

        if isinstance(data_block, dict) and data_block.get("code") == 100:
            authority = str(data_block.get("authority", "")).strip()
            if not authority:
                raise PaymentGatewayRejectionError(_("شناسه مرجع (Authority) از درگاه پرداخت دریافت نشد."))
            raw_fee = int(data_block.get("fee", 0) or 0)
            # Round or normalize fee if needed
            fee_rial = raw_fee - (raw_fee % 10) if raw_fee > 0 else 0
            return PaymentRequestResult(
                authority=authority,
                redirect_url=self.build_start_pay_url(authority),
                fee_rial=fee_rial,
                raw_response=response_data,
            )

        err_code, err_msg = self._extract_error_details(response_data)
        logger.warning(
            "Zarinpal request_payment rejected for order=%s: code=%s msg=%s",
            order_number,
            err_code,
            err_msg,
        )
        raise PaymentGatewayRejectionError(
            _("درگاه پرداخت درخواست را رد کرد (کد خطا: %(code)s).") % {"code": err_code},
            code=f"zarinpal_{err_code}",
        )

    def verify_payment(
        self,
        *,
        authority: str,
        expected_amount_rial: int,
    ) -> PaymentVerifyResult:
        validated_amount = validate_rial_amount(expected_amount_rial)
        cleaned_authority = authority.strip()
        if not cleaned_authority:
            return PaymentVerifyResult(
                is_verified=False,
                failure_code="missing_authority",
                failure_reason=str(_("شناسه Authority برای تأیید تراکنش ارسال نشده است.")),
            )

        payload = {
            "merchant_id": self.merchant_id,
            "amount": validated_amount,
            "authority": cleaned_authority,
        }

        response_data = self._post_json(self.verify_endpoint, payload)
        data_block = response_data.get("data")

        if isinstance(data_block, dict) and data_block.get("code") in (100, 101):
            code = int(data_block["code"])
            ref_id = str(data_block.get("ref_id", "")).strip()
            card_pan = str(data_block.get("card_pan", "")).strip()
            card_hash = str(data_block.get("card_hash", "")).strip()
            raw_fee = int(data_block.get("fee", 0) or 0)
            fee_rial = raw_fee - (raw_fee % 10) if raw_fee > 0 else 0

            return PaymentVerifyResult(
                is_verified=True,
                reference_id=ref_id,
                card_pan_masked=card_pan,
                card_hash=card_hash,
                fee_rial=fee_rial,
                already_verified=(code == 101),
                raw_response=response_data,
            )

        err_code, err_msg = self._extract_error_details(response_data)
        logger.warning(
            "Zarinpal verify_payment failed for authority=%s: code=%s msg=%s",
            cleaned_authority,
            err_code,
            err_msg,
        )
        return PaymentVerifyResult(
            is_verified=False,
            failure_code=err_code,
            failure_reason=err_msg,
            raw_response=response_data,
        )

    def refund_payment(
        self,
        *,
        authority: str,
        reference_id: str,
        amount_rial: int,
        reason: str = "",
    ) -> PaymentRefundResult:
        """
        Record refund reference for Zarinpal transactions.
        (Standard Zarinpal merchant settlements use panel/GraphQL instant payout/refund APIs;
        this method generates a deterministic audit reference for the platform's refund ledger).
        """
        validate_rial_amount(amount_rial)
        if not reference_id:
            return PaymentRefundResult(
                is_succeeded=False,
                failure_reason=str(_("شماره پیگیری بانکی برای ثبت بازگشت وجه الزامی است.")),
            )
        refund_ref = f"ZP-REFUND-{reference_id}"
        return PaymentRefundResult(
            is_succeeded=True,
            provider_refund_id=refund_ref,
            raw_response={
                "status": "recorded",
                "authority": authority,
                "reference_id": reference_id,
                "amount_rial": amount_rial,
                "reason": reason,
            },
        )