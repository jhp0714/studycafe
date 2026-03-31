"""
패스 발급/연장

상품 타입별 패스 발급
기존 결제된 패스 연장
time:remaing_minutes 설정
flat/fixed/locker:end_at연장
fixed/locker는 좌석/사물함 id 유지
생태 갱신
로그 생성
"""

from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError
from django.utils import timezone

from cafe.models import Pass
from common.exceptions import (
    ConflictBusinessError,
    PassError,
    ValidationBusinessError,
)
from logs.services import LogAction, LogEntityType, write_log
from payments.models import Order

def get_active_pass_for_update(*, user, pass_kind:str) -> Pass | None:
    return(
        Pass.objects
        .select_for_update()
        .select_related("fixed_seat","locker","product")
        .filter(
            user=user,
            pass_kind=pass_kind,
            status=Pass.Status.ACTIVE,
        )
        .order_by("id")
        .first()
    )


def refresh_pass_status(*, pass_obj:Pass, now=None) -> Pass:
    """
    현재 시점 기준으로 pass 상태 정리
    - time : remaiining_minutes <= 0 이면 expired
    - flat/fixed/locker : end_at <= now 이면 expired
    """
    current_time = now or timezone.now()

    if pass_obj.status == Pass.Status.CANCELED:
        return pass_obj

    if pass_obj.pass_kind == Pass.PassKind.TIME:
        remaining = pass_obj.remaining_minutes or 0
        pass_obj.status = (
            Pass.Status.EXPIRED if remaining <= 0 else Pass.Status.ACTIVE
        )
    else:
        if pass_obj.end_at is None:
            raise PassError(
                message="기간제 패스의 종료 시간이 없습니다.",
                code="pass_end_at_required",
                detail={"pass_id":pass_obj.id},
            )

        pass_obj.status = (
            Pass.Status.EXPIRED
            if pass_obj.end_at <= current_time
            else Pass.Status.ACTIVE
        )

    pass_obj.save(update_fields=["status"])
    return pass_obj


def _calculate_time_remaining_minutes(*, product, existing_pass: Pass | None) -> int:
    """
    시간제 패스 남은 시간 계산
    - 신규 : 상품 시간만 반영
    - 연장 : 기존 남은 시간 + 상품 시간
    """
    add_minutes = (product.duration_hours or 0) * 60
    base_minutes = 0

    if existing_pass and existing_pass.status == Pass.Status.ACTIVE:
        base_minutes = existing_pass.remaining_minutes or 0

    return base_minutes + add_minutes


def _calculate_period_end_at(*, product, existing_pass:Pass|None, now):
    """
    기간제 종료 시간 계산
    - 신규 : now + duration_days
    - 연장 : 기존 end_at이 미래면 기존 end_at부터 연장
    """

    base_time = now

    if existing_pass and existing_pass.end_at and existing_pass.end_at > now:
        base_time = existing_pass.end_at

    return base_time + timedelta(days=(product.duration_days or 0))


def _create_new_pass(*, order:Order, paid_at, actor_user=None)->Pass:
    """
    신규 pass 생성
    """
    product = order.product
    pass_kind = product.product_type

    pass_obj = Pass(
        user=order.user,
        product=product,
        pass_kind=pass_kind,
        status=Pass.Status.ACTIVE,
        start=paid_at,
    )

    if pass_kind == Pass.PassKind.TIME:
        pass_obj.remaining_minutes = _calculate_time_remaining_minutes(
            product=product,
            existing_pass=None,
        )
    elif pass_kind == Pass.PassKind.FLAT:
        pass_obj.end_at = _calculate_period_end_at(
            product=product,
            existing_pass=None,
            now=paid_at,
        )
    elif pass_kind == Pass.PassKind.FIXED:
        if order.selected_seat_id is None:
            raise ValidationBusinessError(
                message="지정석 상품은 첫 결제 시 좌석 선택이 필요합니다.",
                code="fixed_seat_required",
                detail={"order_id":order.id},
            )

        pass_obj.fixed_seat = order.selected_seat
        pass_obj.end_at = _calculate_period_end_at(
            product=product,
            existing_pass=None,
            now=paid_at,
        )

    elif pass_kind == Pass.PassKind.LOCKER:
        if order.selected_locker_id is None:
            raise ValidationBusinessError(
                message="사물함 상품은 첫 결제 시 사물함 선택이 필요합니다.",
                code="locker_required",
                detail={"order_id":order.id},
            )

        pass_obj.locker = order.selected_locker
        pass_obj.end_at = -_calculate_period_end_at(
            product=product,
            existing_pass=None,
            now=paid_at,
        )

    else:
        raise PassError(
            message="지원하지 않는 pass_kind 입니다.",
            code="unsupported_pass_kind",
            detail={"pass_kind":pass_kind}
        )

    try:
        pass_obj.full_clean()
        pass_obj.save()
    except IntegrityError:
        if pass_kind == Pass.PassKind.FIXED:
            raise ConflictBusinessError(
                message="이미 사용 중인 지정석입니다.",
                code="fixe_seat_not_available",
                detail={"seat_id" : order.selected_seat_id},
            )
        if pass_kind == Pass.PassKind.LOCKER:
            raise ConflictBusinessError(
                message="이미 사용 중인 사물함입니다.",
                code="locker_not_available",
                detail={"seat_id" : order.selected_locker_id},
            )
        raise

    write_log(
        actor_user=actor_user,
        target_user=order.user,
        action=LogAction.PASS_ISSUED,
        entity_type=LogEntityType.PASS,
        entity_id=pass_obj.id,
        message="패스 발급 완료",
        metadata={
            "order_id":order.id,
            "product_id":product.id,
            "pass_kind":pass_kind,
            "remaining_minutes":pass_obj.remaining_minutes,
            "end_at":pass_obj.end_at.isoformat() if pass_obj.end_at else None,
            "fixed_seat_id":pass_obj.fixed_seat_id,
            "locker_id":pass_obj.locker_id,
        },
    )

    return pass_obj


