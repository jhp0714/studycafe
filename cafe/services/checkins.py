"""
입실

active pass 확인
일반석/지정석 분기
사용자 중복 점유 차단
좌석 타입 검증
12시간 규칙 적용
SeatUsage 생성
로그 생성
"""

from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from cafe.models import Pass, Seat, SeatUsage
from common.exceptions import ConflictBusinessError, NotFoundBusinessError, ValidationBusinessError
from logs.services import LogAction, LogEntityType, write_log


def _get_active_normal_pass_for_update(*, user) -> Pass:
    """
    일반석 입실할 때 사용할 active pass 조회

    우선순위 flat > time
    """
    flat_pass = (
        Pass.objects
        .select_for_update()
        .select_related("product")
        .filter(
            user=user,
            pass_kind=Pass.PassKind.FLAT,
            status=Pass.Status.ACTIVE,
        )
        .order_by("-id")
        .first()
    )
    if flat_pass:
        return flat_pass

    time_pass = (
        Pass.objects
        .select_for_update()
        .select_related("product")
        .filter(
            user=user,
            pass_kind=Pass.PassKind.TIME,
            status=Pass.Status.ACTIVE,
        )
        .order_by("-id")
        .first()
    )
    if time_pass :
        return time_pass

    raise NotFoundBusinessError(
        message="일반석에서 사용할 수 있는 이용권이 없습니다.",
        code="normal_pass_not_found"
    )


def _calculate_normal_expected_end_at(*,pass_obj:Pass, now):
    """
    일반석 expected_end_at 계산

    - 최대 12시간 제한
    - flat:min(now+12, pass.end_at)
    - time:min(now+remaining_minutes, now + 12)
    """
    max_end_at = now + timedelta(hours=12)

    if pass_obj.pass_kind == Pass.PassKind.FLAT:
        if pass_obj.end_at is None:
            raise ValidationBusinessError(
                message="기간제 이용권의 종료 시간이 없습니다.",
                code="flat_pass_end_at_required",
                detail={"pass_id":pass_obj.id},
            )
        return min(max_end_at, pass_obj.end_at)

    if pass_obj.pass_kind == Pass.PassKind.TIME:
        remaining_minutes = pass_obj.remaining_minutes or 0
        if remaining_minutes <= 0:
            raise ConflictBusinessError(
                message="남은 시간이 없습니다.",
                code="time_pass_no_remaining_minutes",
                detail={"pass_id":pass_obj.id},
            )

        pass_end_at = now+ timedelta(minutes=remaining_minutes)
        return min(max_end_at, pass_end_at)

    raise ValidationBusinessError(
        message="일반석에서 사용할 수 없는 이용권입니다.",
        code="invalid_normal_pass_kind",
        detail={"pass_kind":pass_obj.pass_kind}
    )

def _assert_checkinable_normal_seat(*, user, seat:Seat) -> None:
    """
    일반석 입실 가능 여부 검증
    """
    if seat.seat_type != Seat.SeatType.NORMAL:
        raise ValidationBusinessError(
            message="일반석만 입실할 수 있습니다.",
            code="normal_seat_only",
            detail={"seat_id":seat.id, "seat_type":seat.seat_type}
        )

    if not seat.available:
        raise ConflictBusinessError(
            message="사용 불가능한 좌석입니다.",
            code="seat_not_available",
            detail={"seat_id":seat.id}
        )

    if SeatUsage.objects.filter(user=user).exists():
        raise ConflictBusinessError(
            message="이미 다른 좌석을 사용 중입니다.",
            code="seat_usage_already_exists"
        )

    if SeatUsage.objects.filter(seat=seat).exists():
        raise ConflictBusinessError(
            message="이미 사용 중인 좌석입니다.",
            code="seat_already_occupied",
            detail={"seat_id":seat.id}
        )


@transaction.atomic
def checkin_normal_seat(*, user, seat_id:int) -> SeatUsage:
    """
    일반석 입실
    """
    now = timezone.now()

    seat = (
        Seat.objects
        .select_for_update()
        .filter(id=seat_id)
        .first()
    )
    if seat is None:
        raise NotFoundBusinessError(
            message="좌석을 찾을 수 없습니다.",
            code="seat_not_found",
            detail={"seat_id":seat_id},
        )

    pass_obj = _get_active_normal_pass_for_update(user=user)
    _assert_checkinable_normal_seat(user=user, seat=seat)

    expected_end_at = _calculate_normal_expected_end_at(pass_obj=pass_obj, now=now)

    try:
        seat_usage = SeatUsage.objects.create(
            user=user,
            pass_obj=pass_obj,
            seat=seat,
            check_in_at=now,
            expected_end_at=expected_end_at,
        )
    except IntegrityError:
        raise ConflictBusinessError(
            message="좌석 점유 생성 중 에러가 발생했습니다.",
            code="seat_usage_conflict",
            detail={"seat_id":seat.id},
        )

    write_log(
        actor_user=user,
        target_user=user,
        action=LogAction.SEAT_CHECKED_IN,
        entity_type=LogEntityType.SEAT_USAGE,
        entity_id=seat_usage.id,
        message="일반석 입실 완료",
        metadata={
            "seat_id":seat.id,
            "seat_no":seat.seat_no,
            "pass_id":pass_obj.id,
            "pass_kind":pass_obj.pass_kind,
            "check_in_at":now.isoformat(),
            "expected_end_at":expected_end_at.isoformat(),
        },
    )

    return seat_usage