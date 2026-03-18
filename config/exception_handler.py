from rest_framework.views import exception_handler
from rest_framework import status
from rest_framework.exceptions import (
    ValidationError,
    NotAuthenticated,
    AuthenticationFailed,
    PermissionDenied,
    NotFound,
    MethodNotAllowed,
)
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


def _extract_message_and_details(data):
    if isinstance(data, dict):
        first_value = next(iter(data.values()),"잘못된 요청입니다.")
        if isinstance(first_value, list) and first_value:
            message = str(first_value[0])
        else:
            message = str(first_value)
        return message, data

    if isinstance(data, list):
        message = str(data[0]) if data else "잘못된 요청입니다."
        return message, {"errors":data}

    return str(data), {}


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return Response(
            {
                "error":{
                    "code":"INTERNAL_SERVER_ERROR",
                    "message":"서부 내부 오류가 발생했스빈다.",
                    "deatails":{},
                }
            },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )

    if isinstance(exc, ValidationError):
        message, details = _extract_message_and_details(response.data)
        code = "VALIDATION_ERROR"

    elif isinstance(exc, (NotAuthenticated, AuthenticationFailed, InvalidToken, TokenError)):
        message, details = _extract_message_and_details(response.data)
        code = "UNAUTHORIZED"

    elif isinstance(exc, PermissionDenied):
        message, details = _extract_message_and_details(response.data)
        code = "FORBIDDEN"

    elif isinstance(exc, NotFound):
        message, details = _extract_message_and_details(response.data)
        code = "RESOURCE_NOT_FOUND"

    elif isinstance(exc, MethodNotAllowed):
        message, details = _extract_message_and_details(response.data)
        code = "METHOD_NOT_ALLOWED"

    else:
        message, details = _extract_message_and_details(response.data)
        code = "API_ERROR"

    response.data = {
        "error":{
            "code":code,
            "message":message,
            "details":details,
        }
    }
    return response