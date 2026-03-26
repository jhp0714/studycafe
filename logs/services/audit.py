"""
로그 생성
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model

from logs.models import Log


User = get_user_model()


def write_log(
    *,
    action: str,
    entity_type: str,
    actor_user: User | None = None,
    target_user: User | None = None,
    entity_id: int | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Log:
    """
    공통 로그 기록 함수

    사용 규칙
    - 서비스 레이어에서만 호출
    - 비즈니스 로직과 같은 트랜잭션 안에서 호출
    - metadata는 JSON 직렬화 가능한 값만 사용
    """

    if metadata is None:
        metadata = {}

    return Log.objects.create(
        actor_user_id=actor_user,
        target_user_id=target_user,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        message=message,
        metadata=metadata,
    )