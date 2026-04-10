from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from cafe.models import LockerUsage, Pass, SeatUsage
from common.exceptions import (
    ConflictBusinessError,
    NotFoundBusinessError,
    RefundError,
    ValidationBusinessError,
)
from logs.services import LogAction, LogEntityType, write_log
from payments.models import Order, Payment, Refund


def _validate_refundable_payment(*, payment: Payment, refund_amount: int) -> None:
    if payment.status != Payment.Status.PAID:
        raise ConflictBusinessError(
            message="환불 가능한 결제 상태가 아닙니다.",
            code="payment_not_refundable",
            detail={
                "payment_id": payment.id,
                "payment_status": payment.status,
            },
        )

    if refund_amount != payment.amount:
        raise ValidationBusinessError(
            message="현재는 전액 환불만 가능합니다.",
            code="full_refund_only",
            detail={
                "payment_id": payment.id,
                "payment_amount": payment.amount,
                "refund_amount": refund_amount,
            },
        )


def _assert_latest_paid_order_for_pass(*, order: Order) -> None:
    """
    현재 구조에서는 같은 pass를 여러 order가 연장할 수 있으므로
    과거 결제를 중간에 환불하면 현재 권리 계산이 꼬일 수 있다.

    따라서 지금 단계에서는
    '해당 pass에 연결된 최신 paid order'만 환불 허용
    """
    pass_obj = order.pass_obj
    if pass_obj is None:
        return

    latest_paid_order = (
        Order.objects
        .select_for_update()
        .filter(
            pass_obj=pass_obj,
            status=Order.Status.PAID,
        )
        .order_by("-id")
        .first()
    )

    if latest_paid_order and latest_paid_order.id != order.id:
        raise ConflictBusinessError(
            message="현재 이용권에 대한 최신 결제만 환불할 수 있습니다.",
            code="latest_paid_order_only_refundable",
            detail={
                "order_id": order.id,
                "latest_paid_order_id": latest_paid_order.id,
                "pass_id": pass_obj.id,
            },
        )


def _cleanup_pass_usage(*, pass_obj: Pass) -> dict:
    deleted_seat_usage_ids: list[int] = []
    deleted_locker_usage_ids: list[int] = []

    seat_usages = list(
        SeatUsage.objects
        .select_for_update()
        .filter(pass_obj=pass_obj)
        .order_by("id")
    )
    if seat_usages:
        deleted_seat_usage_ids = [usage.id for usage in seat_usages]
        SeatUsage.objects.filter(id__in=deleted_seat_usage_ids).delete()

    locker_usages = list(
        LockerUsage.objects
        .select_for_update()
        .filter(pass_obj=pass_obj)
        .order_by("id")
    )
    if locker_usages:
        deleted_locker_usage_ids = [usage.id for usage in locker_usages]
        LockerUsage.objects.filter(id__in=deleted_locker_usage_ids).delete()

    return {
        "deleted_seat_usage_ids": deleted_seat_usage_ids,
        "deleted_locker_usage_ids": deleted_locker_usage_ids,
    }


def _cancel_related_pass(*, pass_obj: Pass | None, canceled_at, actor_user=None) -> dict:
    if pass_obj is None:
        return {
            "pass_canceled": False,
            "deleted_seat_usage_ids": [],
            "deleted_locker_usage_ids": [],
        }

    cleanup_result = _cleanup_pass_usage(pass_obj=pass_obj)

    pass_obj.status = Pass.Status.CANCELED
    pass_obj.save(update_fields=["status"])

    write_log(
        actor_user=actor_user,
        target_user=pass_obj.user,
        action=LogAction.PASS_CANCELED,
        entity_type=LogEntityType.PASS,
        entity_id=pass_obj.id,
        message="환불로 인한 이용권 취소",
        metadata={
            "pass_id": pass_obj.id,
            "pass_kind": pass_obj.pass_kind,
            "canceled_at": canceled_at.isoformat(),
            "deleted_seat_usage_ids": cleanup_result["deleted_seat_usage_ids"],
            "deleted_locker_usage_ids": cleanup_result["deleted_locker_usage_ids"],
        },
    )

    return {
        "pass_canceled": True,
        "deleted_seat_usage_ids": cleanup_result["deleted_seat_usage_ids"],
        "deleted_locker_usage_ids": cleanup_result["deleted_locker_usage_ids"],
    }


@transaction.atomic
def create_refund(
    *,
    admin_user,
    payment_id: int,
    amount: int | None = None,
    reason: str | None = None,
) -> Refund:
    """
    환불 처리

    현재 기준:
    - 전액 환불만 허용
    - 현재 pass에 연결된 최신 paid order만 환불 허용
    """
    refunded_at = timezone.now()

    payment = (
        Payment.objects
        .select_for_update()
        .select_related(
            "order",
            "order__user",
            "order__pass_obj",
            "order__pass_obj__product",
        )
        .filter(id=payment_id)
        .first()
    )
    if payment is None:
        raise NotFoundBusinessError(
            message="결제를 찾을 수 없습니다.",
            code="payment_not_found",
            detail={"payment_id": payment_id},
        )

    refund_amount = payment.amount if amount is None else amount
    _validate_refundable_payment(payment=payment, refund_amount=refund_amount)

    order = payment.order
    _assert_latest_paid_order_for_pass(order=order)

    refund = Refund.objects.create(
        payment=payment,
        admin_user=admin_user,
        amount=refund_amount,
        reason=reason or "",
        status=Refund.Status.APPROVED,
        refunded_at=refunded_at,
    )

    write_log(
        actor_user=admin_user,
        target_user=order.user,
        action=LogAction.REFUND_CREATED,
        entity_type=LogEntityType.REFUND,
        entity_id=refund.id,
        message="환불 생성",
        metadata={
            "payment_id": payment.id,
            "order_id": order.id,
            "refund_amount": refund_amount,
            "reason": reason,
        },
    )

    payment.status = Payment.Status.REFUNDED
    payment.save(update_fields=["status"])

    order.status = Order.Status.CANCELED
    order.save(update_fields=["status"])

    cancel_result = _cancel_related_pass(
        pass_obj=order.pass_obj,
        canceled_at=refunded_at,
        actor_user=admin_user,
    )

    write_log(
        actor_user=admin_user,
        target_user=order.user,
        action=LogAction.REFUND_COMPLETED,
        entity_type=LogEntityType.REFUND,
        entity_id=refund.id,
        message="환불 완료",
        metadata={
            "payment_id": payment.id,
            "order_id": order.id,
            "refund_amount": refund_amount,
            "reason": reason,
            "pass_id": order.pass_obj_id,
            "pass_canceled": cancel_result["pass_canceled"],
            "deleted_seat_usage_ids": cancel_result["deleted_seat_usage_ids"],
            "deleted_locker_usage_ids": cancel_result["deleted_locker_usage_ids"],
        },
    )

    return refund