"""
Authoritative Payment Orchestration, Server-Side Verification & Refund Service (Sub-phase 5.2).

Security & Reliability Guarantees:
1. Never trusts browser callback parameters (`Status=OK`, etc.) to mark an order as paid.
   Always executes server-to-server `gateway.verify_payment()` using the database-stored `amount_rial`.
2. Prevents duplicate callback processing (Replay / Double-Click) via row-level locks (`select_for_update`).
3. Automatically expires overdue `PENDING_PAYMENT` orders and releases their stock reservations.
4. Releases reserved stock when a payment fails or is cancelled by the user on the gateway.
5. Atomically processes full or partial refunds, restoring inventory for unshipped orders.
"""
import logging
from typing import Any
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.accounts.models import User
from apps.core.currency import validate_rial_amount
from apps.orders.models import Order
from apps.orders.services.reservation_service import OrderStateAndReservationService
from apps.payments.exceptions import (
    InvalidPaymentStateError,
    PaymentError,
    PaymentVerificationFailedError,
)
from apps.payments.gateways.registry import get_payment_gateway
from apps.payments.models import PaymentRefund, PaymentTransaction

logger = logging.getLogger("django.security")


class PaymentService:
    """Manages payment creation, server-side callback verification, and order refunds."""

    @staticmethod
    def build_callback_url(provider_code: str) -> str:
        """Construct the absolute callback URL for the given payment provider."""
        base_url = getattr(settings, "PAYMENT_CALLBACK_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        callback_path = reverse("payments:payment_callback", kwargs={"provider": provider_code})
        return f"{base_url}{callback_path}"

    @classmethod
    def initiate_payment(
        cls,
        *,
        order: Order,
        user: User | None,
        provider_code: str | None = None,
        idempotency_key: str | None = None,
        guest_token: str | None = None,
    ) -> tuple[PaymentTransaction, str, bool]:
        """
        Initiate a payment gateway session for a `PENDING_PAYMENT` order owned by `user`.
        Returns `(payment_transaction, redirect_url, created_bool)`.
        """
        cleaned_idem_key = idempotency_key.strip() if idempotency_key and idempotency_key.strip() else None
        expired_error: InvalidPaymentStateError | None = None

        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order.pk)

            from apps.orders.access import token_digest
            from secrets import compare_digest
            guest_allowed = locked_order.user_id is None and bool(guest_token) and compare_digest(token_digest(guest_token), locked_order.guest_access_hash)
            if not guest_allowed and (user is None or locked_order.user_id != user.pk):
                raise InvalidPaymentStateError(_("شما مجاز به پرداخت این سفارش نیستید."))

            if locked_order.status != Order.Status.PENDING_PAYMENT:
                raise InvalidPaymentStateError(
                    _("این سفارش در وضعیت «%(status)s» قرار دارد و قابل پرداخت نیست.")
                    % {"status": locked_order.get_status_display()}
                )

            now = timezone.now()
            if now >= locked_order.reservation_expires_at:
                # Commit expiration and stock restoration before raising the exception outside atomic block
                OrderStateAndReservationService.transition_order_status(
                    order=locked_order,
                    target_status=Order.Status.EXPIRED,
                    cancel_reason=str(_("انقضای مهلت رزرو موجودی پیش از شروع پرداخت.")),
                )
                expired_error = InvalidPaymentStateError(
                    _("مهلت رزرو این سفارش به پایان رسیده و موجودی آن آزاد شده است. لطفاً سفارش جدیدی ثبت کنید."),
                    code="order_reservation_expired",
                )
            else:
                gateway = get_payment_gateway(provider_code)
                resolved_provider = gateway.provider_code

                # Idempotency check: if client retries with the same idempotency_key, return existing INITIATED tx
                if cleaned_idem_key:
                    existing_tx = (
                        PaymentTransaction.objects.select_for_update()
                        .filter(
                            order=locked_order,
                            idempotency_key=cleaned_idem_key,
                            status=PaymentTransaction.Status.INITIATED,
                        )
                        .first()
                    )
                    if existing_tx and existing_tx.authority:
                        existing_tx.order = locked_order
                        redirect_url = existing_tx.raw_request_response.get("redirect_url") or ""
                        if not redirect_url and hasattr(gateway, "build_start_pay_url"):
                            redirect_url = gateway.build_start_pay_url(existing_tx.authority)  # type: ignore[attr-defined]
                        return existing_tx, str(redirect_url), False

                # Mark any previous abandoned INITIATED transactions for this order as EXPIRED
                PaymentTransaction.objects.filter(
                    order=locked_order,
                    status=PaymentTransaction.Status.INITIATED,
                ).update(
                    status=PaymentTransaction.Status.EXPIRED,
                    failure_reason=str(_("جایگزین‌شده با تلاش پرداخت جدید.")),
                    updated_at=now,
                )

                amount_rial = validate_rial_amount(int(locked_order.payable_rial))
                callback_url = cls.build_callback_url(resolved_provider)
                description = f"پرداخت سفارش {locked_order.order_number}"

                req_result = gateway.request_payment(
                    amount_rial=amount_rial,
                    callback_url=callback_url,
                    description=description,
                    order_number=locked_order.order_number,
                    customer_phone=locked_order.recipient_phone,
                )

                raw_req_data = dict(req_result.raw_response)
                raw_req_data["redirect_url"] = req_result.redirect_url

                tx_kwargs: dict[str, Any] = {
                    "order": locked_order,
                    "provider": resolved_provider,
                    "status": PaymentTransaction.Status.INITIATED,
                    "amount_rial": amount_rial,
                    "fee_rial": req_result.fee_rial,
                    "authority": req_result.authority,
                    "raw_request_response": raw_req_data,
                }
                if cleaned_idem_key:
                    tx_kwargs["idempotency_key"] = cleaned_idem_key

                payment_tx = PaymentTransaction(**tx_kwargs)
                payment_tx.full_clean()
                payment_tx.save()
                payment_tx.order = locked_order

                logger.info(
                    "Payment initiated: order=%s provider=%s authority=%s amount_rial=%d",
                    locked_order.order_number,
                    resolved_provider,
                    payment_tx.authority,
                    amount_rial,
                )
                return payment_tx, req_result.redirect_url, True

        assert expired_error is not None
        raise expired_error

    @classmethod
    def process_callback(
        cls,
        *,
        provider_code: str,
        authority: str,
        callback_status_param: str,
        release_reservation_on_failure: bool | None = None,
    ) -> tuple[PaymentTransaction, bool]:
        """
        Process a payment gateway callback securely and idempotently.
        Returns `(payment_transaction, already_processed_bool)`.

        CRITICAL SECURITY CONTRACT:
        - Never marks an order as `PAID` based on `callback_status_param` alone.
        - Always performs server-to-server `gateway.verify_payment()` using `payment_tx.amount_rial`.
        - Commits FAILED/CANCELLED states and stock releases before raising verification errors.
        """
        cleaned_authority = (authority or "").strip()
        cleaned_status_param = (callback_status_param or "").strip()
        cleaned_provider = (provider_code or "").strip().lower()

        if not cleaned_authority:
            raise PaymentVerificationFailedError(
                _("شناسه تراکنش (Authority) در بازگشت از درگاه یافت نشد."),
                code="missing_authority",
            )

        should_release_on_fail = (
            release_reservation_on_failure
            if release_reservation_on_failure is not None
            else bool(getattr(settings, "PAYMENT_RELEASE_RESERVATION_ON_FAILURE", True))
        )

        verification_error: PaymentVerificationFailedError | None = None
        already_processed: bool = False

        with transaction.atomic():
            try:
                payment_tx = (
                    PaymentTransaction.objects.select_for_update()
                    .select_related("order")
                    .get(provider=cleaned_provider, authority=cleaned_authority)
                )
            except PaymentTransaction.DoesNotExist as exc:
                logger.warning(
                    "Payment callback with unknown authority: provider=%s authority=%s",
                    cleaned_provider,
                    cleaned_authority,
                )
                raise PaymentVerificationFailedError(
                    _("تراکنش پرداخت منطبق با این شناسه در سیستم یافت نشد."),
                    code="transaction_not_found",
                ) from exc

            locked_order = Order.objects.select_for_update().get(pk=payment_tx.order_id)
            payment_tx.order = locked_order

            # 1. Idempotency Guard: If already SUCCEEDED, return immediately without re-mutating state
            if payment_tx.status == PaymentTransaction.Status.SUCCEEDED:
                logger.info(
                    "Idempotent callback replay ignored for already succeeded tx: order=%s authority=%s",
                    locked_order.order_number,
                    cleaned_authority,
                )
                return payment_tx, True

            # 2. If transaction was already terminal (FAILED / EXPIRED / REFUNDED), reject replay
            if payment_tx.status in (
                PaymentTransaction.Status.FAILED,
                PaymentTransaction.Status.EXPIRED,
                PaymentTransaction.Status.REFUNDED,
            ):
                raise PaymentVerificationFailedError(
                    _("این تراکنش قبلاً تعیین تکلیف شده و دیگر معتبر نیست (وضعیت: %(status)s).")
                    % {"status": payment_tx.get_status_display()},
                    code="transaction_already_terminal",
                )

            payment_tx.callback_status_param = cleaned_status_param[:32]
            now = timezone.now()

            # 3. Check if browser status parameter explicitly indicates user cancellation / failure
            if cleaned_status_param.upper() not in ("OK", "SUCCESS", "1"):
                payment_tx.status = PaymentTransaction.Status.FAILED
                payment_tx.failure_code = "user_cancelled_or_nok"
                payment_tx.failure_reason = str(
                    _("پرداخت توسط کاربر لغو شد یا درگاه وضعیت ناموفق برگرداند.")
                )
                payment_tx.save(
                    update_fields=[
                        "callback_status_param",
                        "status",
                        "failure_code",
                        "failure_reason",
                        "updated_at",
                    ]
                )
                cls._handle_order_on_failed_payment(
                    order=locked_order,
                    now=now,
                    should_release_on_fail=should_release_on_fail,
                    reason=str(_("انصراف کاربر یا عدم موفقیت در درگاه پرداخت.")),
                )
                verification_error = PaymentVerificationFailedError(
                    _("پرداخت انجام نشد یا توسط کاربر لغو گردید."),
                    code="payment_cancelled_by_user",
                )

            # 4. Verify that the order is still eligible to be paid before calling gateway verify
            elif locked_order.status != Order.Status.PENDING_PAYMENT:
                payment_tx.status = PaymentTransaction.Status.FAILED
                payment_tx.failure_code = f"order_status_{locked_order.status}"
                payment_tx.failure_reason = str(
                    _("وضعیت سفارش پیش از تأیید تراکنش تغییر کرده است (%(status)s).")
                    % {"status": locked_order.get_status_display()}
                )
                payment_tx.save(
                    update_fields=[
                        "callback_status_param",
                        "status",
                        "failure_code",
                        "failure_reason",
                        "updated_at",
                    ]
                )
                verification_error = PaymentVerificationFailedError(
                    _("مهلت پرداخت این سفارش به پایان رسیده یا سفارش لغو شده است."),
                    code="order_not_payable",
                )

            else:
                # 5. Mandatory Server-to-Server Verification with authoritative database amount_rial
                gateway = get_payment_gateway(cleaned_provider)
                verify_result = gateway.verify_payment(
                    authority=cleaned_authority,
                    expected_amount_rial=int(payment_tx.amount_rial),
                )

                if not verify_result.is_verified or not verify_result.reference_id:
                    payment_tx.status = PaymentTransaction.Status.FAILED
                    payment_tx.failure_code = (verify_result.failure_code or "verify_rejected")[:64]
                    payment_tx.failure_reason = (
                        verify_result.failure_reason
                        or str(_("تأییدیه تراکنش از سرور بانک دریافت نشد."))
                    )[:255]
                    payment_tx.raw_verify_response = verify_result.raw_response
                    payment_tx.save(
                        update_fields=[
                            "callback_status_param",
                            "status",
                            "failure_code",
                            "failure_reason",
                            "raw_verify_response",
                            "updated_at",
                        ]
                    )
                    cls._handle_order_on_failed_payment(
                        order=locked_order,
                        now=now,
                        should_release_on_fail=should_release_on_fail,
                        reason=str(_("عدم تأیید تراکنش در استعلام سمت سرور از درگاه بانکی.")),
                    )
                    logger.warning(
                        "Server-side payment verification FAILED: order=%s authority=%s code=%s",
                        locked_order.order_number,
                        cleaned_authority,
                        payment_tx.failure_code,
                    )
                    verification_error = PaymentVerificationFailedError(
                        _("تراکنش بانکی در استعلام سمت سرور تأیید نشد."),
                        code="server_verification_rejected",
                    )
                else:
                    # 6. Verification Succeeded: Transition Order to PAID (committing stock reservations)
                    updated_order = OrderStateAndReservationService.transition_order_status(
                        order=locked_order,
                        target_status=Order.Status.PAID,
                    )
                    payment_tx.order = updated_order

                    payment_tx.status = PaymentTransaction.Status.SUCCEEDED
                    payment_tx.reference_id = verify_result.reference_id.strip()
                    payment_tx.card_pan_masked = verify_result.card_pan_masked[:32]
                    payment_tx.card_hash = verify_result.card_hash[:128]
                    if verify_result.fee_rial > 0:
                        payment_tx.fee_rial = verify_result.fee_rial
                    payment_tx.raw_verify_response = verify_result.raw_response
                    payment_tx.verified_at = now
                    payment_tx.full_clean()
                    payment_tx.save()
                    already_processed = verify_result.already_verified

                    logger.info(
                        "Payment verified and Order marked PAID: order=%s ref_id=%s amount_rial=%d",
                        updated_order.order_number,
                        payment_tx.reference_id,
                        payment_tx.amount_rial,
                    )

        if verification_error is not None:
            raise verification_error

        return payment_tx, already_processed

    @staticmethod
    def _handle_order_on_failed_payment(
        *,
        order: Order,
        now: Any,
        should_release_on_fail: bool,
        reason: str,
    ) -> None:
        """
        Release stock reservations when a payment callback fails or is cancelled.
        If the order's reservation window has elapsed, marks the order `EXPIRED`;
        otherwise, if `should_release_on_fail` is enabled, transitions the order to `CANCELLED`
        and restores its reserved stock back to the catalog.
        """
        if order.status != Order.Status.PENDING_PAYMENT:
            return

        if now >= order.reservation_expires_at:
            OrderStateAndReservationService.transition_order_status(
                order=order,
                target_status=Order.Status.EXPIRED,
                cancel_reason=str(_("انقضای مهلت پرداخت پس از بازگشت ناموفق از درگاه.")),
            )
        elif should_release_on_fail:
            OrderStateAndReservationService.transition_order_status(
                order=order,
                target_status=Order.Status.CANCELLED,
                cancel_reason=reason,
            )

    @classmethod
    def refund_order_payment(
        cls,
        *,
        order: Order,
        reason: str,
        amount_rial: int | None = None,
        actor: User | None = None,
        confirmed_bank_reference: str | None = None,
    ) -> PaymentRefund:
        """
        Execute a verified refund for a paid Order, record `PaymentRefund`,
        restore committed inventory if the order has not yet been shipped,
        and transition both `Order` and `PaymentTransaction` to `REFUNDED`.
        """
        cleaned_reason = (reason or "").strip() or str(_("بازگشت وجه سفارش"))

        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order.pk)

            refundable_order_statuses = {
                Order.Status.PAID,
                Order.Status.PROCESSING,
                Order.Status.SHIPPED,
                Order.Status.DELIVERED,
            }
            if locked_order.status not in refundable_order_statuses:
                raise InvalidPaymentStateError(
                    _("سفارش در وضعیت «%(status)s» قابلیت ثبت بازگشت وجه را ندارد.")
                    % {"status": locked_order.get_status_display()}
                )

            payment_tx = (
                PaymentTransaction.objects.select_for_update()
                .filter(
                    order=locked_order,
                    status=PaymentTransaction.Status.SUCCEEDED,
                )
                .first()
            )
            if payment_tx is None or not payment_tx.reference_id:
                raise InvalidPaymentStateError(
                    _("تراکنش پرداخت موفقی برای این سفارش یافت نشد.")
                )

            refund_amount = (
                validate_rial_amount(int(amount_rial))
                if amount_rial is not None
                else int(payment_tx.amount_rial)
            )

            already_refunded = int(
                locked_order.refunds.filter(status=PaymentRefund.Status.SUCCEEDED)
                .aggregate(total=Sum("amount_rial"))
                .get("total")
                or 0
            )
            if already_refunded + refund_amount > int(payment_tx.amount_rial):
                raise InvalidPaymentStateError(
                    _("مجموع مبلغ استرداد نمی‌تواند از مبلغ کل تراکنش پرداخت‌شده بیشتر باشد.")
                )

            if confirmed_bank_reference is not None:
                from apps.payments.gateways.base import PaymentRefundResult
                from apps.payments.models import BankRefundReceipt
                if not actor or not actor.is_active or not actor.is_staff or not actor.has_perm("payments.change_paymentrefund"):
                    raise PaymentError("اجازه ثبت رسید بانکی ندارید.")
                receipt = BankRefundReceipt.objects.select_for_update().filter(reference=confirmed_bank_reference, operator=actor, refund__isnull=True).first()
                if not receipt:
                    raise PaymentError("رسید رزروشده استرداد یافت نشد.")
                refund_res = PaymentRefundResult(is_succeeded=True, provider_refund_id=confirmed_bank_reference)
            else:
                gateway = get_payment_gateway(payment_tx.provider)
                refund_res = gateway.refund_payment(
                    authority=payment_tx.authority or "", reference_id=payment_tx.reference_id,
                    amount_rial=refund_amount, reason=cleaned_reason,
                )
            if not refund_res.is_succeeded:
                raise PaymentError(
                    refund_res.failure_reason or str(_("خطا در ثبت بازگشت وجه در درگاه پرداخت.")),
                    code="refund_failed",
                )

            now = timezone.now()
            refund_record = PaymentRefund(
                payment=payment_tx,
                order=locked_order,
                amount_rial=refund_amount,
                status=PaymentRefund.Status.SUCCEEDED,
                reason=cleaned_reason[:255],
                provider_refund_id=refund_res.provider_refund_id,
                processed_by=actor,
                processed_at=now,
            )
            refund_record.full_clean()
            refund_record.save()
            if confirmed_bank_reference is not None:
                receipt.refund = refund_record
                receipt.save(update_fields=["refund", "updated_at"])

            # Restore committed inventory if the order was not yet shipped
            fully_refunded = already_refunded + refund_amount == int(payment_tx.amount_rial)
            if fully_refunded and locked_order.status in (Order.Status.PAID, Order.Status.PROCESSING):
                OrderStateAndReservationService._restore_committed_stock_on_post_payment_cancel(
                    locked_order
                )

            if fully_refunded:
                OrderStateAndReservationService.transition_order_status(
                    order=locked_order, target_status=Order.Status.REFUNDED, cancel_reason=cleaned_reason,
                )
                payment_tx.status = PaymentTransaction.Status.REFUNDED
                payment_tx.save(update_fields=["status", "updated_at"])

            logger.info(
                "Order payment refunded: order=%s refund_id=%s amount_rial=%d",
                locked_order.order_number,
                refund_record.provider_refund_id,
                refund_amount,
            )
            return refund_record

    @staticmethod
    def serialize_transaction(tx: PaymentTransaction) -> dict[str, Any]:
        """Serialize a PaymentTransaction with Rial and Toman details."""
        return {
            "public_id": str(tx.public_id),
            "order_number": tx.order.order_number,
            "provider": {
                "code": tx.provider,
                "label": tx.get_provider_display(),
            },
            "status": {
                "code": tx.status,
                "label": tx.get_status_display(),
            },
            "amount_rial": tx.amount_rial,
            "amount_toman": tx.amount_toman,
            "formatted_amount_toman": tx.formatted_amount_toman,
            "fee_rial": tx.fee_rial,
            "authority": tx.authority,
            "reference_id": tx.reference_id,
            "card_pan_masked": tx.card_pan_masked,
            "failure_code": tx.failure_code,
            "failure_reason": tx.failure_reason,
            "verified_at": tx.verified_at.isoformat() if tx.verified_at else None,
            "created_at": tx.created_at.isoformat(),
        }
