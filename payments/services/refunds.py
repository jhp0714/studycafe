"""
환불

payment 락
payment refunded
order canceled
pass canceled
usage 정리
refund 생성
로그 생성
"""

from __future__ import annotations

from typing import Optional

from django.db import transaction
from django.utils import timezone

from payments.models import Payment, Refund, Order
from cafe.models import Pass, SeatUsage, LockerUsage


class RefundError(Exception):
    """
    서비스 계층에서 발생하는 예외를 뷰에서 공통 에러 포맷으로 변환하기 위해 사용
    """
    def __init__(self, code:str, message:str, details:Optional[dict]=None, http_status:int=409,):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.http_status = http_status


@transaction.atomic
def create_refund(*, admin_user, payment_id:int, amount:int, reason:str|None=None,) -> Refund:
      """
      환불 처리
      트랜잭션 단위
      1. Payment 락(select_for_update), 상태 검증
      2. Refund 레코드 생성
      3. Payment.status = Refunded
      4. Order.status = canceled
      5. Pass.status = canceled order와 1:1
      6. 점유 해졔
        - fixed: SeatUsage(status=used) -> unused
        - locker : LockerUsage9status=used) -> unused
        - time/flat: 사용 중인 usage가 있다면 그 pass 기준으로 점유 좌석 unused 처리
      """
      now = timezone.now()

      # 1.Payment 락(select_for_update), 상태 검증
      payment = (
          Payment.objects
          .select_for_update()
          .select_related("order","order__user")
          .get(id=payment_id)
      )
      order:Order = payment.order

      if payment.status != Payment.Status.PAID:
          # 결제가 완료된 상태일때만
          raise RefundError(
              "CONFLICT",
              "환불 가능한 결제 상태가 아닙니다.",
              details={"payment_status":payment.status},
              http_status=409
          )

      # 일단 부분 환불 막음
      if amount != payment.amount:
          raise RefundError(
              "VALIDATION_ERROR",
              "전체 환불만 지원합니다.",
              details={"requested_amount":amount, "payment_amount":payment.amount},
              http_status=400,
          )

      # 2. Refund 레코드 생성
      refund = Refund.objects.create(
          payment=payment,
          admin_user=admin_user,
          amount=amount,
          reason=reason or None,
          refund_at=now,
      )

      # 3. Payment.status = Refunded
      payment.status = Payment.Status.REFUNDED
      payment.save(update_fields=["status"])

      # 4. Order.status = canceled
      order.status = Order.Status.CANCELED
      order.save(update_fields=["status"])

      # 5. Pass.status = canceled order와 1:1
      # 6. 점유 해졔
      p = getattr(order, "pass_obj", None)
      if p:
          # Pass canceled
          p.status = Pass.Status.CANCELED
          p.save(update_fields=["status"])

          # locker 점유 해제
          if p.pass_kind == "locker":
              LockerUsage.objects.filter(pass_obj=p).delete()
          # seat 점유 해제
          else:
              SeatUsage.objects.filter(pass_obj=p).delete()

      return refund

