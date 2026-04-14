"""
좌석/사물함 이동

현재 usage 확인
대상 좌석/사물함 available + unused인지 확인
일반석 이동시 expcted_end_at 유지
fixed/locker 이동시 Pass_id와 SeatUsage/LockerUsage_id 동시 변경
로그 생성
"""
from __future__ import annotations

from django.db import IntegrityError, transaction

from cafe.models import Locker, LockerUsage, Pass, Seat, SeatUsage
from cafe.services.expirations import expire_due_passes
from common.exceptions import ConflictBusinessError, NotFoundBusinessError, ValidationBusinessError
from logs.services import LogAction, LogEntityType, write_log


def _assert_seat_movable(*, seat:Seat) -> None:
    if not seat.available:
        raise ConflictBusinessError(
            message="사용 불가능한 좌석입니다.",
            code="seat_not_available",
            detail={"seat_id":seat.id}
        )


def _assert_locker_movable(*, locker:Locker) -> None:
    if not locker.available:
        raise ConflictBusinessError(
            message="사용 불가능한 사물함입니다.",
            code="locker_not_available",
            detail={"locker_id":locker.id}
        )


def _get_current_normal_seat_usage_for_update(*, user) -> SeatUsage:
    seat_usage = (
        SeatUsage.objects
        .select_for_update()
        .select_related("seat","pass_obj","pass_obj__product")
        .filter(user=user, seat__seat_type=Seat.SeatType.NORMAL)
        .first()
    )

    if seat_usage is None:
        raise NotFoundBusinessError(
            message="현재 사용 중인 일반석이 없습니다.",
            code="normal_seat_usage_not_found",
        )

    if seat_usage.pass_obj.pass_kind not in (Pass.PassKind.TIME, Pass.PassKind.FLAT):
        raise ValidationBusinessError(
            message="일반석 이동에 사용할 수 없는 이용권입니다.",
            code="invalid_normal_move_pass_kind",
            detail={
                "seat_usage_id":seat_usage.id,
                "pass_kind":seat_usage.pass_obj.pass_kind,
            },
        )

    return seat_usage


def _get_current_fixed_pass_and_usage_for_update(*, user) -> tuple[Pass, SeatUsage]:
    pass_obj = (
        Pass.objects
        .select_for_update()
        .select_related("fixed_seat","product")
        .filter(
            user=user,
            pass_kind=Pass.PassKind.FIXED,
            status=Pass.Status.ACTIVE
        )
        .order_by("-id")
        .first()
    )

    if pass_obj is None:
        raise NotFoundBusinessError(
            message="사용 중인 지정석 이용권이 없습니다.",
            code="fixed_pass_not_found"
        )

    seat_usage = (
        SeatUsage.objects
        .select_for_update()
        .select_related("seat","pass_obj")
        .filter(pass_obj=pass_obj, user=user)
        .first()
    )

    if seat_usage is None:
        raise NotFoundBusinessError(
            message="현재 점유 중인 지정석 정보가 없습니다.",
            code = "fixed_seat_usage_not_found",
            detail={"pass_id":pass_obj.id},
        )

    return pass_obj, seat_usage


def _get_current_locker_pass_and_usage_for_update(*, user) -> tuple[Pass, LockerUsage]:
    pass_obj = (
        Pass.objects
        .select_for_update()
        .select_related("locker","product")
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
            message="사용중인 사물함 이용권이 없습니다.",
            code="locker_pass_not_found"
        )

    locker_usage = (
        LockerUsage.objects
        .select_for_update()
        .select_related("locker","pass_obj")
        .filter(pass_obj=pass_obj,user=user)
        .first()
    )

    if locker_usage is None:
        raise NotFoundBusinessError(
            message="현재 점유 중인 사물함 정보가 없습니다.",
            code="locker_usage_not_found",
            detail={"pass_id":pass_obj.id}
        )

    return pass_obj, locker_usage


