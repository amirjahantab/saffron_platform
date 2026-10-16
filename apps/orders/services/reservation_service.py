"""
Order State Machine & Inventory Reservation Lifecycle Service (Sub-phase 4.2).

Guarantees:
1. Atomic stock deduction when creating a reservation (`select_for_update`).
2. Strict idempotency when releasing or expiring reservations (stock is never restored twice).
3. Validated order state transitions (`ALLOWED_STATUS_TRANSITIONS`).
4. Batch expiration of overdue `PENDING_PAYMENT` orders and their active stock reservations.
"""
import logging
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.catalog.models import ProductVariant
from apps.orders.exceptions import (
    InsufficientStockError,
    InvalidOrderStateTransitionError,
    StockReservationError,
)
from apps.orders.models import Order, StockReservation

logger = logging.getLogger(__name__)

ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    Order.Status.PENDING_PAYMENT: {
        Order.Status.PAID,
        Order.Status.CANCELLED,
        Order.Status.EXPIRED,
    },
    Order.Status.PAID: {
        Order.Status.PROCESSING,
        Order.Status.CANCELLED,
        Order.Status.REFUNDED,
    },
    Order.Status.PROCESSING: {
        Order.Status.SHIPPED,
        Order.Status.CANCELLED,
        Order.Status.REFUNDED,
    },
    Order.Status.SHIPPED: {
        Order.Status.DELIVERED,
        Order.Status.REFUNDED,
    },
    Order.Status.DELIVERED: {
        Order.Status.REFUNDED,
    },
    Order.Status.CANCELLED: set(),
    Order.Status.EXPIRED: set(),
    Order.Status.REFUNDED: set(),
}


