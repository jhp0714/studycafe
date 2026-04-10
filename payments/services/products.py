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


def _has_available_fixed_seat() -> bool:
    occupied_fixed_seat_ids = (
        Seat.objects
        .filter(
            seat_usage__isnull=False,
            seat_type=Seat.SeatType.FIXED,
        )
        .values_list("id",flat=True)
    )

    return Seat.objects.filter(
        seat_type=Seat.SeatType.FIXED,
        available=True,
    ).exclude(id__in=occupied_fixed_seat_ids).exists()


def _has_available_locker() -> bool:
    occupied_locker_ids = (
        Locker.objects
        .filter(
            locker_usage__isnull=False,
        )
        .values_list("id",flat=True)
    )

    return Locker.objects.filter(available=True).exclude(id__in=occupied_locker_ids).exists()


def is_product_purchasable(*,product:Product,user=None) -> tuple[bool, str|None]:
    """
    반환
    - (True, None)
    - (False, reason_code)
    """
    if not product.is_active:
        return False, "product_inactive"

    product_type = product.product_type

    if product_type in (Product.ProductType.TIME, Product.ProductType.FLAT):
        return True, None

    if product_type == Product.ProductType.FIXED:
        if _has_active_pass(user=user, pass_kind=Pass.PassKind.FIXED):
            return True, None
        if _has_available_fixed_seat():
            return True, None
        return False, "fixed_seat_unavailable"

    if product_type == Product.ProductType.LOCKER:
        if _has_active_pass(user=user, pass_kind=Pass.PassKind.LOCKER):
            return True, None
        if _has_available_locker():
            return True, None
        return False, "locker_unavailable"

    return False, "unsupported_product_type"


def get_product_pourchase_status(*, product:Product, user=None) -> dict:
    is_purchasable, reason_code = is_product_purchasable(product=product, user=user)

    reason_messages = {
        "product_inactive" : "비활성 상품입니다.",
        "fixed_seat_unavailable" : "현재 선택 가능한 지정석이 없습니다.",
        "locker_unavailable" : "현재 선택 가능한 사물함이 없습니다.",
        "unsupported_product_type" : "지원하지 않는 상품 유형입니다.",
    }

    return {
        "is_purchasable" : is_purchasable,
        "reason_code" : reason_code,
        "reason_message" : reason_messages.get(reason_code),
    }