from __future__ import annotations

from typing import Any


class BusinessError(Exception):
    """
    모든 비즈니스 예외의 부모 클래스

    사용 목적:
    - 서비스 레이어에서 raise
    - 전역 exception handler에서 일관된 응답으로 변환
    """

    default_message = "비즈니스 로직 처리 중 오류가 발생했습니다."
    default_code = "business_error"
    default_status_code = 400

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.status_code = status_code or self.default_status_code
        self.detail = detail or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "code": self.code,
            "detail": self.detail,
        }


class ValidationBusinessError(BusinessError):
    default_message = "요청 값이 올바르지 않습니다."
    default_code = "validation_business_error"
    default_status_code = 400


class NotFoundBusinessError(BusinessError):
    default_message = "대상을 찾을 수 없습니다."
    default_code = "not_found_business_error"
    default_status_code = 404


class ConflictBusinessError(BusinessError):
    default_message = "현재 상태에서는 처리할 수 없습니다."
    default_code = "conflict_business_error"
    default_status_code = 409


class PermissionBusinessError(BusinessError):
    default_message = "해당 작업을 수행할 권한이 없습니다."
    default_code = "permission_business_error"
    default_status_code = 403


class OrderError(BusinessError):
    default_message = "주문 처리 중 오류가 발생했습니다."
    default_code = "order_error"


class PaymentError(BusinessError):
    default_message = "결제 처리 중 오류가 발생했습니다."
    default_code = "payment_error"


class PassError(BusinessError):
    default_message = "이용권 처리 중 오류가 발생했습니다."
    default_code = "pass_error"


class UsageError(BusinessError):
    default_message = "이용 처리 중 오류가 발생했습니다."
    default_code = "usage_error"


class CheckinError(UsageError):
    default_message = "입실 처리 중 오류가 발생했습니다."
    default_code = "checkin_error"


class CheckoutError(UsageError):
    default_message = "퇴실 처리 중 오류가 발생했습니다."
    default_code = "checkout_error"


class MoveError(UsageError):
    default_message = "이동 처리 중 오류가 발생했습니다."
    default_code = "move_error"


class LockerError(BusinessError):
    default_message = "사물함 처리 중 오류가 발생했습니다."
    default_code = "locker_error"


class RefundError(BusinessError):
    default_message = "환불 처리 중 오류가 발생했습니다."
    default_code = "refund_error"


class ExpirationError(BusinessError):
    default_message = "만료 처리 중 오류가 발생했습니다."
    default_code = "expiration_error"


class BatchProcessError(BusinessError):
    default_message = "배치 처리 중 오류가 발생했습니다."
    default_code = "batch_process_error"