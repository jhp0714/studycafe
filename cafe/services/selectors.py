"""
현재 사용 상태 조회
"""
from __future__ import annotations

from cafe.models import LockerUsage, SeatUsage, Pass, Seat
from common.exceptions import NotFoundBusinessError


def get_current_normal_seat_usage(*, user) -> SeatUsage:
    seat_usage = (
        SeatUsage.objects
        .selecte_related("seat","pass_obj","pass_obj__product")
        .filter(user=user, seat__seat=Seat.SeatType.NORMAL)
        .first()
    )
    if seat_usage is None:
        raise NotFoundBusinessError(
            message="현재 사용 중인 일반석이 없습니다.",
             code="normal_seat_usage_not_found"
        )
    return seat_usage

def get_active_fixed_pass(*, user) -> Pass:
    pass_obj = (
        Pass.objects
        .filter(
            user=user,
            pass_kind=Pass.PassKind.FIXED,
            status=Pass.Status.ACTIVE,
        )
        .order_by("-id")
        .first()
    )
    if pass_obj is None :
        raise NotFoundBusinessError(
            message="사용 중인 지정석 이용권이 없습니다.",
            code="fixed_pass_not_found",
        )
    return pass_obj


def get_active_locker_pass(*, user) -> Pass:
    pass_obj = (
        Pass.objects
        .select_related("locker", "product")
        .filter(
            user=user,
            pass_kind=Pass.PassKind.LOCKER,
            status=Pass.Status.ACTIVE,
        )
        .order_by("-id")
        .first()
    )
    if pass_obj is None:
        raise NotFoundBusinessError(
            message="사용 중인 사물함 이용권이 없습니다.",
            code="locker_pass_not_found",
        )
    return pass_obj


def get_current_fixed_seat_usage(*, user, pass_obj:Pass|None=None) -> SeatUsage:
    if pass_obj is None:
        pass_obj = get_active_fixed_pass(user=user)

    seat_usage = (
        SeatUsage.objects
        .select_related("seat","pass_obj")
        .filter(user=user, pass_obj=pass_obj)
        .first()
    )
    if seat_usage is None:
        raise NotFoundBusinessError(
            message="현재 점유 중인 지정석 정보가 없습니다.",
            code="fixed_seat_usage_not_found",
            detail={"pass_id":pass_obj.id}
        )
    return seat_usage


def get_current_locker_usage(*, user, pass_obj: Pass | None = None) -> LockerUsage:
    if pass_obj is None:
        pass_obj = get_active_locker_pass(user=user)

    locker_usage = (
        LockerUsage.objects
        .select_related("locker", "pass_obj")
        .filter(user=user, pass_obj=pass_obj)
        .first()
    )
    if locker_usage is None:
        raise NotFoundBusinessError(
            message="현재 점유 중인 사물함 정보가 없습니다.",
            code="locker_usage_not_found",
            detail={"pass_id": pass_obj.id},
        )
    return locker_usage