def _extend_existing_pass(*, order:Order, existing_pass:Pass, paid_at, actor_user=None,)->Pass:
    """
    active pass를 그대로 연장
    - time : remaining_minutes 누적
    - flat/fixed/locker : end_at 연장
    - fixed/locker : 기존 좌석/사물함 점유 유지
    """
    product = order.product

    if existing_pass.status != Pass.Status.ACTIVE:
        raise PassError(
            message="활성 상태의 패스만 연장할 수 있습니다.",
            code="pass_not_active",
            detail={
                "pass_id":existing_pass.id,
                "status":existing_pass.status,
            }
        )

    existing_pass.product = product

    if existing_pass.pass_kind == Pass.PassKind.TIME:
        existing_pass.remaining_minutes = _calculate_time_remaining_minutes(
            product=product, existing_pass=existing_pass,
        )

    elif existing_pass.pass_kind in (
        Pass.PassKind.FLAT, Pass.PassKind.FIXED, Pass.PassKind.LOCKER,
    ):
        existing_pass.end_at = _calculate_period_end_at(
            product=product, existing_pass=existing_pass, now=paid_at
        )

    else:
        raise PassError(
            message="지원하지 않는 pass_kind입니다.",
            code="unsupported_pass_kind",
            detail={"pass_kind" : existing_pass.pass_kind},
        )

    try:
        existing_pass.full_clean()
        existing_pass.save()
    except IntegrityError:
        if existing_pass.pass_kind == Pass.PassKind.FIXED:
            raise ConflictBusinessError(
                message="이미 사용 중인 지정석입니다.",
                code="fixed_seat_not_available",
                detail={"seat_id" : existing_pass.fixed_seat_id},
            )
        if existing_pass.pass_kind == Pass.PassKind.LOCKER :
            raise ConflictBusinessError(
                message="이미 사용 중인 사물함입니다.",
                code="locker_not_available",
                detail={"locker_id" : existing_pass.locker_id},
            )
        raise

    write_log(
        actor_user=actor_user,
        target_user=order.user,
        action=LogAction.PASS_EXTENDED,
        entity_type=LogEntityType.PASS,
        entity_id=existing_pass.id,
        message="패스 연장 완료",
        metadata={
            "order_id" : order.id,
            "product_id" : product.id,
            "pass_kind" : existing_pass.pass_kind,
            "remaining_minutes" : existing_pass.remaining_minutes,
            "end_at" : existing_pass.end_at.isoformat() if existing_pass.end_at else None,
            "fixed_seat_id" : existing_pass.fixed_seat_id,
            "locker_id" : existing_pass.locker_id,
        },
    )

    return existing_pass


def issue_or_extend_pass(*, order:Order, paid_at=None, actor_user=None) -> tuple[Pass, bool]:
    """
    services/passes.py 외부 공개 함수
    - active pass 가 없으면 신규 생성, 있으면 연장
    """
    current_time = paid_at or timezone.now()
    pass_kind = order.product.primary_type

    existing_pass = get_active_pass_for_update(user=order.user, pass_kind=pass_kind)

    if existing_pass is None:
        pass_obj = _create_new_pass(order=order, paid_at=current_time,actor_user=actor_user)
        return pass_obj, False

    pass_obj = _extend_existing_pass(
        order=order,
        existing_pass=existing_pass,
        paid_at=current_time,
        actor_user=actor_user,
    )
    return pass_obj, True