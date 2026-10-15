"""
Authentication endpoints for OTP request, OTP verification (login/register),
session status inspection, and secure CSRF-protected logout.
"""
import json
from typing import Any
from django.conf import settings
from django.contrib.auth import login, logout
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from apps.accounts.forms import OTPRequestForm, OTPVerifyForm
from apps.accounts.models import User
from apps.accounts.services.otp_service import (
    OTPInvalidError,
    OTPRateLimitError,
    OTPService,
)
from apps.accounts.services.sms_provider import SMSDeliveryError
from apps.accounts.signals import user_logged_in_via_otp
from apps.accounts.validators import mask_phone_number


def _extract_client_ip(request: HttpRequest) -> str:
    """
    Extract client IP safely.
    Uses REMOTE_ADDR by default; only trusts X-Forwarded-For when SECURE_PROXY_SSL_HEADER is active.
    """
    if getattr(settings, "USE_X_FORWARDED_HOST", False):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or "unknown"


def _parse_request_data(request: HttpRequest) -> dict[str, Any]:
    """Support both application/json and standard form-urlencoded POST bodies."""
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}
    return request.POST.dict()


@never_cache
@require_POST
def otp_request_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: POST /accounts/otp/request/
    Validates Iranian mobile number, enforces rate limits, and sends a 6-digit OTP via SMS.
    """
    payload = _parse_request_data(request)
    form = OTPRequestForm(data=payload)
    if not form.is_valid():
        return JsonResponse(
            {"status": "error", "errors": form.errors},
            status=400,
        )

    phone_number = form.cleaned_data["phone_number"]
    client_ip = _extract_client_ip(request)

    try:
        result = OTPService.request_otp(raw_phone=phone_number, client_ip=client_ip)
    except OTPRateLimitError as exc:
        response = JsonResponse(
            {
                "status": "error",
                "code": "rate_limited",
                "message": str(exc),
                "retry_after": exc.retry_after,
            },
            status=429,
        )
        response["Retry-After"] = str(exc.retry_after)
        return response
    except SMSDeliveryError as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": "sms_delivery_failed",
                "message": str(exc),
            },
            status=503,
        )

    return JsonResponse(
        {
            "status": "ok",
            "message": _("کد تایید به شماره موبایل شما ارسال شد."),
            "masked_phone": mask_phone_number(result.phone_number),
            "expires_in": result.expires_in,
            "cooldown_seconds": result.cooldown_seconds,
        },
        status=200,
    )


@never_cache
@require_POST
def otp_verify_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: POST /accounts/otp/verify/
    Verifies the OTP code, creates/activates the User account atomically,
    rotates session key to prevent Session Fixation, and emits cart-merge signal.
    """
    payload = _parse_request_data(request)
    form = OTPVerifyForm(data=payload)
    if not form.is_valid():
        return JsonResponse(
            {"status": "error", "errors": form.errors},
            status=400,
        )

    phone_number = form.cleaned_data["phone_number"]
    code = form.cleaned_data["code"]
    client_ip = _extract_client_ip(request)

    try:
        verified_phone = OTPService.verify_otp(
            raw_phone=phone_number,
            raw_code=code,
            client_ip=client_ip,
        )
    except OTPRateLimitError as exc:
        response = JsonResponse(
            {
                "status": "error",
                "code": "rate_limited",
                "message": str(exc),
                "retry_after": exc.retry_after,
            },
            status=429,
        )
        response["Retry-After"] = str(exc.retry_after)
        return response
    except OTPInvalidError as exc:
        return JsonResponse(
            {
                "status": "error",
                "code": "invalid_otp",
                "message": str(exc),
            },
            status=400,
        )

    with transaction.atomic():
        user, created = User.objects.select_for_update().get_or_create(
            phone_number=verified_phone,
            defaults={"is_active": True, "is_phone_verified": True},
        )
        if not user.is_active:
            return JsonResponse(
                {
                    "status": "error",
                    "code": "account_disabled",
                    "message": _("حساب کاربری شما غیرفعال شده است."),
                },
                status=403,
            )

        now = timezone.now()
        user.is_phone_verified = True
        user.last_otp_verified_at = now
        user.save(update_fields=["is_phone_verified", "last_otp_verified_at", "updated_at"])

    # Capture guest session key prior to login rotation for Phase 4 cart merging
    pre_login_session_key = request.session.session_key

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)

    user_logged_in_via_otp.send(
        sender=User,
        user=user,
        request=request,
        pre_login_session_key=pre_login_session_key,
    )

    return JsonResponse(
        {
            "status": "ok",
            "message": _("ورود با موفقیت انجام شد."),
            "is_new_user": created,
            "user": {
                "public_id": str(user.public_id),
                "phone_number": user.phone_number,
                "full_name": user.full_name,
            },
        },
        status=200,
    )


@never_cache
@require_POST
def logout_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: POST /accounts/logout/
    Strictly requires POST (CSRF-protected) and completely flushes the active session.
    """
    logout(request)
    return JsonResponse(
        {
            "status": "ok",
            "message": _("خروج از حساب کاربری با موفقیت انجام شد."),
        },
        status=200,
    )


@never_cache
@ensure_csrf_cookie
@require_GET
def session_status_view(request: HttpRequest) -> JsonResponse:
    """
    Endpoint: GET /accounts/me/
    Returns current user profile if authenticated, or 401 if anonymous.
    Also ensures CSRF cookie is set for frontend clients.
    """
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "status": "unauthenticated",
                "is_authenticated": False,
            },
            status=401,
        )

    user: User = request.user  # type: ignore[assignment]
    return JsonResponse(
        {
            "status": "ok",
            "is_authenticated": True,
            "user": {
                "public_id": str(user.public_id),
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "is_phone_verified": user.is_phone_verified,
            },
        },
        status=200,
    )