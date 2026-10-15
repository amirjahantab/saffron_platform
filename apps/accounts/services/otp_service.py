"""
Cryptographically secure OTP generation, salted hashing, rate-limiting, and verification service.
"""
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from apps.accounts.services.sms_provider import SMSDeliveryError, get_sms_provider
from apps.accounts.validators import mask_phone_number, normalize_iranian_phone, normalize_digits_to_ascii
from apps.core.exceptions import SaffronBaseError

logger = logging.getLogger("django.security")

PBKDF2_ITERATIONS = 100_000


class OTPError(SaffronBaseError):
    """Base exception for OTP operations."""


class OTPRateLimitError(OTPError):
    """Raised when OTP request or verification exceeds rate limits."""

    def __init__(self, message: str, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


class OTPInvalidError(OTPError):
    """Raised when an OTP code is invalid, expired, or exhausted."""


@dataclass(frozen=True)
class OTPDispatchResult:
    phone_number: str
    expires_in: int
    cooldown_seconds: int


class OTPService:
    """
    Manages the full lifecycle of One-Time Passwords backed by Redis cache.
    """

    @staticmethod
    def _challenge_key(phone_number: str) -> str:
        return f"otp:challenge:{phone_number}"

    @staticmethod
    def _cooldown_key(phone_number: str) -> str:
        return f"otp:cooldown:{phone_number}"

    @staticmethod
    def _phone_hourly_key(phone_number: str) -> str:
        return f"otp:rl:phone:{phone_number}"

    @staticmethod
    def _ip_hourly_key(client_ip: str) -> str:
        return f"otp:rl:ip:{client_ip}"

    @staticmethod
    def generate_secure_code(length: int | None = None) -> str:
        """Generate a cryptographically random numeric OTP using CSPRNG (`secrets`)."""
        code_length = length or int(getattr(settings, "OTP_CODE_LENGTH", 6))
        if code_length < 4 or code_length > 10:
            raise ValueError("OTP_CODE_LENGTH must be between 4 and 10.")
        upper_bound = 10**code_length
        return f"{secrets.randbelow(upper_bound):0{code_length}d}"

    @staticmethod
    def hash_otp(code: str, salt: str, phone_number: str) -> str:
        """
        Compute a salted, domain-bound PBKDF2-HMAC-SHA256 hash of the OTP code.
        Binding `phone_number` into the key material prevents cross-user hash substitution.
        """
        key_material = f"{phone_number}:{code}:{settings.SECRET_KEY}".encode("utf-8")
        salt_bytes = salt.encode("utf-8")
        derived = hashlib.pbkdf2_hmac("sha256", key_material, salt_bytes, PBKDF2_ITERATIONS)
        return derived.hex()

    @classmethod
    def verify_hash_constant_time(cls, code: str, salt: str, phone_number: str, expected_hash: str) -> bool:
        """Verify an OTP hash using constant-time comparison (`secrets.compare_digest`)."""
        candidate_hash = cls.hash_otp(code=code, salt=salt, phone_number=phone_number)
        return secrets.compare_digest(candidate_hash, expected_hash)

    @staticmethod
    def _increment_window_counter(cache_key: str, window_seconds: int) -> int:
        """Atomically increment a rate-limit counter in cache and ensure TTL is set."""
        created = cache.add(cache_key, 1, timeout=window_seconds)
        if created:
            return 1
        try:
            return int(cache.incr(cache_key))
        except ValueError:
            cache.set(cache_key, 1, timeout=window_seconds)
            return 1

    @classmethod
    def request_otp(cls, raw_phone: str, client_ip: str = "unknown") -> OTPDispatchResult:
        """
        Validate phone number, enforce multi-layer rate limits, store hashed OTP in Redis,
        and dispatch the code via the configured SMS provider.
        """
        phone_number = normalize_iranian_phone(raw_phone)
        masked_phone = mask_phone_number(phone_number)

        expiry_seconds = int(getattr(settings, "OTP_EXPIRY_SECONDS", 120))
        cooldown_seconds = int(getattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 120))
        max_phone_hourly = int(getattr(settings, "OTP_MAX_REQUESTS_PER_HOUR_PHONE", 5))
        max_ip_hourly = int(getattr(settings, "OTP_MAX_REQUESTS_PER_HOUR_IP", 10))

        # 1. Check active per-phone resend cooldown
        cooldown_key = cls._cooldown_key(phone_number)
        cooldown_until = cache.get(cooldown_key)
        now_ts = int(time.time())
        if cooldown_until is not None and int(cooldown_until) > now_ts:
            remaining = int(cooldown_until) - now_ts
            logger.warning(
                "OTP cooldown violation for phone=%s ip=%s remaining=%ds",
                masked_phone,
                client_ip,
                remaining,
            )
            raise OTPRateLimitError(
                _("لطفاً پیش از درخواست مجدد کد، کمی صبر کنید."),
                retry_after=remaining,
            )

        # 2. Check hourly IP rate limit (check before incrementing phone counter)
        ip_key = cls._ip_hourly_key(client_ip)
        current_ip_count = int(cache.get(ip_key, 0))
        if current_ip_count >= max_ip_hourly:
            logger.warning("OTP IP hourly rate limit exceeded for ip=%s", client_ip)
            raise OTPRateLimitError(
                _("تعداد درخواست‌های شما بیش از حد مجاز است. لطفاً یک ساعت دیگر تلاش کنید."),
                retry_after=3600,
            )

        # 3. Check hourly phone rate limit
        phone_key = cls._phone_hourly_key(phone_number)
        current_phone_count = int(cache.get(phone_key, 0))
        if current_phone_count >= max_phone_hourly:
            logger.warning("OTP phone hourly rate limit exceeded for phone=%s ip=%s", masked_phone, client_ip)
            raise OTPRateLimitError(
                _("تعداد دفعات ارسال پیامک برای این شماره به سقف مجاز ساعتی رسیده است."),
                retry_after=3600,
            )

        # 4. Generate OTP and Salted Hash
        code = cls.generate_secure_code()
        salt = secrets.token_hex(16)
        code_hash = cls.hash_otp(code=code, salt=salt, phone_number=phone_number)
        expires_at = now_ts + expiry_seconds

        challenge_payload = {
            "hash": code_hash,
            "salt": salt,
            "attempts": 0,
            "expires_at": expires_at,
        }

        # 5. Dispatch SMS first; only commit rate limits if SMS gateway accepts the message
        sms_provider = get_sms_provider()
        try:
            sent = sms_provider.send_otp(phone_number=phone_number, code=code)
            if not sent:
                raise SMSDeliveryError("SMS provider returned unsuccessful status.")
        except Exception as exc:
            logger.error("Failed to dispatch OTP SMS to %s: %s", masked_phone, exc)
            raise SMSDeliveryError(_("خطا در ارسال پیامک. لطفاً دقایقی دیگر تلاش کنید.")) from exc

        # 6. Persist challenge, cooldown, and increment hourly counters
        cache.set(cls._challenge_key(phone_number), challenge_payload, timeout=expiry_seconds)
        cache.set(cooldown_key, now_ts + cooldown_seconds, timeout=cooldown_seconds)
        cls._increment_window_counter(phone_key, 3600)
        cls._increment_window_counter(ip_key, 3600)

        logger.info("OTP challenge created for phone=%s ip=%s", masked_phone, client_ip)
        return OTPDispatchResult(
            phone_number=phone_number,
            expires_in=expiry_seconds,
            cooldown_seconds=cooldown_seconds,
        )

    @classmethod
    def verify_otp(cls, raw_phone: str, raw_code: str, client_ip: str = "unknown") -> str:
        """
        Verify a submitted OTP code against the active Redis challenge.
        Enforces expiration, brute-force attempt caps, and single-use deletion.
        Returns the normalized phone_number upon success.
        """
        phone_number = normalize_iranian_phone(raw_phone)
        masked_phone = mask_phone_number(phone_number)
        code = normalize_digits_to_ascii(str(raw_code)).strip()

        expected_length = int(getattr(settings, "OTP_CODE_LENGTH", 6))
        if not code.isdigit() or len(code) != expected_length:
            raise OTPInvalidError(_("کد تایید واردشده نامعتبر است."))

        challenge_key = cls._challenge_key(phone_number)
        challenge = cache.get(challenge_key)

        if not isinstance(challenge, dict):
            logger.warning("OTP verification failed (missing/expired) for phone=%s ip=%s", masked_phone, client_ip)
            raise OTPInvalidError(_("کد تایید منقضی شده یا وجود ندارد. لطفاً کد جدیدی درخواست کنید."))

        now_ts = int(time.time())
        expires_at = int(challenge.get("expires_at", 0))
        if now_ts >= expires_at:
            cache.delete(challenge_key)
            logger.warning("OTP verification failed (timestamp expired) for phone=%s ip=%s", masked_phone, client_ip)
            raise OTPInvalidError(_("مهلت استفاده از این کد به پایان رسیده است."))

        max_attempts = int(getattr(settings, "OTP_MAX_VERIFY_ATTEMPTS", 5))
        attempts = int(challenge.get("attempts", 0))

        if attempts >= max_attempts:
            cache.delete(challenge_key)
            logger.warning("OTP challenge invalidated (max attempts) for phone=%s ip=%s", masked_phone, client_ip)
            raise OTPRateLimitError(
                _("تعداد تلاش‌های ناموفق بیش از حد مجاز بود. کد فعلی باطل شد."),
                retry_after=60,
            )

        is_valid = cls.verify_hash_constant_time(
            code=code,
            salt=str(challenge["salt"]),
            phone_number=phone_number,
            expected_hash=str(challenge["hash"]),
        )

        if not is_valid:
            attempts += 1
            remaining_ttl = max(1, expires_at - now_ts)
            if attempts >= max_attempts:
                cache.delete(challenge_key)
                logger.warning(
                    "OTP brute-force threshold reached; challenge deleted for phone=%s ip=%s",
                    masked_phone,
                    client_ip,
                )
                raise OTPRateLimitError(
                    _("تعداد تلاش‌های ناموفق بیش از حد مجاز بود. کد فعلی باطل شد."),
                    retry_after=remaining_ttl,
                )

            challenge["attempts"] = attempts
            cache.set(challenge_key, challenge, timeout=remaining_ttl)
            logger.warning(
                "Invalid OTP attempt (%d/%d) for phone=%s ip=%s",
                attempts,
                max_attempts,
                masked_phone,
                client_ip,
            )
            raise OTPInvalidError(_("کد تایید واردشده صحیح نیست."))

        # Single-use enforcement: immediately purge challenge and cooldown on success
        cache.delete(challenge_key)
        cache.delete(cls._cooldown_key(phone_number))
        logger.info("OTP verified successfully for phone=%s ip=%s", masked_phone, client_ip)
        return phone_number