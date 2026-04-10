"""
상품 구매 가능 여부 계산 로직
"""

from __future__ import annotations

from cafe.models import Locker, Pass, Seat
from payments.models import Product


def _has_active_pass(*,user,pass_kind:str) -> bool:
    if user is None:
        return False

    return Pass.objects.filter(
        user=user,
        pass_kind=pass_kind,
        status=Pass.Status.ACTIVE
    ).exists()