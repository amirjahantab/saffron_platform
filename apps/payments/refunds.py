from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from .models import BankRefundReceipt
from .services.payment_service import PaymentService


@transaction.atomic
def record_bank_refund(*, order, actor, reference, amount_rial, reason, evidence_note):
    """Operator attests an already executed bank transfer; no simulated API success."""
    if not actor.is_active or not actor.is_staff or not actor.has_perm("payments.change_paymentrefund"):
        raise PermissionDenied
    if not 6 <= len(reference.strip()) <= 128 or len(evidence_note.strip()) < 12:
        raise ValidationError("شناسه بانکی معتبر و توضیح مستند استرداد الزامی است.")
    reference = reference.strip()
    if BankRefundReceipt.objects.filter(reference=reference).exists():
        raise ValidationError("این رسید بانکی قبلاً ثبت شده است.")
    BankRefundReceipt.objects.create(reference=reference, operator=actor, evidence_note=evidence_note)
    return PaymentService.refund_order_payment(order=order, actor=actor, amount_rial=amount_rial, reason=reason, confirmed_bank_reference=reference)
