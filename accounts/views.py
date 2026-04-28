from django.core.paginator import Paginator, EmptyPage

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter, OpenApiResponse

from cafe.models import SeatUsage, LockerUsage, Pass
from payments.models import Order
from payments.serializers import PassReadSerializer, OrderReadSerializer

from .serializers import (
    SignUpSerializer, LoginSerializer,
    UserSerializer, MeSerializer
)
from common.swagger import UNAUTHORIZED_RESPONSE, VALIDATION_ERROR_RESPONSE, FORBIDDEN_RESPONSE

def ok(data=None, meta=None, status_code=200):
    payload = {"data": data if data is not None else {}}
    if meta is None:
        meta = {}
    payload["meta"] = meta
    return Response(payload, status=status_code)


def error(code, message, details=None, status_code=400):
    return Response(
        {
            "message": message,
            "code": code,
            "details": details or {},
        },
        status=status_code,
    )

@extend_schema(
    tags=["Auth"],
    summary="회원가입",
    request=SignUpSerializer,
    responses={
        201: OpenApiResponse(
            description="회원가입 성공",
            examples=[
                OpenApiExample(
                    "SignupSuccess",
                    value={
                        "data": {
                            "id": 1,
                            "phone": "01012345678",
                            "name": "홍길동",
                            "role": "USER",
                        },
                        "meta": {},
                    },
                    response_only=True,
                )
            ],
        ),
        400: VALIDATION_ERROR_RESPONSE,
    },
)
class SignUpAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "data":{
                    "id":user.id,
                    "phone":user.phone,
                    "name":user.name,
                    "role":user.role,
                },
                "meta":{},
            },
            status=status.HTTP_201_CREATED,
        )