@transaction.atomic
def move_normal_seat(*, user, to_seat_id:int) -> SeatUsage:
    """
    일반석 이동
    - 기존 SeatUsage에서 seat만 변경
    """
    expire_due_passes()  # 임시 만료처리 실행
    seat_usage = _get_current_normal_seat_usage_for_update(user=user)

    to_seat = (
        Seat.objects
        .select_for_update()
        .filter(id=to_seat_id)
        .first()
    )
    if to_seat is None:
        raise NotFoundBusinessError(
            message="이동할 좌석을 찾을 수 없습니다.",
            code="seat_not_found",
            detail={"seat_id":to_seat_id},
        )

    if to_seat.seat_type != Seat.SeatType.NORMAL:
        raise ValidationBusinessError(
            message="일반석으로만 이동할 수 있습니다.",
            code="normal_seat_only",
            detail={"seat_id":to_seat.id, "seat_type":to_seat.seat_type},
        )

    _assert_seat_movable(seat=to_seat)

    from_seat = seat_usage.seat
    if from_seat.id == to_seat.id:
        raise ConflictBusinessError(
            message="같은 좌석으로 이동할 수 없습니다.",
            code="same_seat_move_not_allowed",
            detail={"seat_id":to_seat.id}
        )

    if SeatUsage.objects.filter(seat=to_seat).exclude(id=seat_usage.id).exists():
        raise ConflictBusinessError(
            message="이미 사용 중인 좌석입니다.",
            code="seat_already_occupied",
            detail={"seat_id":to_seat.id},
        )

    seat_usage.seat = to_seat

    try:
        seat_usage.save(update_fields=["seat"])
    except IntegrityError:
        raise ConflictBusinessError(
            message="좌석 이동 중 충돌이 발생했습니다.",
            code="seat_move_conflict",
            detail={"from_seat_id":from_seat.id,"to_seat_id":to_seat.id},
        )

    write_log(
        actor_user=user,
        target_user=user,
        action=LogAction.SEAT_MOVED,
        entity_type=LogEntityType.SEAT_USAGE,
        entity_id=seat_usage.id,
        message="일반석 이동 완료",
        metadata={
            "seat_usage_id":seat_usage.id,
            "pass_id":seat_usage.pass_obj_id,
            "from_seat_id":from_seat.id,
            "from_seat_no":from_seat.seat_no,
            "to_seat_id":to_seat.id,
            "to_seat_no":to_seat.seat_no,
            "expected_end_at":(seat_usage.expected_end_at.isoformat() if seat_usage.expected_end_at else None)
        },
    )

    return seat_usage


@transaction.atomic
def move_fixed_seat(*,user,to_seat_id:int) -> SeatUsage:
    """
    지정석 이동
    - Pass.fixed_seat와 SEatUsage.seat를 같이 변경
    """
    expire_due_passes()  # 임시 만료처리 실행
    pass_obj, seat_usage = _get_current_fixed_pass_and_usage_for_update(user=user)

    to_seat = (
        Seat.objects
        .select_for_update()
        .filter(id=to_seat_id)
        .first()
    )
    if to_seat is None:
        raise NotFoundBusinessError(
            message="이동할 지정석을 찾을 수 없습니다.",
            code="seat_not_found",
            detail={"seat_id":to_seat_id},
        )

    if to_seat.seat_type != Seat.SeatType.FIXED:
        raise ValidationBusinessError(
            message="지정석으로만 이동할 수 있습니다.",
            code="fixed_seat_only",
            detail={"seat_id":to_seat.id, "seat_type":to_seat.seat_type},
        )

    _assert_seat_movable(seat=to_seat)

    from_seat = pass_obj.fixed_seat
    if from_seat and from_seat.id == to_seat.id:
        raise ConflictBusinessError(
            message="같은 지정석으로는 이동할 수 없습니다.",
            code="same_fixed_seat_move_not_allowed",
            detail={"seat_id":to_seat.id},
        )

    if SeatUsage.objects.filter(seat=to_seat).exclude(id=seat_usage.id).exists():
        raise ConflictBusinessError(
            message="이미 사용 중인 자석입니다.",
            code="fixed_seat_already_occupied",
            detail={"seat_id":to_seat.id},
        )

    pass_obj.fixed_seat = to_seat
    seat_usage.seat = to_seat
    seat_usage.expected_end_at = pass_obj.end_at

    try:
        pass_obj.save(update_fields=["fixed_seat"])
        seat_usage.save(update_fields=["seat","expected_end_at"])
    except IntegrityError:
        raise ConflictBusinessError(
            message="지정석 이동 중 충돌이 발생했습니다.",
            code="fixed_seat_move_conflict",
            detail={
                "from_seat_id":from_seat.id if from_seat else None,
                "to_seat_id":to_seat.id,
                "pass_id":pass_obj.id
            },
        )

    write_log(
        actor_user=user,
        target_user=user,
        action=LogAction.FIXED_SEAT_MOVED,
        entity_type=LogEntityType.SEAT_USAGE,
        entity_id=seat_usage.id,
        message="지정석 이동 완료",
        metadata={
            "seat_usage_id" : seat_usage.id,
            "pass_id" : pass_obj.id,
            "from_seat_id" : from_seat.id if from_seat else None,
            "from_seat_no" : from_seat.seat_no if from_seat else None,
            "to_seat_id" : to_seat.id,
            "to_seat_no" : to_seat.seat_no,
            "expected_end_at" : (seat_usage.expected_end_at.isoformat() if seat_usage.expected_end_at else None)
        },
    )

    return seat_usage


