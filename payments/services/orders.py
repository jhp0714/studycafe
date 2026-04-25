"""
주문 생성

상품 활성화 여부
상품 타입별 selection 검증
fixed, locker 첫 구매시 seat/locker 필수
기존에 활성화된 fixed/locker pass 있으면 재선택 없이 연장 허용 여부 판단
좌석/사물함 선택 가능 여부 검증
로그 생성
"""
from __future__ import annotations

import uuid

from django.db import transaction

from cafe.models import Pass, Locker, Seat, SeatUsage, LockerUsage
from common.exceptions import ConflictBusinessError, NotFoundBusinessError, ValidationBusinessError
from logs.services import LogAction, LogEntityType, write_log
from payments.models import Order, Product
from payments.services.products import is_product_purchasable



def _get_active_pass(*, user, pass_kind:str) -> Pass | None:
    return (
        Pass.objects
        .filter(
            user=user,
            pass_kind=pass_kind,
            status=Pass.Status.ACTIVE,
        )
        .order_by("-id")
        .first()
    )


def _validate_selection_for_product(*,user,product:Product, seat_id:int|None,locker_id:int|None) -> tuple[Seat|None, Locker|None]:
    selected_seat = None
    selected_locker = None
    product_type = product.product_type

    if product_type in (Product.ProductType.TIME, Product.ProductType.FLAT):
        if seat_id is not None or locker_id is not None:
            raise ValidationBusinessError(
                message="시간권/기간권상품은 좌석 또는 사물함을 선택할 수 없습니다.",
                code="selection_not_allowed_for_time_or_flat"
            )
        return None, None

    if product_type == Product.ProductType.FIXED:
        if locker_id is not None:
            raise ValidationBusinessError(
                message="지정석 상품에는 사물함을 선택할 수 없습니다.",
                code="locker_not_allowed_for_fixed_product"
            )

        active_fixed_pass = _get_active_pass(user=user, pass_kind=Pass.PassKind.FIXED)

        if active_fixed_pass:
            if seat_id is not None:
                raise ValidationBusinessError(
                    message="지정석 연장 구매 시 좌석을 다시 선택할 수 없습니다.",
                    code="seat_selection_not_allowed_for_fixed_extension"
                )
            return None, None

        if seat_id is None:
            raise ValidationBusinessError(
                message="지정석 첫 구매 시 좌석 선택이 필요합니다.",
                code="seat_required_for_fixed_product"
            )

        selected_seat = Seat.objects.filter(id=seat_id).first()
        if selected_seat is None:
            raise NotFoundBusinessError(
                message="좌석을 찾을 수 없습니다.",
                code="seat_not_found",
                detail={"seat_id":seat_id}
            )

        if selected_seat.seat_type !=Seat.SeatType.FIXED:
            raise ValidationBusinessError(
                message="지정석 상품에는 지정석만 선택할 수 있습니다.",
                code="fixed_seat_only",
                detail={"seat_id":selected_seat.id,"seat_type":selected_seat.seat_type},
            )

        if not selected_seat.available:
            raise ConflictBusinessError(
                message="사용 불가능한 좌석입니다.",
                code="seat_not_available",
                detail={"seat_id":selected_seat.id}
            )

        if SeatUsage.objects.filter(seat=selected_seat).exists() :
            raise ConflictBusinessError(
                message="이미 사용 중인 지정석입니다.",
                code="fixed_seat_already_occupied",
                detail={"seat_id" : selected_seat.id},
            )
        return selected_seat, None

    if product_type == Product.ProductType.LOCKER:
        if seat_id is not None:
            raise ValidationBusinessError(
                message="사물함 상품에는 좌석을 선택할 수 없습니다.",
                code="seat_not_allowed_for_locker_product",
            )

        active_locker_pass = _get_active_pass(user=user,pass_kind=Pass.PassKind.LOCKER)

        if active_locker_pass:
            if locker_id is not None:
                raise ValidationBusinessError(
                    message="사물함 연장 구매 시 사물함을 다시 선택할 수 없습니다.",
                    code="locker_selection_not_allowed_for_locker_extension",
                )
            return None, None

        if locker_id is None:
            raise ValidationBusinessError(
                message="사물함을 첫 구매 시 사물함 선택이 필요합니다.",
                code="locker_required_for_locker_product",
                detail={"locker_id":locker_id},
            )

        selected_locker = Locker.objects.filter(id=locker_id).first()
        if selected_locker is None:
            raise NotFoundBusinessError(
                message="사물함을 찾을 수 없습니다.",
                code="locker_not_found",
                detail={"locker_id":locker_id},
            )

        if not selected_locker.available:
            raise ConflictBusinessError(
                message="사용 불가능한 사물함입니다.",
                code="locker_not_available",
                detail={"locker_id":selected_locker.id},
            )
        if LockerUsage.objects.filter(locker=selected_locker).exists() :
            raise ConflictBusinessError(
                message="이미 사용 중인 사물함입니다.",
                code="locker_already_occupied",
                detail={"locker_id" : selected_locker.id},
            )

        return None, selected_locker

    raise ValidationBusinessError(
        message="지원하지 않는 상품 유형입니다.",
        code="unsupported_product_type",
        detail={"product_type":product_type},
    )


@transaction.atomic
def create_order(*,user,product_id:int,seat_id:int|None=None,locker_id:int|None=None)->Order:
    product = Product.objects.filter(id=product_id).first()
    if product is None:
        raise NotFoundBusinessError(
            message="상품을 찾을 수 없습니다.",
            code="product_not_found",
            detail={"product_id":product_id},
        )

    is_purchasable, reason_code = is_product_purchasable(product=product, user=user)
    if not is_purchasable:
        raise ConflictBusinessError(
            message="현재 구매할 수 없는 상품입니다.",
            code=reason_code or "product_not_purchasable",
            detail={"product_id":product_id},
        )

    selected_seat, selected_locker = _validate_selection_for_product(user=user, product=product,seat_id=seat_id,locker_id=locker_id)

    order = Order.objects.create(user=user,product=product,status=Order.Status.CREATED,selected_seat=selected_seat,selected_locker=selected_locker)

    write_log(
        actor_user=user,
        target_user=user,
        action=LogAction.ORDER_CREATED,
        entity_type=LogEntityType.ORDER,
        entity_id=order.id,
        message="주문 생성 완료",
        metadata={
            "order_id":order.id,
            "product_id":product.id,
            "product_type":product.product_type,
            "selected_seat_id":selected_seat.id if selected_seat else None,
            "selected_locker_id":selected_locker.id if selected_locker else None,
        },
    )

    return order