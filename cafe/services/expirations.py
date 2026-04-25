"""
만료 처리

기간제 상품은 end_at 기준으로 만료
시간제 상품은 remaining_minutes 0이면 만료
 fixed/locker 만료 시 관련 usage 정리
 로그 생성
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from cafe.models import LockerUsage, Pass, SeatUsage
from logs.services import LogAction, LogEntityType, write_log


def _cleanup_expired_pass_usage(*, pass_obj:Pass) -> dict:
    """
    만료된 pass에 연결된 점유 정보

    반환:
    {
        "deleted_seat_usage_ids":[..., ....],
        "deleted_locker_usage_ids":[..., ....],
    }
    """
    deleted_seat_usage_ids : list[int] = []
    deleted_locker_usage_ids : list[int] = []

    # fixed/flat/time 남아 있는 SeatUsage 정리
    seat_usages = list(
        SeatUsage.objects
        .select_for_update()
        .filter(pass_obj=pass_obj)
        .order_by("id")
    )
    if seat_usages:
        deleted_seat_usage_ids = [usage.id for usage in seat_usages]
        SeatUsage.objects.filter(id__in=deleted_seat_usage_ids).delete()

    # locker에 lockerUsage 정리
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
        "deleted_seat_usage_ids":deleted_seat_usage_ids,
        "deleted_locker_usage_ids" : deleted_locker_usage_ids,
    }


def _expire_single_pass(*,pass_obj:Pass,now) -> dict:
    """
    pass 1건 만료 처리
    """
    cleanup_result = _cleanup_expired_pass_usage(pass_obj=pass_obj)

    pass_obj.status = Pass.Status.EXPIRED
    pass_obj.save(update_fields=["status"])

    write_log(
        actor_user=None,
        target_user=pass_obj.user,
        action=LogAction.PASS_EXPIRED,
        entity_type=LogEntityType.PASS,
        entity_id=pass_obj.id,
        message="이용권 만료 처리 완료",
        metadata={
            "pass_id":pass_obj.id,
            "pass_kind":pass_obj.pass_kind,
            "product_id":pass_obj.product_id,
            "expired_at":now.isoformat(),
            "end_at":pass_obj.end_at.isoformat() if pass_obj.end_at else None,
            "remaining_minutes":pass_obj.remaining_minutes,
            "deleted_seat_usage_ids":cleanup_result["deleted_seat_usage_ids"],
            "deleted_locker_usage_ids" : cleanup_result["deleted_locker_usage_ids"],
        },
    )

    return {
        "pass_id":pass_obj.id,
        "user_id":pass_obj.user_id,
        "pass_kind":pass_obj.pass_kind,
        "deleted_seat_ids":cleanup_result["deleted_seat_usage_ids"],
        "deleted_locker_usage_ids":cleanup_result["deleted_locker_usage_ids"],
    }


@transaction.atomic
def expire_due_passes(*, now=None) -> dict:
    """
    만료 대상 pass 일괄 처리

    1. 기간형(active + end_at <= now)
    2. 시간형(active + remaining_minutes <= 0)
    """
    current_time = now or timezone.now()

    period_passes = list(
        Pass.objects
        .select_for_update()
        .filter(
            status=Pass.Status.ACTIVE,
            pass_kind__in=[
                Pass.PassKind.FLAT,
                Pass.PassKind.FIXED,
                Pass.PassKind.LOCKER,
            ],
            end_at__isnull=False,
            end_at__lte=current_time,
        )
        .order_by("end_at","id")
    )

    time_passes = list(
        Pass.objects
        .select_for_update()
        .filter(
            status=Pass.Status.ACTIVE,
            pass_kind=Pass.PassKind.TIME,
            remaining_minutes__lte=0,
        )
        .order_by("id")
    )

    due_passes = period_passes + time_passes

    results = []
    for pass_obj in due_passes:
        results.append(
            _expire_single_pass(
                pass_obj=pass_obj,
                now=current_time,
            )
        )

    write_log(
        actor_user=None,
        target_user=None,
        action=LogAction.BATCH_PASS_EXPIRE_RUN,
        entity_type=LogEntityType.BATCH,
        entity_id=None,
        message="이용권 만료 배치 실행 완료",
        metadata={
            "excuted_at":current_time.isoformat(),
            "processed_count":len(results),
            "processed_pass_ids":[item["pass_id"] for item in results],
            "processed_user_ids" : [item["user_id"] for item in results]
        },
    )

    return {
        "processed_count":len(results),
        "processed_pass_ids":[item["pass_id"] for item in results],
        "processed_user_ids":[item["user_id"] for item in results]
    }