class OrderStateAndReservationService:
    """Manages atomic inventory reservations and order status transitions."""

    @classmethod
    def reserve_variant_stock(
        cls,
        order: Order,
        variant_id: int,
        quantity: int,
    ) -> StockReservation:
        """
        Atomically lock the ProductVariant row, verify available stock, deduct `quantity`,
        and create an ACTIVE StockReservation tied to `order.reservation_expires_at`.
        """
        if quantity < 1:
            raise StockReservationError(_("تعداد رزرو موجودی باید حداقل ۱ عدد باشد."))

        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order.pk)
            if locked_order.status != Order.Status.PENDING_PAYMENT:
                raise StockReservationError(
                    _("رزرو موجودی فقط برای سفارش‌های در وضعیت «در انتظار پرداخت» مجاز است.")
                )

            variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
            if not variant.is_active:
                raise StockReservationError(
                    _("گونه محصول %(sku)s غیرفعال است و امکان رزرو ندارد.") % {"sku": variant.sku}
                )
            if variant.stock_quantity < quantity:
                raise InsufficientStockError(
                    _("موجودی گونه %(sku)s کافی نیست (موجودی فعلی: %(stock)d، درخواستی: %(req)d).")
                    % {"sku": variant.sku, "stock": variant.stock_quantity, "req": quantity}
                )

            variant.stock_quantity -= quantity
            variant.save(update_fields=["stock_quantity", "updated_at"])

            reservation = StockReservation.objects.create(
                order=locked_order,
                variant=variant,
                quantity=quantity,
                status=StockReservation.Status.ACTIVE,
                expires_at=locked_order.reservation_expires_at,
            )
            logger.info(
                "Reserved stock: order=%s variant=%s qty=%d remaining_stock=%d",
                locked_order.order_number,
                variant.sku,
                quantity,
                variant.stock_quantity,
            )
            return reservation

    @classmethod
    def release_order_reservations(
        cls,
        order: Order,
        mark_as_expired: bool = False,
    ) -> int:
        """
        Idempotently release all ACTIVE reservations for an order and restore stock
        to the respective ProductVariant rows in deterministic PK order (preventing deadlocks).
        Returns the number of reservations released.
        """
        target_res_status = (
            StockReservation.Status.EXPIRED
            if mark_as_expired
            else StockReservation.Status.RELEASED
        )

        with transaction.atomic():
            active_reservations = list(
                StockReservation.objects.select_for_update()
                .filter(order=order, status=StockReservation.Status.ACTIVE)
                .order_by("variant_id")
            )
            if not active_reservations:
                return 0

            variant_ids = [res.variant_id for res in active_reservations]
            locked_variants = {
                v.pk: v
                for v in ProductVariant.objects.select_for_update()
                .filter(pk__in=variant_ids)
                .order_by("pk")
            }

            now = timezone.now()
            for res in active_reservations:
                variant = locked_variants[res.variant_id]
                variant.stock_quantity += res.quantity
                variant.save(update_fields=["stock_quantity", "updated_at"])

                res.status = target_res_status
                res.released_at = now
                res.save(update_fields=["status", "released_at", "updated_at"])

            logger.info(
                "Released %d stock reservation(s) for order=%s (status=%s)",
                len(active_reservations),
                order.order_number,
                target_res_status,
            )
            return len(active_reservations)

    @classmethod
    def commit_order_reservations(cls, order: Order) -> int:
        """
        Transition all ACTIVE reservations for `order` to COMMITTED upon verified payment.
        Raises StockReservationError if reservations were already expired or released.
        """
        with transaction.atomic():
            reservations = list(
                StockReservation.objects.select_for_update()
                .filter(order=order)
                .order_by("id")
            )
            if not reservations:
                raise StockReservationError(_("هیچ رکورد رزرو موجودی برای این سفارش یافت نشد."))

            now = timezone.now()
            committed_count = 0
            for res in reservations:
                if res.status == StockReservation.Status.COMMITTED:
                    continue
                if res.status != StockReservation.Status.ACTIVE:
                    raise StockReservationError(
                        _("رزرو موجودی این سفارش قبلاً آزاد یا منقضی شده است و امکان قطعی‌سازی ندارد.")
                    )
                res.status = StockReservation.Status.COMMITTED
                res.committed_at = now
                res.save(update_fields=["status", "committed_at", "updated_at"])
                committed_count += 1

            return committed_count

    @classmethod
    def transition_order_status(
        cls,
        order: Order,
        target_status: str,
        cancel_reason: str = "",
        tracking_code: str = "",
    ) -> Order:
        """
        Validate and execute an order status transition atomically.
        Automatically commits or releases inventory reservations based on the target status.
        """
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order.pk)
            current_status = locked_order.status

            if current_status == target_status:
                return locked_order

            allowed_targets = ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
            if target_status not in allowed_targets:
                raise InvalidOrderStateTransitionError(
                    _(
                        "تغییر وضعیت سفارش از «%(current)s» به «%(target)s» مجاز نیست."
                    )
                    % {
                        "current": locked_order.get_status_display(),
                        "target": dict(Order.Status.choices).get(target_status, target_status),
                    }
                )

            now = timezone.now()
            update_fields = ["status", "updated_at"]

            if target_status == Order.Status.PAID:
                cls.commit_order_reservations(locked_order)
                locked_order.paid_at = now
                update_fields.append("paid_at")

            elif target_status == Order.Status.EXPIRED:
                cls.release_order_reservations(locked_order, mark_as_expired=True)
                locked_order.cancelled_at = now
                locked_order.cancel_reason = cancel_reason or str(
                    _("انقضای خودکار به دلیل عدم تکمیل پرداخت در مهلت مقرر.")
                )
                update_fields.extend(["cancelled_at", "cancel_reason"])

            elif target_status == Order.Status.CANCELLED:
                # If cancelled while still PENDING_PAYMENT, release active reservations.
                # If cancelled after PAID/PROCESSING, also restore committed stock.
                if current_status == Order.Status.PENDING_PAYMENT:
                    cls.release_order_reservations(locked_order, mark_as_expired=False)
                else:
                    cls._restore_committed_stock_on_post_payment_cancel(locked_order)
                locked_order.cancelled_at = now
                if cancel_reason:
                    locked_order.cancel_reason = cancel_reason
                    update_fields.append("cancel_reason")
                update_fields.append("cancelled_at")

            elif target_status == Order.Status.SHIPPED:
                locked_order.shipped_at = now
                update_fields.append("shipped_at")
                if tracking_code:
                    locked_order.tracking_code = tracking_code.strip()
                    update_fields.append("tracking_code")

            elif target_status == Order.Status.DELIVERED:
                locked_order.delivered_at = now
                update_fields.append("delivered_at")

            locked_order.status = target_status
            locked_order.save(update_fields=update_fields)
            order.refresh_from_db()
            return locked_order

    @classmethod
    def _restore_committed_stock_on_post_payment_cancel(cls, order: Order) -> None:
        """Restore stock if an already-paid order is cancelled before shipment."""
        committed_reservations = list(
            StockReservation.objects.select_for_update()
            .filter(order=order, status=StockReservation.Status.COMMITTED)
            .order_by("variant_id")
        )
        if not committed_reservations:
            return

        variant_ids = [res.variant_id for res in committed_reservations]
        locked_variants = {
            v.pk: v
            for v in ProductVariant.objects.select_for_update()
            .filter(pk__in=variant_ids)
            .order_by("pk")
        }
        now = timezone.now()
        for res in committed_reservations:
            variant = locked_variants[res.variant_id]
            variant.stock_quantity += res.quantity
            variant.save(update_fields=["stock_quantity", "updated_at"])

            res.status = StockReservation.Status.RELEASED
            res.released_at = now
            res.save(update_fields=["status", "released_at", "updated_at"])

    @classmethod
    def expire_overdue_reservations(cls) -> int:
        """
        Find all `PENDING_PAYMENT` orders whose `reservation_expires_at` has passed,
        transition them to `EXPIRED`, and atomically return their reserved stock to inventory.
        Returns the count of expired orders.
        """
        now = timezone.now()
        overdue_order_ids = list(
            Order.objects.filter(
                status=Order.Status.PENDING_PAYMENT,
                reservation_expires_at__lte=now,
            ).values_list("id", flat=True)
        )

        expired_count = 0
        for order_id in overdue_order_ids:
            try:
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(pk=order_id)
                    if order.status == Order.Status.PENDING_PAYMENT and order.reservation_expires_at <= now:
                        cls.transition_order_status(
                            order=order,
                            target_status=Order.Status.EXPIRED,
                        )
                        expired_count += 1
            except Exception as exc:
                logger.error("Failed to expire overdue order_id=%s: %s", order_id, exc)

        return expired_count