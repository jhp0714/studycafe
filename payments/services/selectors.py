"""
조회 공통 함수

중복 조회 방지용
"""
from __future__ import annotations

from cafe.models import Pass
from common.exceptions import NotFoundBusinessError
from payments.models import Order, Payment, Product


def get_product_or_404(*, product_id: int) -> Product:
    product = Product.objects.filter(id=product_id).first()
    if product is None:
        raise NotFoundBusinessError(
            message="상품을 찾을 수 없습니다.",
            code="product_not_found",
            detail={"product_id": product_id},
        )
    return product


def get_order_for_user_or_404(*, user, order_id: int) -> Order:
    order = (
        Order.objects
        .select_related("product", "selected_seat", "selected_locker", "pass_obj")
        .filter(id=order_id, user=user)
        .first()
    )
    if order is None:
        raise NotFoundBusinessError(
            message="주문을 찾을 수 없습니다.",
            code="order_not_found",
            detail={"order_id": order_id},
        )
    return order


def get_payment_for_user_or_404(*, user, payment_id: int) -> Payment:
    payment = (
        Payment.objects
        .select_related("order", "order__product")
        .filter(id=payment_id, order__user=user)
        .first()
    )
    if payment is None:
        raise NotFoundBusinessError(
            message="결제를 찾을 수 없습니다.",
            code="payment_not_found",
            detail={"payment_id": payment_id},
        )
    return payment


def get_active_pass(*, user, pass_kind: str) -> Pass | None:
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