@transaction.atomic
def move_fixed_seat(*, user, to_seat_id: int) -> SeatUsage:
    """
    지정석 이동
    - Pass.fixed_seat와 SeatUsage.seat를 같이 변경
    """
    expire_due_passes()  # 임시 만료처리 실행
    pass_obj, seat_usage = _get_current_fixed_pass_and_usage_for_update(user=user)

    to_seat = (
        Seat.objects
        .select_for_update()
        .filter(id=to_seat_id)
        .first()
    )
    if to_seat is None:
        raise NotFoundBusinessError(
            message="이동할 지정석을 찾을 수 없습니다.",
            code="seat_not_found",
            detail={"seat_id": to_seat_id},
        )

    if to_seat.seat_type != Seat.SeatType.FIXED:
        raise ValidationBusinessError(
            message="지정석으로만 이동할 수 있습니다.",
            code="fixed_seat_only",
            detail={"seat_id": to_seat.id, "seat_type": to_seat.seat_type},
        )

    _assert_seat_movable(seat=to_seat)

    from_seat = pass_obj.fixed_seat
    if from_seat and from_seat.id == to_seat.id:
        raise ConflictBusinessError(
            message="같은 지정석으로는 이동할 수 없습니다.",
            code="same_fixed_seat_move_not_allowed",
            detail={"seat_id": to_seat.id},
        )

    if SeatUsage.objects.filter(seat=to_seat).exclude(id=seat_usage.id).exists():
        raise ConflictBusinessError(
            message="이미 사용 중인 지정석입니다.",
            code="fixed_seat_already_occupied",
            detail={"seat_id": to_seat.id},
        )

    pass_obj.fixed_seat = to_seat
    seat_usage.seat = to_seat
    seat_usage.expected_end_at = pass_obj.end_at

    try:
        pass_obj.save(update_fields=["fixed_seat"])
        seat_usage.save(update_fields=["seat", "expected_end_at"])
    except IntegrityError:
        raise ConflictBusinessError(
            message="지정석 이동 중 충돌이 발생했습니다.",
            code="fixed_seat_move_conflict",
            detail={
                "from_seat_id": from_seat.id if from_seat else None,
                "to_seat_id": to_seat.id,
                "pass_id": pass_obj.id,
            },
        )

    write_log(
        actor_user=user,
        target_user=user,
        action=LogAction.FIXED_SEAT_MOVED,
        entity_type=LogEntityType.SEAT_USAGE,
        entity_id=seat_usage.id,
        message="지정석 이동 완료",
        metadata={
            "seat_usage_id": seat_usage.id,
            "pass_id": pass_obj.id,
            "from_seat_id": from_seat.id if from_seat else None,
            "from_seat_no": from_seat.seat_no if from_seat else None,
            "to_seat_id": to_seat.id,
            "to_seat_no": to_seat.seat_no,
            "expected_end_at": (
                seat_usage.expected_end_at.isoformat()
                if seat_usage.expected_end_at
                else None
            ),
        },
    )

    return seat_usage


