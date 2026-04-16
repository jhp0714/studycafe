from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException


class BusinessError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "BUSINESS_ERROR"

    def __init__(self, message=None, detail=None, code=None):
        self.message = message or self.default_detail
        self.detail = detail or {}
        self.code = code or self.default_code
        super().__init__(detail=self.message, code=self.code)


class ValidationBusinessError(BusinessError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "요청 값이 올바르지 않습니다."
    default_code = "VALIDATION_ERROR"


class NotFoundBusinessError(BusinessError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "요청한 리소스를 찾을 수 없습니다."
    default_code = "RESOURCE_NOT_FOUND"


class ConflictBusinessError(BusinessError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "이미 존재하거나 충돌하는 데이터입니다."
    default_code = "CONFLICT"


class PermissionBusinessError(BusinessError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "접근 권한이 없습니다."
    default_code = "FORBIDDEN"


class OrderError(BusinessError):
    default_message = "주문 처리 중 오류가 발생했습니다."
    default_code = "ORDER_ERROR"


class PaymentError(BusinessError):
    default_message = "결제 처리 중 오류가 발생했습니다."
    default_code = "PAYMENT_ERROR"


class PassError(BusinessError):
    default_message = "이용권 처리 중 오류가 발생했습니다."
    default_code = "PASS_ERROR"


class UsageError(BusinessError):
    default_message = "이용 처리 중 오류가 발생했습니다."
    default_code = "USAGE_ERROR"


class CheckinError(UsageError):
    default_message = "입실 처리 중 오류가 발생했습니다."
    default_code = "CHECKIN_ERROR"


class CheckoutError(UsageError):
    default_message = "퇴실 처리 중 오류가 발생했습니다."
    default_code = "CHECKOUT_ERROR"


class MoveError(UsageError):
    default_message = "이동 처리 중 오류가 발생했습니다."
    default_code = "MOVE_ERROR"


class LockerError(BusinessError):
    default_message = "사물함 처리 중 오류가 발생했습니다."
    default_code = "LOCKER_ERROR"


class RefundError(BusinessError):
    default_message = "환불 처리 중 오류가 발생했습니다."
    default_code = "REFUND_ERROR"


class ExpirationError(BusinessError):
    default_message = "만료 처리 중 오류가 발생했습니다."
    default_code = "EXPIRATION_ERROR"


class BatchProcessError(BusinessError):
    default_message = "배치 처리 중 오류가 발생했습니다."
    default_code = "BATCH_PROCESS_ERROR"