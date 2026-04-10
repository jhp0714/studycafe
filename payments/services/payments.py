"""
결제 완료

order 락
이미 결제도니 주문인지 검증
payment 생성
order paid 변경
패스 발급/연장 호출
fixed/locker 최초 결제면 usage까지 같이 생성
로그 생성
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from cafe.models import LockerUsage, Pass, SeatUsage
from cafe.services.expirations import expire_duc_passes
from common.exceptions import ConflictBusinessError, NotFoundBusinessError
from logs.services import LogAction, LogEntityType, write_log
from payments.models import Order, Payment
from payments.services.passes import issue_or_extend_pass


def _sync_fixed_seat_usage(*, pass_obj:Pass, started_at) -> SeatUsage:
    """
    fixed seat는 결제 시점부터 점유
    - 첫 결제면 SeatUsage 생성
    - 연장이면 기존 SeatUsage 유지하면서 expected_end_at만 갱신
    - checkout이라는 개념이 없다.
    """
    existing_usage = (
        SeatUsage.objects
        .select_for_update()
        .filter(pass_obj=pass_obj)
        .first()
    )

    if existing_usage is None:
        try:
            seat_usage = SeatUsage.objects.create(
                user=pass_obj.user,
                pass_obj=pass_obj,
                seat=pass_obj.fixed_seat,
                check_in_at=started_at,
                expected_end_at=pass_obj.end_at,
            )
        except IntegrityError:
            raise ConflictBusinessError(
                message="지정석 점유 생성에 실패했습니다.",
                code="fixed_seat_usage_conflict",
                detail={"seat_id" : pass_obj.fixed_seat_id},
            )
        return seat_usage

    existing_usage.seat = pass_obj.fixed_seat
    existing_usage.expected_end_at = pass_obj.end_at
    existing_usage.save(update_fields=["seat","expected_end_at"])
    return existing_usage


def _sync_locker_usage(*, pass_obj:Pass, assigned_at):
    """
    locker는 결제 시점부터 점유 시작
    - 첫 결제면 LockerUsage 생성
    - 연장이면 기존 LockerUsage 유지하면서 unassign_at 갱신
    - checkout이라는 개념이 없다.
    """
    existing_usage = (
        LockerUsage.objects
        .select_for_update()
        .filter(pass_obj=pass_obj)
        .first()
    )

    if existing_usage is None :
        try :
            locker_usage = LockerUsage.objects.create(
                user=pass_obj.user,
                pass_obj=pass_obj,
                locker=pass_obj.locker,
                assign_at=assigned_at,
                unassign_at=pass_obj.end_at,
            )
        except IntegrityError :
            raise ConflictBusinessError(
                message="사물함 점유 생성에 실패했습니다.",
                code="locker_seat_usage_conflict",
                detail={"locker_id" : pass_obj.locker_id},
            )
        return locker_usage

    existing_usage.locker = pass_obj.locker
    existing_usage.unassign_at = pass_obj.end_at
    existing_usage.save(update_fields=["locker", "unassign_at"])
    return existing_usage


@transaction.atomic
def pay_order(*, user, order_id:int, payment_method:str="mock") -> tuple[Payment, Order, Pass]:
    """
    결제 완료 처리

    1. order 락
    2. created 상태 검증
    3. payment 생성
    4. pass 발급 또는 연장
    5. order.pass_obj 연결
    6. fixed/locker usage 동기화
    7. order 상태 paid 변경
    8. 로그
    """
    expire_duc_passes()     # 임시 만료처리 실행

    paid_at = timezone.now()

    order = (
        Order.objects
        .select_for_update()
        .select_related(
            "user",
            "product",
            "selected_seat",
            "selected_locker",
            "pass_obj"
        )
        .filter(id=order_id, user=user)
        .first()
    )
    if order is None:
        raise NotFoundBusinessError(
            message="주문을 찾을 수 없습니다.",
            code="order_not_found",
            detail={"order_id":order_id}
        )

    if order.status != Order.Status.CREATED:
        raise ConflictBusinessError(
            message="결제 가능한 주문 상태가 아닙니다.",
            code="order_not_payable",
            detail={"order_id" : order_id, "order_status":order.status}
        )

    if order.payments.filter(status=Payment.Status.PAID).exists():
        raise ConflictBusinessError(
            message="이미 결제된 주문입니다.",
            code="payment_already_exists",
            detail={"order_id": order.id},
        )

    payment = Payment.objects.create(
        order=order,
        amount=order.product.price,
        status=Payment.Status.PAID,
        method=payment_method,
        paid_at=paid_at,
    )

    write_log(
        actor_user=user,
        target_user=order.user,
        action=LogAction.PAYMENT_CREATED,
        entity_type=LogEntityType.PAYMENT,
        entity_id=payment.id,
        message="결제 레코드 생성",
        metadata={
            "order_id": order.id,
            "amount": payment.amount,
            "method": payment.method,
            "payment_status": payment.status,
        },
    )

    pass_obj, is_extension = issue_or_extend_pass(
        order=order,
        paid_at=paid_at,
        actor_user=user,
    )

    order.pass_obj = pass_obj
    order.status = Order.Status.PAID
    order.save(update_fields=["pass_obj", "status"])

    if pass_obj.pass_kind == Pass.PassKind.FIXED:
        seat_usage = _sync_fixed_seat_usage(
            pass_obj=pass_obj,
            started_at=paid_at,
        )

        write_log(
            actor_user=user,
            target_user=order.user,
            action=LogAction.FIXED_SEAT_CHECKED_IN,
            entity_type=LogEntityType.SEAT_USAGE,
            entity_id=seat_usage.id,
            message="지정석 점유 시작/연장",
            metadata={
                "seat_id": pass_obj.fixed_seat_id,
                "pass_id": pass_obj.id,
                "order_id": order.id,
                "expected_end_at": (
                    seat_usage.expected_end_at.isoformat()
                    if seat_usage.expected_end_at
                    else None
                ),
                "is_extension": is_extension,
            },
        )

    elif pass_obj.pass_kind == Pass.PassKind.LOCKER:
        locker_usage = _sync_locker_usage(
            pass_obj=pass_obj,
            assigned_at=paid_at,
        )

        write_log(
            actor_user=user,
            target_user=order.user,
            action=LogAction.LOCKER_ASSIGNED,
            entity_type=LogEntityType.LOCKER_USAGE,
            entity_id=locker_usage.id,
            message="사물함 점유 시작/연장",
            metadata={
                "locker_id": pass_obj.locker_id,
                "pass_id": pass_obj.id,
                "order_id": order.id,
                "unassign_at": (
                    locker_usage.unassign_at.isoformat()
                    if locker_usage.unassign_at
                    else None
                ),
                "is_extension": is_extension,
            },
        )

    write_log(
        actor_user=user,
        target_user=order.user,
        action=LogAction.PAYMENT_PAID,
        entity_type=LogEntityType.PAYMENT,
        entity_id=payment.id,
        message="결제 완료",
        metadata={
            "order_id": order.id,
            "pass_id": pass_obj.id,
            "payment_status": payment.status,
            "order_status": order.status,
            "paid_at": paid_at.isoformat(),
            "is_extension": is_extension,
        },
    )

    return payment, order, pass_obj
