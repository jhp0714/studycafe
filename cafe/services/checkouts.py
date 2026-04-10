"""
퇴실

현재 SeatUsage 조회
time pass면 사용 시간 차감
flat/fixed면 시간 차감 없이 usage 삭제
강제 퇴실(로그만 강제 퇴실로 남기면 됨)
로그 생성
"""
from __future__ import annotations

from math import ceil

from django.db import transaction
from django.utils import timezone

from cafe.models import Pass, SeatUsage, Seat
from common.exceptions import ConflictBusinessError, NotFoundBusinessError, ValidationBusinessError
from logs.services import LogAction, LogEntityType, write_log


def _get_current_normal_seat_usage_for_update(*, user) -> SeatUsage:
    """
    현재 사용자의 일반선 SeatUsage 조회
    """
    seat_usage = (
        SeatUsage.objects
        .select_for_update()
        .select_related("seat","pass_obj","pass_obj__product")
        .filter(user=user)
        .first()
    )

    if seat_usage is None:
        raise NotFoundBusinessError(
            message="현재 사용 중인 좌석이 없습니다.",
            code="seat_usage_not_found"
        )

    if seat_usage.seat.seat_type != seat_usage.seat.SeatType.NORMAL:
        raise ValidationBusinessError(
            message="일반석만 퇴실만 처리할 수 있습니다.",
            code="normal_seat_choeckout_only",
            detail={
                "seat_usage_id":seat_usage.id,
                "seat_type":seat_usage.seat.seat_type,
            },
        )

    return seat_usage


def _calculate_used_minutes(*, seat_usage:SeatUsage, checked_out_at) -> int:
    """
    실제 사용 시간(분) 계싼
    - 초 단위는 올림 처리
    - 최소 1분
    """
    started_at = seat_usage.check_in_at
    duration_seconds = (checked_out_at - started_at).total_seconds()

    if duration_seconds < 0:
        raise ValidationBusinessError(
            message="퇴실 시간이  입실 시간보다 빠를 수 없습니다.",
            code="invalid_checkout_time",
            detail={
                "seat_usage_id":seat_usage.id,
                "check_in_at":started_at.isoformat(),
                "checked_out_at":checked_out_at.isoformat(),
            },
        )

    used_minutes = max(1, ceil(duration_seconds/60))
    return used_minutes


def _consume_time_pass_minutes(*,pass_obj:Pass,used_minutes:int)->tuple[int,int]:
    """
    시간제 pass의 남은 시간 차감

    반환:
    - (before_minutes, after_minutes
    """
    before_minutes = pass_obj.remaining_minutes or 0
    after_minutes = max(0, before_minutes -used_minutes)

    pass_obj.remaining_minutes = after_minutes

    if after_minutes <= 0:
        pass_obj.status = Pass.Status.EXPIRED
        pass_obj.save(update_fields=["remaining_minutes","status"])
    else:
        pass_obj.save(update_fields=["remaining_minutes"])

    return before_minutes, after_minutes


