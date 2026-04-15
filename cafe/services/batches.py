"""
배치 실행

자동 퇴실 대상 처리
만료 대상 처리
로그 생성
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from cafe.services.checkouts import auto_checkout_expired_normal_seats
from cafe.services.expirations import expire_due_passes
from logs.services import LogAction, LogEntityType, write_log
from cafe.services.cleanup import run_cleanup_jobs


@transaction.atomic
def run_auto_checkout(*, now=None) -> dict:
    """
    일반석 자동 퇴실 실행 wrapper
    """
    current_time = now or timezone.now()

    result = auto_checkout_expired_normal_seats(now=current_time)

    write_log(
        actor_user=None,
        target_user=None,
        action=LogAction.BATCH_AUTO_CHECKOUT_RUN,
        entity_type=LogEntityType.BATCH,
        entity_id=None,
        message="자동 퇴실 배치 실행",
        metadata={
            "executed_at": current_time.isoformat(),
            "processed_count": result["processed_count"],
            "processed_seat_usage_ids": result["processed_seat_usage_ids"],
            "processed_user_ids": result["processed_user_ids"],
        },
    )

    return result


@transaction.atomic
def run_expire_passes(*, now=None) -> dict:
    """
    pass 만료 처리 실행 wrapper
    """
    current_time = now or timezone.now()

    result = expire_due_passes(now=current_time)

    write_log(
        actor_user=None,
        target_user=None,
        action=LogAction.BATCH_PASS_EXPIRE_RUN,
        entity_type=LogEntityType.BATCH,
        entity_id=None,
        message="이용권 만료 배치 실행",
        metadata={
            "executed_at": current_time.isoformat(),
            "processed_count": result["processed_count"],
            "processed_pass_ids": result["processed_pass_ids"],
            "processed_user_ids": result["processed_user_ids"],
        },
    )

    return result


@transaction.atomic
def run_all_batches(*, now=None) -> dict:
    """
    전체 배치 실행
    현재는
    1. 일반석 자동 퇴실
    2. pass 만료 처리
    순서로 실행
    """
    current_time = now or timezone.now()

    auto_checkout_result = auto_checkout_expired_normal_seats(now=current_time)
    expire_result = expire_due_passes(now=current_time)
    cleanup_result = run_cleanup_jobs(now=current_time)

    result = {
        "executed_at": current_time,
        "auto_checkout": auto_checkout_result,
        "expire_passes": expire_result,
        "cleanup": cleanup_result,
        "total_processed_count": (
            auto_checkout_result["processed_count"]
            + expire_result["processed_count"]
            + cleanup_result["total_processed_count"]
        ),
    }

    write_log(
        actor_user=None,
        target_user=None,
        action=LogAction.BATCH_ALL_RUN,
        entity_type=LogEntityType.BATCH,
        entity_id=None,
        message="전체 배치 실행",
        metadata={
            "executed_at" : current_time.isoformat(),
            "auto_checkout_processed_count" : auto_checkout_result["processed_count"],
            "expire_processed_count" : expire_result["processed_count"],
            "cleanup_processed_count" : cleanup_result["total_processed_count"],
            "auto_checkout_seat_usage_ids" : auto_checkout_result["processed_seat_usage_ids"],
            "expire_pass_ids" : expire_result["processed_pass_ids"],
            "cleanup_deleted_seat_usage_ids" : cleanup_result["inactive_usage_cleanup"]["deleted_seat_usage_ids"],
            "cleanup_deleted_locker_usage_ids" : cleanup_result["inactive_usage_cleanup"]["deleted_locker_usage_ids"],
            "cleanup_updated_pass_ids" : cleanup_result["expired_pass_cleanup"]["updated_pass_ids"],
            "cleanup_mismatch_deleted_seat_usage_count" : cleanup_result["mismatch_cleanup"]["deleted_seat_usage_count"],
            "cleanup_mismatch_deleted_locker_usage_count" : cleanup_result["mismatch_cleanup"]["deleted_locker_usage_count"],
            "total_processed_count" : result["total_processed_count"],
        },
    )

    return result