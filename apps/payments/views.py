"""
HTTP Endpoints for Payment Initiation, Server-Verified Gateway Callbacks,
Payment Status Inspection, and Staff-Authorized Refunds (Sub-phase 5.2).
"""
import json
from typing import Any
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from apps.accounts.models import User
from apps.orders.models import Order
from apps.payments.exceptions import (
    InvalidPaymentStateError,
    PaymentConfigurationError,
    PaymentError,
    PaymentGatewayCommunicationError,
    PaymentVerificationFailedError,
)
from apps.payments.forms import PaymentInitiateForm, PaymentRefundForm
from apps.payments.services.payment_service import PaymentService


def _parse_request_payload(request: HttpRequest) -> dict[str, Any]:
    """Parse JSON or form-urlencoded POST payload safely."""
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            parsed = json.loads(request.body.decode("utf-8") or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}
    return request.POST.dict()


def _require_authenticated_user(request: HttpRequest) -> JsonResponse | None:
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "status": "error",
                "code": "authentication_required",
                "message": _("برای انجام عملیات پرداخت، لطفاً وارد حساب کاربری خود شوید."),
            },
            status=401,
        )
    return None


@never_cache
@require_POST
def payment_initiate_view(request: HttpRequest, order_number: str) -> JsonResponse:
    """
    Endpoint: POST /payments/initiate/<str:order_number>/
    Creates a payment transaction for an authenticated user's PENDING_PAYMENT order
    and returns the gateway redirect URL and Authority token.
    """
    auth_err = _require_authenticated_user(request)
    if auth_err is not None:
        return auth_err

    user: User = request.user  # type: ignore[assignment]
    order = get_object_or_404(
        Order.objects.filter(user=user),
        order_number=order_number.strip().upper(),
    )

    payload = _parse_request_payload(request)
    header_idem = request.headers.get("X-Idempotency-Key", "").strip()
    if header_idem and not payload.get("idempotency_key"):
        payload["idempotency_key"] = header_idem

    form = PaymentInitiateForm(data=payload)
    if not form.is_valid():
        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

    provider_code = form.cleaned_data.get("provider") or None
    idempotency_key = form.cleaned_data.get("idempotency_key") or None

    try:
        tx, redirect_url, created = PaymentService.initiate_payment(
            order=order,
            user=user,
            provider_code=provider_code,
            idempotency_key=idempotency_key,
        )
    except PaymentGatewayCommunicationError as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": exc.code,
                "message": str(exc),
            },
            status=503,
        )
    except (InvalidPaymentStateError, PaymentConfigurationError, PaymentError) as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": exc.code,
                "message": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "status": "ok",
            "created": created,
            "message": _("درخواست پرداخت ایجاد شد. در حال انتقال به درگاه بانکی..."),
            "redirect_url": redirect_url,
            "payment": PaymentService.serialize_transaction(tx),
        },
        status=201 if created else 200,
    )


@never_cache
@csrf_exempt
@require_http_methods(["GET", "POST"])
def payment_callback_view(request: HttpRequest, provider: str) -> JsonResponse:
    """
    Endpoint: GET | POST /payments/callback/<str:provider>/
    Handles the return redirect/callback from the payment gateway.
    Note: Marked `csrf_exempt` because external bank gateways redirect or POST back
    from cross-origin domains; security is strictly enforced via server-to-server
    verification (`gateway.verify_payment`) with the gateway using the stored Authority.
    """
    # Extract Authority and Status from query params (standard Zarinpal GET callback) or POST body
    authority = (
        request.GET.get("Authority")
        or request.GET.get("authority")
        or request.POST.get("Authority")
        or request.POST.get("authority")
        or ""
    ).strip()

    callback_status = (
        request.GET.get("Status")
        or request.GET.get("status")
        or request.POST.get("Status")
        or request.POST.get("status")
        or ""
    ).strip()

    try:
        tx, already_processed = PaymentService.process_callback(
            provider_code=provider,
            authority=authority,
            callback_status_param=callback_status,
        )
    except PaymentGatewayCommunicationError as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": exc.code,
                "message": str(exc),
            },
            status=503,
        )
    except PaymentVerificationFailedError as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": exc.code,
                "message": str(exc),
            },
            status=400,
        )
    except PaymentError as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": exc.code,
                "message": str(exc),
            },
            status=400,
        )

    return JsonResponse(
        {
            "status": "ok",
            "already_processed": already_processed,
            "message": _("پرداخت شما با موفقیت در سمت سرور تأیید و ثبت شد."),
            "order_number": tx.order.order_number,
            "order_status": tx.order.status,
            "payment": PaymentService.serialize_transaction(tx),
        },
        status=200,
    )


@never_cache
@require_GET
def order_payment_status_view(request: HttpRequest, order_number: str) -> JsonResponse:
    """
    Endpoint: GET /payments/order/<str:order_number>/status/
    Returns all payment attempts and current payment status for a user-owned Order.
    """
    auth_err = _require_authenticated_user(request)
    if auth_err is not None:
        return auth_err

    user: User = request.user  # type: ignore[assignment]
    order = get_object_or_404(
        Order.objects.filter(user=user).prefetch_related("payments"),
        order_number=order_number.strip().upper(),
    )

    transactions = [
        PaymentService.serialize_transaction(tx)
        for tx in order.payments.all().order_by("-created_at")
    ]
    succeeded_tx = next((t for t in transactions if t["status"]["code"] == "succeeded"), None)

    return JsonResponse(
        {
            "status": "ok",
            "order_number": order.order_number,
            "order_status": {
                "code": order.status,
                "label": order.get_status_display(),
            },
            "is_paid": order.status == Order.Status.PAID or succeeded_tx is not None,
            "succeeded_payment": succeeded_tx,
            "transactions": transactions,
        },
        status=200,
    )


@never_cache
@require_POST
def order_payment_refund_view(request: HttpRequest, order_number: str) -> JsonResponse:
    """
    Endpoint: POST /payments/order/<str:order_number>/refund/
    Staff-only endpoint to trigger a verified refund for a paid Order.
    """
    auth_err = _require_authenticated_user(request)
    if auth_err is not None:
        return auth_err

    user: User = request.user  # type: ignore[assignment]
    if not user.is_staff:
        return JsonResponse(
            {
                "status": "error",
                "code": "permission_denied",
                "message": _("فقط مدیران فروشگاه مجاز به ثبت بازگشت وجه هستند."),
            },
            status=403,
        )

    order = get_object_or_404(Order, order_number=order_number.strip().upper())
    payload = _parse_request_payload(request)
    form = PaymentRefundForm(data=payload)
    if not form.is_valid():
        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

    try:
        refund = PaymentService.refund_order_payment(
            order=order,
            reason=form.cleaned_data["reason"],
            amount_rial=form.cleaned_data.get("amount_rial"),
            actor=user,
        )
    except (InvalidPaymentStateError, PaymentError) as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": exc.code,
                "message": str(exc),
            },
            status=400,
        )

    order.refresh_from_db()
    return JsonResponse(
        {
            "status": "ok",
            "message": _("بازگشت وجه با موفقیت ثبت شد و وضعیت سفارش به‌روزرسانی گردید."),
            "order_number": order.order_number,
            "order_status": order.status,
            "refund": {
                "public_id": str(refund.public_id),
                "amount_rial": refund.amount_rial,
                "amount_toman": refund.amount_toman,
                "formatted_amount_toman": refund.formatted_amount_toman,
                "provider_refund_id": refund.provider_refund_id,
                "reason": refund.reason,
                "processed_at": refund.processed_at.isoformat() if refund.processed_at else None,
            },
        },
        status=200,
    )