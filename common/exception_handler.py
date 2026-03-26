from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from common.exceptions import BusinessError


def _convert_error_detail(detail):
    """
    DRF의 ErrorDetail / list / dict 구조를
    일반 python 타입으로 변환
    """
    if isinstance(detail, ErrorDetail):
        return str(detail)

    if isinstance(detail, list):
        return [_convert_error_detail(item) for item in detail]

    if isinstance(detail, dict):
        return {key: _convert_error_detail(value) for key, value in detail.items()}

    return detail


def custom_exception_handler(exc, context):
    """
    프로젝트 전역 예외 핸들러

    응답 형식:
    {
        "message": "...",
        "code": "...",
        "detail": {... 또는 []}
    }
    """

    # 1. 서비스 레이어 비즈니스 예외
    if isinstance(exc, BusinessError):
        return Response(
            {
                "message": exc.message,
                "code": exc.code,
                "detail": exc.detail,
            },
            status=exc.status_code,
        )

    # 2. DRF 기본 예외 처리
    response = drf_exception_handler(exc, context)
    if response is None:
        return response

    detail_data = _convert_error_detail(response.data)

    message = "요청 처리 중 오류가 발생했습니다."
    code = "api_error"

    if isinstance(detail_data, dict):
        # DRF 기본 형식: {"detail": "..."} 인 경우
        if "detail" in detail_data and len(detail_data) == 1:
            message = detail_data["detail"]
            code = getattr(exc, "default_code", "api_error")
            detail = {}
        else:
            message = "요청 값이 올바르지 않습니다."
            code = "validation_error"
            detail = detail_data

    elif isinstance(detail_data, list):
        message = "요청 값이 올바르지 않습니다."
        code = "validation_error"
        detail = detail_data

    else:
        message = str(detail_data)
        code = getattr(exc, "default_code", "api_error")
        detail = {}

    response.data = {
        "message": message,
        "code": code,
        "detail": detail,
    }
    return response