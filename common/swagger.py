from drf_spectacular.utils import OpenApiExample, OpenApiResponse

UNAUTHORIZED_RESPONSE = OpenApiResponse(
    description="인증 실패",
    examples=[
        OpenApiExample(
            "Unauthorized",
            value={
                "message": "인증 정보가 없습니다.",
                "code": "UNAUTHORIZED",
                "details": {},
            },
            response_only=True,
        )
    ],
)

FORBIDDEN_RESPONSE = OpenApiResponse(
    description="권한 없음",
    examples=[
        OpenApiExample(
            "Forbidden",
            value={
                "message": "접근 권한이 없습니다.",
                "code": "FORBIDDEN",
                "details": {},
            },
            response_only=True,
        )
    ],
)

VALIDATION_ERROR_RESPONSE = OpenApiResponse(
    description="요청 값 검증 실패",
    examples=[
        OpenApiExample(
            "ValidationError",
            value={
                "message": "요청 값이 올바르지 않습니다.",
                "code": "VALIDATION_ERROR",
                "details": {},
            },
            response_only=True,
        )
    ],
)

NOT_FOUND_RESPONSE = OpenApiResponse(
    description="리소스를 찾을 수 없음",
    examples=[
        OpenApiExample(
            "NotFound",
            value={
                "message": "대상을 찾을 수 없습니다.",
                "code": "RESOURCE_NOT_FOUND",
                "details": {},
            },
            response_only=True,
        )
    ],
)