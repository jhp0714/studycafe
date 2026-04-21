from __future__ import annotations

from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    ErrorDetail,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from common.exceptions import BusinessError


def _convert_error_detail(detail):
    if isinstance(detail, ErrorDetail):
        return str(detail)

    if isinstance(detail, list):
        return [_convert_error_detail(item) for item in detail]

    if isinstance(detail, dict):
        return {key: _convert_error_detail(value) for key, value in detail.items()}

    return detail


def _extract_message_and_detail(detail_data):
    if isinstance(detail_data, dict):
        if "detail" in detail_data and len(detail_data) == 1:
            return str(detail_data["detail"]), {}
        return "요청 값이 올바르지 않습니다.", detail_data

    if isinstance(detail_data, list):
        if detail_data:
            return str(detail_data[0]), detail_data
        return "요청 값이 올바르지 않습니다.", []

    return str(detail_data), {}


def custom_exception_handler(exc, context):
    # 1. 서비스 레이어 비즈니스 예외
    if isinstance(exc, BusinessError):
        return Response(
            {
                "message": exc.message,
                "code": exc.code,
                "details": exc.detail,
            },
            status=exc.status_code,
        )

    # DB 제약조건 충돌
    if isinstance(exc, IntegrityError):
        return Response(
            {
                "message": "이미 존재하거나 현재 상태에서는 처리할 수 없습니다.",
                "code": "CONFLICT",
                "details": {},
            },
            status=status.HTTP_409_CONFLICT,
        )

    # DRF 기본 예외 처리
    response = drf_exception_handler(exc, context)

    # 처리되지 않은 예외 -> 500 통일
    if response is None:
        return Response(
            {
                "message": "서버 내부 오류가 발생했습니다.",
                "code": "INTERNAL_SERVER_ERROR",
                "details": {},
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail_data = _convert_error_detail(response.data)
    message, detail = _extract_message_and_detail(detail_data)

    if isinstance(exc, ValidationError):
        code = "VALIDATION_ERROR"

    elif isinstance(exc, (NotAuthenticated, AuthenticationFailed, InvalidToken, TokenError)):
        code = "UNAUTHORIZED"

    elif isinstance(exc, PermissionDenied):
        code = "FORBIDDEN"

    elif isinstance(exc, NotFound):
        code = "RESOURCE_NOT_FOUND"

    elif isinstance(exc, MethodNotAllowed):
        code = "METHOD_NOT_ALLOWED"

    else:
        code = "API_ERROR"

    response.data = {
        "message": message,
        "code": code,
        "details": detail,
    }
    return response