def _checkout_normal_seat_usage(*,seat_usage:SeatUsage,checked_out_at,action:str,actor_user=None,message:str,) -> dict:
    """
    일반석 SeatUsage 공통 퇴실 처리

    - time : 실제 사용 분만큼 차감
    - flat : 시간 차감 없음
    - usage 삭제
    - 로그 기록
    """
    pass_obj = seat_usage.pass_obj
    seat = seat_usage.seat

    if seat.seat_type != seat.SeatType.NORMAL:
        raise ValidationBusinessError(
            message="일반석 퇴살만 처리할 수 있습니다.",
            code="normal_seat_checkout_only",
            detail={
                "seat_usage_id":seat_usage.id,
                "seat_type":seat.seat_type,
            },
        )

    if pass_obj.pass_kind not in (Pass.PassKind.TIME, Pass.PassKind.FLAT):
        raise ValidationBusinessError(
            message="일반석 퇴실에 사용할 수 없는 이용권입니다.",
            code="invalid_normal_checkout_pass_kind",
            detail={
                "seat_usage_id":seat_usage.id,
                "pass_kind":pass_obj.pass_kind,
            },
        )

    used_minutes = _calculate_used_minutes(seat_usage=seat_usage, checked_out_at=checked_out_at)
    remaining_before = pass_obj.remaining_minutes
    remaining_after = pass_obj.remaining_minutes

    if pass_obj.pass_kind == Pass.PassKind.TIME:
        remaining_before, remaining_after = _consume_time_pass_minutes(pass_obj=pass_obj,used_minutes=used_minutes)

    seat_usage_id = seat_usage.id
    pass_id = pass_obj.id
    pass_kind = pass_obj.pass_kind
    seat_id = seat.id
    seat_no = seat.seat_no
    check_in_at = seat_usage.check_in_at
    expected_end_at = seat_usage.expected_end_at
    target_user = seat_usage.user

    seat_usage.delete()

    write_log(
        actor_user=actor_user,
        target_user=target_user,
        action=action,
        entity_type=LogEntityType.SEAT_USAGE,
        entity_id=seat_usage_id,
        message=message,
        metadata={
            "seat_id":seat_id,
            "seat_no":seat_no,
            "pass_id":pass_id,
            "pass_kind":pass_kind,
            "check_in_at":check_in_at.isoformat(),
            "checked_out_at":checked_out_at.isoformat(),
            "expected_end_at": expected_end_at.isoformat() if expected_end_at else None,
            "used_minutes":used_minutes,
            "remaining_minutes_before":remaining_before,
            "remaining_minutes_after":remaining_after,
        },
    )

    return {
        "seat_usage_id":seat_usage_id,
        "seat_id":seat_id,
        "seat_no":seat_no,
        "user_id":target_user.id,
        "pass_id":pass_id,
        "pass_kind":pass_kind,
        "checked_out_at":checked_out_at,
        "used_minutes":used_minutes,
        "remaining_minutes_before":remaining_before,
        "remaining_minutes_after":remaining_after,
    }


@transaction.atomic
def checkout_normal_seat(*,user,checked_out_at=None) -> dict:
    """
    일반석 수동 퇴실
    """
    current_time = checked_out_at or timezone.now()

    seat_usage = _get_current_normal_seat_usage_for_update(user=user)

    return _checkout_normal_seat_usage(seat_usage=seat_usage, checked_out_at=current_time,
                                       action=LogAction.SEAT_CHECKED_OUT, actor_user=user, message="일반석 수동 퇴실 완료")


@transaction.atomic
def auto_checkout_expired_normal_seats(*, now=None) -> dict:
    """
    일반석 자동 퇴실 일괄 처리
    - expected_end_at <= now 인경우
    """
    current_time = now or timezone.now()

    expired_usages = list(
        SeatUsage.objects
        .select_for_update()
        .select_related("seat","pass_obj","pass_obj__product","user")
        .filter(
            seat__seat_type=Seat.SeatType.NORMAL,
            expected_end_at__isnull=False,
            expected_end_at__lte=current_time,
        )
        .order_by("expected_end_at","id")
    )

    results = []

    for seat_usage in expired_usages:
        result = _checkout_normal_seat_usage(seat_usage=seat_usage, checked_out_at=current_time,
                                             action=LogAction.SEAT_AUTO_CHECKED_OUT, actor_user=None, message="일반석 자동 퇴실 완료")
        results.append(result)

    write_log(
        actor_user=None,
        target_user=None,
        action=LogAction.BATCH_AUTO_CHECKOUT_RUN,
        entity_type=LogEntityType.BATCH,
        entity_id=None,
        message="일반석 자동 퇴실 배치 실행 완료",
        metadata={
            "executed_at":current_time.isoformat(),
            "processed_count":len(results),
            "seat_usage_ids":[item["seat_usage_id"] for item in results],
        },
    )

    return {
        "processed_count":len(results),
        "processed_seat_usage_ids":[item["seat_usage_id"] for item in results],
        "processed_user_ids":[item["user_id"] for item in results],
    }