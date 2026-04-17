from django.core.paginator import Paginator, EmptyPage

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from cafe.models import SeatUsage, LockerUsage, Pass
from payments.models import Order
from payments.serializers import PassReadSerializer, OrderReadSerializer

from .serializers import (
    SignUpSerializer, LoginSerializer,
    UserSerializer, MeSerializer
)

def ok(data=None, meta=None, status_code=200):
    payload = {"data": data if data is not None else {}}
    if meta is None:
        meta = {}
    payload["meta"] = meta
    return Response(payload, status=status_code)


def error(code, message, details=None, status_code=400):
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
        status=status_code,
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
            if token.get("user_id") != request.user.id :
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