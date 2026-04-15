"""
정상 흐름으로 끝나는게 아니라 중간 실패나 과거 데이터를 정리하는 로직
"""
from __future__ import annotations

from django.db import transaction, models
from django.utils import timezone

from cafe.models import LockerUsage, Pass, SeatUsage
from logs.services import LogAction, LogEntityType, write_log


@transaction.atomic
def cleanup_inactive_pass_usages() -> dict:
    """
    expired / canceled pass에 연결된 usage 정리
    """
    inactive_statuses = [
        Pass.Status.EXPIRED,
        Pass.Status.CANCELED,
    ]

    seat_usage_ids = list(
        SeatUsage.objects
        .select_for_update()
        .filter(pass_obj__status__in=inactive_statuses)
        .values_list("id", flat=True)
    )

    locker_usage_ids = list(
        LockerUsage.objects
        .select_for_update()
        .filter(pass_obj__status__in=inactive_statuses)
        .values_list("id", flat=True)
    )

    deleted_seat_usage_count = 0
    deleted_locker_usage_count = 0

    if seat_usage_ids:
        deleted_seat_usage_count, _ = (
            SeatUsage.objects
            .filter(id__in=seat_usage_ids)
            .delete()
        )

    if locker_usage_ids:
        deleted_locker_usage_count, _ = (
            LockerUsage.objects
            .filter(id__in=locker_usage_ids)
            .delete()
        )

    return {
        "deleted_seat_usage_count": deleted_seat_usage_count,
        "deleted_locker_usage_count": deleted_locker_usage_count,
        "deleted_seat_usage_ids": seat_usage_ids,
        "deleted_locker_usage_ids": locker_usage_ids,
    }


@transaction.atomic
def cleanup_expired_but_active_passes(*, now=None) -> dict:
    """
    실제로는 만료됐는데 active로 남아 있는 pass 상태 보정
    """
    current_time = now or timezone.now()

    period_pass_ids = list(
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
        .values_list("id", flat=True)
    )

    time_pass_ids = list(
        Pass.objects
        .select_for_update()
        .filter(
            status=Pass.Status.ACTIVE,
            pass_kind=Pass.PassKind.TIME,
            remaining_minutes__lte=0,
        )
        .values_list("id", flat=True)
    )

    target_pass_ids = period_pass_ids + time_pass_ids

    updated_count = 0
    if target_pass_ids:
        updated_count = (
            Pass.objects
            .filter(id__in=target_pass_ids)
            .update(status=Pass.Status.EXPIRED)
        )

    return {
        "updated_pass_count": updated_count,
        "updated_pass_ids": target_pass_ids,
    }


@transaction.atomic
def run_cleanup_jobs(*, now=None) -> dict:
    """
    cleanup 전체 실행
    """
    current_time = now or timezone.now()

    inactive_usage_result = cleanup_inactive_pass_usages()
    expired_pass_result = cleanup_expired_but_active_passes(now=current_time)
    mismatch_result = cleanup_mismatched_pass_usages()

    result = {
        "executed_at": current_time,
        "inactive_usage_cleanup": inactive_usage_result,
        "expired_pass_cleanup": expired_pass_result,
        "mismatch_cleanup":mismatch_result,
        "total_processed_count": (
            inactive_usage_result["deleted_seat_usage_count"]
            + inactive_usage_result["deleted_locker_usage_count"]
            + expired_pass_result["updated_pass_count"]
            + mismatch_result["deleted_seat_usage_count"]
            + mismatch_result["deleted_locker_usage_count"]
        ),
    }

    write_log(
        actor_user=None,
        target_user=None,
        action=LogAction.BATCH_CLEANUP_RUN,
        entity_type=LogEntityType.BATCH,
        entity_id=None,
        message="정합성 정리 배치 실행 완료",
        metadata={
            "executed_at": current_time.isoformat(),
            "deleted_seat_usage_count": inactive_usage_result["deleted_seat_usage_count"],
            "deleted_locker_usage_count": inactive_usage_result["deleted_locker_usage_count"],
            "updated_pass_count": expired_pass_result["updated_pass_count"],
            "deleted_seat_usage_ids": inactive_usage_result["deleted_seat_usage_ids"],
            "deleted_locker_usage_ids": inactive_usage_result["deleted_locker_usage_ids"],
            "updated_pass_ids": expired_pass_result["updated_pass_ids"],
            "total_processed_count": result["total_processed_count"],
            "mismatch_deleted_seat_usage_count" : mismatch_result["deleted_seat_usage_count"],
            "mismatch_deleted_locker_usage_count" : mismatch_result["deleted_locker_usage_count"],
            "mismatch_deleted_seat_usage_ids" : mismatch_result["deleted_seat_usage_ids"],
            "mismatch_deleted_locker_usage_ids" : mismatch_result["deleted_locker_usage_ids"],
        },
    )

    return result


@transaction.atomic
def cleanup_mismatched_pass_usages() -> dict:
    """
    pass와 usage의 연결 자원이 서로 다른 데이터 정리
    - fixed pass인데 Pass.fixed_seat != Seatusage.seat
    - locker pass인데 Pass.locker != LockerUsage.locker

    일단 서로 다른 데이터의 usage를 삭제하고 정상 흐름에서 다시 생성, 유지되게 한다.
    """
    mismatched_seat_usage_ids = list(
        SeatUsage.objects
        .select_for_update()
        .filter(pass_obj__pass_kind=Pass.PassKind.FIXED)
        .exclude(seat_id=models.F("pass_obj__fixed_seat_id"))
        .values_list("id",flat=True)
    )

    mismatched_locker_usage_ids = list(
        LockerUsage.objects
        .select_for_update()
        .filter(
            pass_obj__pass_kind=Pass.PassKind.LOCKER,
        )
        .exclude(
            locker_id=models.F("pass_obj__locker_id"),
        )
        .values_list("id", flat=True)
    )

    deleted_seat_usage_count = 0
    deleted_locker_usage_count = 0

    if mismatched_seat_usage_ids :
        deleted_seat_usage_count, _ = (
            SeatUsage.objects
            .filter(id__in=mismatched_seat_usage_ids)
            .delete()
        )

    if mismatched_locker_usage_ids :
        deleted_locker_usage_count, _ = (
            LockerUsage.objects
            .filter(id__in=mismatched_locker_usage_ids)
            .delete()
        )

    return {
        "deleted_seat_usage_count" : deleted_seat_usage_count,
        "deleted_locker_usage_count" : deleted_locker_usage_count,
        "deleted_seat_usage_ids" : mismatched_seat_usage_ids,
        "deleted_locker_usage_ids" : mismatched_locker_usage_ids,
    }