@transaction.atomic
def move_locker(*, user, to_locker_id: int) -> LockerUsage:
    """
    사물함 이동
    - Pass.locker와 LockerUsage.locker를 같이 변경
    """
    pass_obj, locker_usage = _get_current_locker_pass_and_usage_for_update(user=user)

    to_locker = (
        Locker.objects
        .select_for_update()
        .filter(id=to_locker_id)
        .first()
    )
    if to_locker is None:
        raise NotFoundBusinessError(
            message="이동할 사물함을 찾을 수 없습니다.",
            code="locker_not_found",
            detail={"locker_id": to_locker_id},
        )

    _assert_locker_movable(locker=to_locker)

    from_locker = pass_obj.locker
    if from_locker and from_locker.id == to_locker.id:
        raise ConflictBusinessError(
            message="같은 사물함으로는 이동할 수 없습니다.",
            code="same_locker_move_not_allowed",
            detail={"locker_id": to_locker.id},
        )

    if LockerUsage.objects.filter(locker=to_locker).exclude(id=locker_usage.id).exists():
        raise ConflictBusinessError(
            message="이미 사용 중인 사물함입니다.",
            code="locker_already_occupied",
            detail={"locker_id": to_locker.id},
        )

    pass_obj.locker = to_locker
    locker_usage.locker = to_locker
    locker_usage.unassign_at = pass_obj.end_at

    try:
        pass_obj.save(update_fields=["locker"])
        locker_usage.save(update_fields=["locker", "unassign_at"])
    except IntegrityError:
        raise ConflictBusinessError(
            message="사물함 이동 중 충돌이 발생했습니다.",
            code="locker_move_conflict",
            detail={
                "from_locker_id": from_locker.id if from_locker else None,
                "to_locker_id": to_locker.id,
                "pass_id": pass_obj.id,
            },
        )

    write_log(
        actor_user=user,
        target_user=user,
        action=LogAction.LOCKER_MOVED,
        entity_type=LogEntityType.LOCKER_USAGE,
        entity_id=locker_usage.id,
        message="사물함 이동 완료",
        metadata={
            "locker_usage_id": locker_usage.id,
            "pass_id": pass_obj.id,
            "from_locker_id": from_locker.id if from_locker else None,
            "from_locker_no": from_locker.locker_no if from_locker else None,
            "to_locker_id": to_locker.id,
            "to_locker_no": to_locker.locker_no,
            "unassign_at": (
                locker_usage.unassign_at.isoformat()
                if locker_usage.unassign_at
                else None
            ),
        },
    )

    return locker_usage


def move_seat(*, user, to_seat_id:int) -> dict:
    """
    현재 사용 상태 기준으로 일반석 이동/지정석 이동
    """
    normal_usage= (
        SeatUsage.objects
        .select_related("seat","pass_obj")
        .filter(user=user, seat__seat_type=Seat.SeatType.NORMAL)
        .first()
    )

    if normal_usage:
        seat_usage = move_normal_seat(user=user, to_seat_id=to_seat_id)
        return {
            "move_type" : "normal",
            "seat_usage_id" : seat_usage.id,
            "seat_id" : seat_usage.seat_id,
            "pass_id" : seat_usage.pass_obj_id,
            "expected_end_at" : seat_usage.expected_end_at,
        }

    fixed_pass = (
        Pass.objects
        .filter(
            user=user,
            pass_kind=Pass.PassKind.FIXED,
            status=Pass.Status.ACTIVE,
        )
        .first()
    )

    if fixed_pass :
        seat_usage = move_fixed_seat(user=user, to_seat_id=to_seat_id)
        return {
            "move_type" : "fixed",
            "seat_usage_id" : seat_usage.id,
            "seat_id" : seat_usage.seat_id,
            "pass_id" : seat_usage.pass_obj_id,
            "expected_end_at" : seat_usage.expected_end_at,
        }

    raise NotFoundBusinessError(
        message="이동할 좌석 사용 정보가 없습니다.",
        code="seat_move_target_not_found",
    )