@extend_schema(
    tags=["Auth"],
    summary="로그인",
    request=LoginSerializer,
    responses={
        200: OpenApiResponse(
            description="로그인 성공",
            examples=[
                OpenApiExample(
                    "LoginSuccess",
                    value={
                        "data": {
                            "access_token": "jwt-access-token",
                            "refresh_token": "jwt-refresh-token",
                            "user": {
                                "id": 1,
                                "name": "홍길동",
                                "role": "USER",
                            },
                        },
                        "meta": {},
                    },
                    response_only=True,
                )
            ],
        ),
        401: UNAUTHORIZED_RESPONSE,
        400: VALIDATION_ERROR_RESPONSE,
    },
)
class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request":request})
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "data":{
                    "access_token":str(refresh.access_token),
                    "refresh_token":str(refresh),
                    "user":UserSerializer(user).data
                },
                "meta":{},
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Auth"],
    summary="토큰 재발급",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "refresh_token": {"type": "string"},
            },
            "required": ["refresh_token"],
        }
    },
    responses={
        200: OpenApiResponse(
            description="재발급 성공",
            examples=[
                OpenApiExample(
                    "RefreshSuccess",
                    value={
                        "data": {
                            "access_token": "new-access-token"
                        },
                        "meta": {},
                    },
                    response_only=True,
                )
            ],
        ),
        401: UNAUTHORIZED_RESPONSE,
        400: VALIDATION_ERROR_RESPONSE,
    },
)
class RefreshAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request) :
        refresh_token = request.data.get("refresh_token")
        if not refresh_token :
            return error(
                code="VALIDATION_ERROR",
                message="refresh_token은 필수입니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try :
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            return ok(
                data={"access_token" : access_token},
                status_code=status.HTTP_200_OK,
            )
        except (TokenError, InvalidToken) :
            return error(
                code="UNAUTHORIZED",
                message="유효하지 않은 refresh_token 입니다.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )


@extend_schema(
    tags=["Auth"],
    summary="로그아웃",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "refresh_token": {"type": "string"},
            },
            "required": ["refresh_token"],
        }
    },
    responses={
        200: OpenApiResponse(
            description="로그아웃 성공",
            examples=[
                OpenApiExample(
                    "LogoutSuccess",
                    value={
                        "data": {
                            "message": "로그아웃 되었습니다."
                        },
                        "meta": {},
                    },
                    response_only=True,
                )
            ],
        ),
        401: UNAUTHORIZED_RESPONSE,
        400: VALIDATION_ERROR_RESPONSE,
        403: FORBIDDEN_RESPONSE
    },
)
class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) :
        refresh_token = request.data.get("refresh_token")
        if not refresh_token :
            return error(
                code="VALIDATION_ERROR",
                message="refresh_token은 필수입니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try :
            token = RefreshToken(refresh_token)
            if str(token.get("user_id")) != str(request.user.id) :
                return error(
                    code="FORBIDDEN",
                    message="본인의 refresh_token만 로그아웃할 수 있습니다.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            token.blacklist()

            return ok(
                data={"message" : "로그아웃 되었습니다."},
                status_code=status.HTTP_200_OK,
            )
        except (TokenError, InvalidToken) :
            return error(
                code="UNAUTHORIZED",
                message="유효하지 않은 refresh_token 입니다.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )


@extend_schema(
    tags=["Users"],
    summary="내 정보 조회",
    responses={
        200: OpenApiResponse(
            description="내 정보 조회 성공",
            examples=[
                OpenApiExample(
                    "MeSuccess",
                    value={
                        "data": {
                            "id": 1,
                            "name": "홍길동",
                            "phone": "01012345678",
                            "current_seat": {
                                "id": 10,
                                "seat_type": "normal",
                            },
                            "current_locker": None,
                        },
                        "meta": {},
                    },
                    response_only=True,
                )
            ],
        ),
        401: UNAUTHORIZED_RESPONSE,
    },
)
class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        seat_usage = (
            SeatUsage.objects
            .select_related("seat")
            .filter(user=user)
            .first()
        )

        locker_usage = (
            LockerUsage.objects
            .select_related("locker")
            .filter(user=user)
            .first()
        )

        user.active_seat_usage = seat_usage
        user.active_locker_usage = locker_usage

        return ok(data=MeSerializer(user).data)


@extend_schema(
    tags=["Users"],
    summary="내 패스 목록 조회",
    parameters=[
        OpenApiParameter(
            name="status",
            location=OpenApiParameter.QUERY,
            required=False,
            enum=["active", "expired", "canceled"],
            description="패스 상태 필터",
        ),
    ],
    responses={
        200 : OpenApiResponse(
            description="내 패스 목록 조회 성공",
            examples=[
                OpenApiExample(
                    "MyPassListSuccess",
                    value={
                        "data" : [
                            {
                                "id" : 1,
                                "pass_kind" : "time",
                                "status" : "active",
                                "start_at" : "2026-04-19T10:00:00+09:00",
                                "end_at" : None,
                                "remaining_minutes" : 180,
                                "fixed_seat_id" : None,
                                "locker_id" : None,
                                "product" : {
                                    "id" : 1,
                                    "name" : "3시간권",
                                    "product_type" : "time",
                                    "price" : 6000
                                },
                                "created_at" : "2026-04-19T10:00:00+09:00"
                            }
                        ],
                        "meta" : {
                            "count" : 1
                        }
                    },
                    response_only=True,
                )
            ],
        ),
        401 : UNAUTHORIZED_RESPONSE,
        400 : VALIDATION_ERROR_RESPONSE,
    },
)
class MyPassListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    VALID_STATUS = {"active", "expired", "canceled"}

    def get(self, request):
        qs = (
            Pass.objects
            .select_related("product", "fixed_seat", "locker")
            .filter(user=request.user)
            .order_by("-created_at","-id")
        )

        status_param = request.query_params.get("status")
        if status_param:
            if status_param not in self.VALID_STATUS:
                return error(
                    code="VALIDATION_ERROR",
                    message="status는 active, expired, canceled 중 하나여야 합니다.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            qs = qs.filter(status=status_param)

        data = PassReadSerializer(qs, many=True).data
        return ok(data=data, meta={"count":len(data)})


@extend_schema(
    tags=["Users"],
    summary="내 주문 목록 조회",
    parameters=[
        OpenApiParameter(
            name="status",
            location=OpenApiParameter.QUERY,
            required=False,
            enum=["created", "paid", "canceled", "expired"],
            description="주문 상태 필터",
        ),
        OpenApiParameter(
            name="page",
            location=OpenApiParameter.QUERY,
            required=False,
            type=int,
            description="페이지 번호",
        ),
        OpenApiParameter(
            name="size",
            location=OpenApiParameter.QUERY,
            required=False,
            type=int,
            description="페이지 크기",
        ),
    ],
    responses={
        200 : OpenApiResponse(
            description="내 주문 목록 조회 성공",
            examples=[
                OpenApiExample(
                    "MyOrderListSuccess",
                    value={
                        "data" : [
                            {
                                "id" : 10,
                                "status" : "paid",
                                "product" : {
                                    "id" : 1,
                                    "name" : "3시간권",
                                    "product_type" : "time",
                                    "price" : 6000
                                },
                                "created_at" : "2026-04-19T10:00:00+09:00"
                            }
                        ],
                        "meta" : {
                            "page" : 1,
                            "size" : 20,
                            "total" : 1,
                            "total_pages" : 1
                        }
                    },
                    response_only=True,
                )
            ],
        ),
        401 : UNAUTHORIZED_RESPONSE,
        400 : VALIDATION_ERROR_RESPONSE,
    },
)
class MyOrderListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    VALID_STATUS = {"created", "paid", "canceled", "expired"}

    def get(self, request):
        qs = (
            Order.objects
            .select_related("product")
            .filter(user=request.user)
            .order_by("-created_at","-id")
        )

        status_param = request.query_params.get("status")
        if status_param:
            if status_param not in self.VALID_STATUS:
                return error(
                    code="VALIDATION_ERROR",
                    message="status는 created, paid, canceled, expired 중 하나여야 합니다.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(status=status_param)

        try:
            page = int(request.query_params.get("page",1))
            size = int(request.query_params.get("size",20))
        except ValueError:
            return error(
                code="VALIDATION_ERROR",
                message="page와 size는 정수여야 합니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if page < 1 or size <1:
            return error(
                code="VALIDATION_ERROR",
                message="page와 size는 1 이상이어야 합니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        paginator = Paginator(qs, size)

        try:
            page_obj = paginator.page(page)
            current_page = page
        except EmptyPage:
            if paginator.num_pages == 0:
                page_obj = []
                current_page = 1
            else:
                page_obj = paginator.page(paginator.num_pages)
                current_page = paginator.num_pages

        data = OrderReadSerializer(page_obj, many=True).data

        return ok(
            data=data,
            meta={
                "page" : current_page,
                "size" : size,
                "total" : paginator.count,
                "total_pages" : paginator.num_pages,
            }
        )