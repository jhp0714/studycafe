"""
시간 연장

현재 입실 중인지 확인
time 상품이면 구매한 상품 시간 만큼 연장
flat 상품이면 한 번만 연장 시 최대 6시간(만약 가지고 있는 상품의 남은 시간이 부족하면 부족한만큼만 연장)
로그 생성
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from cafe.models import Pass, Seat, SeatUsage
from common.exceptions import ConflictBusinessError, NotFoundBusinessError, ValidationBusinessError
from logs.services import LogAction, LogEntityType, write_log


def _get_current_normal_seat_usage_for_update(*, user) -> SeatUsage:
    seat_usage = (
        SeatUsage.objects
        .select_for_update()
        .filter(user=user)
        .first()
    )

    if seat_usage is None :
        raise NotFoundBusinessError(
            message="현재 사용 중인 좌석이 없습니다.",
            code="seat_usage_not_found",
        )

    if seat_usage.seat.seat_type != Seat.SeatType.NORMAL :
        raise ValidationBusinessError(
            message="일반석만 시간 연장할 수 있습니다.",
            code="normal_seat_extension_only",
            detail={
                "seat_usage_id" : seat_usage.id,
                "seat_type" : seat_usage.seat.seat_type,
            },
        )

    return seat_usage


def _calculate_extendable_end_at(*, pass_obj:Pass,current_expected_end_at,request_hours:int):
    """
    연장 후 expected_end_at 계산
    - 한 번에 최대 6시간
    - time : 남은 minutes을 넘길 수 없음
    - flat : pass.end_at를 넘길 수 없음
    """
    if request_hours <= 0:
        raise ValidationBusinessError(
            message="연장 시간은 1시간 이상이어야 합니다.",
            code="invalid_extension_hours",
            detail={"hours":request_hours}
        )

    if request_hours > 6:
        raise ValidationBusinessError(
            message="한 번에 최대 6시간까지만 연장할 수 있습니다.",
            code="max_extension_hours_exceeded",
            detail={"hours" : request_hours}
        )

    requested_end_at = current_expected_end_at + timedelta(hours=request_hours)

    if pass_obj.pass_kind == Pass.PassKind.FLAT:
        if pass_obj.end_at is None:
            raise ValidationBusinessError(
                message="기간권 종료 시간이 없습니다.",
                code="flat_pass_end_at_required",
                detail={"pass_id" : pass_obj.id},
            )

        new_expected_end_at = min(requested_end_at, pass_obj.end_at)

        if new_expected_end_at <= current_expected_end_at:
            raise ConflictBusinessError(
                message="더 이상 연장할 수 없습니다.",
                code="flat_extension_not_available",
                detail={
                    "pass_id" : pass_obj.id,
                    "pass_end_at" : pass_obj.end_at.isoformat(),
                    "current_expected_end_at" : current_expected_end_at.isoformat(),
                },
            )

        return new_expected_end_at



    raise ValidationBusinessError(
        message="일반석 연장에 사용할 수 없는 이용권입니다.",
        code="invalid_extension_pass_kind",
        detail={
            "pass_id" : pass_obj.id,
            "pass_kind" : pass_obj.pass_kind,
        },
    )


@transaction.atomic
def extend_normal_seat_usage(*, user, hours: int) -> SeatUsage:
    """
    일반석 시간 연장
    - 일반석만 가능
    - 한 번에 최대 6시간
    """
    now = timezone.now()

    seat_usage = _get_current_normal_seat_usage_for_update(user=user)
    pass_obj = seat_usage.pass_obj

    if pass_obj.pass_kind == Pass.PassKind.TIME :
        raise ConflictBusinessError(
            message="시간제 이용권은 추가 결제를 통해 연장해야 합니다.",
            code="time_pass_extend_requires_payment",
            detail={
                "pass_id" : pass_obj.id,
                "pass_kind" : pass_obj.pass_kind,
                "requires_payment" : True,
            },
        )

    if pass_obj.pass_kind != Pass.PassKind.FLAT:
        raise ValidationBusinessError(
            message="일반석 연장에 사용할 수 없는 이용권입니다.",
            code="invalid_extension_pass_kind",
            detail={
                "seat_usage_id":seat_usage.id,
                "pass_kind":pass_obj.pass_kind,
            },
        )

    current_expected_end_at = seat_usage.expected_end_at
    if current_expected_end_at is None:
        raise ValidationBusinessError(
            message="현재 퇴실 예정 시간이 없습니다.",
            code="expected_end_at_required",
            detail={"seat_usage_id":seat_usage.id},
        )

    if current_expected_end_at <= now:
        raise ConflictBusinessError(
            message="이미 종료된 사용은 연장할 수 없습니다.",
            code="seat_usage_already_expired",
            detail={
                "seat_usage_id" : seat_usage.id,
                "expected_end_at" : current_expected_end_at.isoformat(),
            },
        )

    new_expected_end_at = _calculate_extendable_end_at(
        pass_obj=pass_obj,
        current_expected_end_at=current_expected_end_at,
        request_hours=hours,
    )

    if new_expected_end_at == current_expected_end_at :
        raise ConflictBusinessError(
            message="연장 가능한 시간이 없습니다.",
            code="no_extendable_time",
            detail={
                "seat_usage_id" : seat_usage.id,
                "current_expected_end_at" : current_expected_end_at.isoformat(),
            },
        )

    seat_usage.expected_end_at = new_expected_end_at
    seat_usage.save(update_fields=["expected_end_at"])

    write_log(
        actor_user=user,
        target_user=user,
        action=LogAction.SEAT_EXTENDED,
        entity_type=LogEntityType.SEAT_USAGE,
        entity_id=seat_usage.id,
        message="일반석 시간 연장 완료",
        metadata={
            "seat_usage_id" : seat_usage.id,
            "seat_id" : seat_usage.seat_id,
            "seat_no" : seat_usage.seat.seat_no,
            "pass_id" : pass_obj.id,
            "pass_kind" : pass_obj.pass_kind,
            "requested_hours" : hours,
            "previous_expected_end_at" : current_expected_end_at.isoformat(),
            "new_expected_end_at" : new_expected_end_at.isoformat(),
        },
    )

    return seat_usage