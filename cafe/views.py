from django.db.models import Exists, OuterRef
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample, OpenApiParameter, OpenApiResponse

from common.swagger import UNAUTHORIZED_RESPONSE, FORBIDDEN_RESPONSE, VALIDATION_ERROR_RESPONSE, NOT_FOUND_RESPONSE

from accounts.permissions import IsAdminRole
from .models import Seat, Locker, SeatUsage, LockerUsage
from .serializers import (
    SeatReadSerializer, SeatAdminWriteSerializer,
    LockerReadSerializer, LockerAdminWriteSerializer,
    AdminForceCheckoutSerializer, NormalSeatCheckinSerializer,
    SeatMoveSerializer, LockerMoveSerializer,
    NormalSeatExtendSerializer,
)
from .services.checkins import checkin_normal_seat
from .services.checkouts import checkout_normal_seat, force_checkout_normal_seat
from .services.moves import move_seat, move_locker
from .services.extensions import extend_normal_seat_usage

def ok(data=None, meta=None, status_code=200):
    payload = {"data": data if data is not None else {}}
    if meta is not None:
        payload["meta"] = meta
    return Response(payload, status=status_code)

@extend_schema_view(
    list=extend_schema(
        tags=["Seats/Lockers"],
        summary="좌석 목록 조회",
        parameters=[
            OpenApiParameter("seat_type", str, OpenApiParameter.QUERY, enum=["normal", "fixed"], required=False),
            OpenApiParameter("status", str, OpenApiParameter.QUERY, enum=["used", "unused"], required=False),
            OpenApiParameter("available", bool, OpenApiParameter.QUERY, required=False),
        ],
        responses={
            200 : OpenApiResponse(
                description="좌석 목록 조회 성공",
                examples=[
                    OpenApiExample(
                        "SeatListSuccess",
                        value={
                            "data" : [
                                {
                                    "id" : 1,
                                    "seat_no" : "N1",
                                    "seat_type" : "normal",
                                    "status" : "unused",
                                    "available" : True,
                                }
                            ],
                            "meta" : {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401 : UNAUTHORIZED_RESPONSE,
        },
    ),
    retrieve=extend_schema(
        tags=["Seats/Lockers"],
        summary="좌석 상세 조회",
        responses={
            200 : OpenApiResponse(
                description="좌석 상세 조회 성공",
                examples=[
                    OpenApiExample(
                        "SeatDetailSuccess",
                        value={
                            "data" : {
                                "id" : 1,
                                "seat_no" : "N1",
                                "seat_type" : "normal",
                                "status" : "unused",
                                "available" : True,
                            },
                            "meta" : {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401 : UNAUTHORIZED_RESPONSE,
            404 : NOT_FOUND_RESPONSE,
        },
    ),
)
class SeatViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /seats?seat_type=normal|fixed&status=used|unused&available=true|false
    """
    serializer_class = SeatReadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        used_exists = SeatUsage.objects.filter(seat_id=OuterRef("pk"), )
        qs = Seat.objects.all().annotate(_is_used=Exists(used_exists)).order_by("id")

        seat_type = self.request.query_params.get("seat_type")
        if seat_type:
            qs = qs.filter(seat_type=seat_type)

        status_param = self.request.query_params.get("status")
        if status_param == "used":
            qs = qs.filter(_is_used=True)
        elif status_param == "unused":
            qs = qs.filter(_is_used=False)

        # 선택 가능한 좌석
        available = self.request.query_params.get("available")
        if available is not None and available == "true":
            qs = qs.filter(_is_used=False, available=True)

        return qs

    def list(self, request, *args, **kwargs):
        res = super().list(request, *args, **kwargs)
        return ok(res.data)

    def retrieve(self, request, *args, **kwargs):
        res = super().retrieve(request, *args, **kwargs)
        return ok(res.data)


@extend_schema_view(
    list=extend_schema(
        tags=["Seats/Lockers"],
        summary="사물함 목록 조회",
        parameters=[
            OpenApiParameter("status", str, OpenApiParameter.QUERY, enum=["used", "unused"], required=False),
            OpenApiParameter("available", bool, OpenApiParameter.QUERY, required=False),
        ],
        responses={
            200: OpenApiResponse(
                description="사물함 목록 조회 성공",
                examples=[
                    OpenApiExample(
                        "LockerListSuccess",
                        value={
                            "data": [
                                {
                                    "id": 1,
                                    "locker_no": "L1",
                                    "status": "unused",
                                    "available": True,
                                }
                            ],
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401: UNAUTHORIZED_RESPONSE,
        },
    ),
    retrieve=extend_schema(
        tags=["Seats/Lockers"],
        summary="사물함 상세 조회",
        responses={
            200: OpenApiResponse(
                description="사물함 상세 조회 성공",
                examples=[
                    OpenApiExample(
                        "LockerDetailSuccess",
                        value={
                            "data": {
                                "id": 1,
                                "locker_no": "L1",
                                "status": "unused",
                                "available": True,
                            },
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401: UNAUTHORIZED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
        },
    ),
)
class LockerViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /lockers?status=used|unused&available=true|false
    """
    serializer_class = LockerReadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        used_exists = LockerUsage.objects.filter(locker_id=OuterRef("pk"),)
        qs = Locker.objects.all().annotate(_is_used=Exists(used_exists)).order_by("id")

        status_param = self.request.query_params.get("status")
        if status_param == "used":
            qs = qs.filter(_is_used=True)
        elif status_param == "unused":
            qs = qs.filter(_is_used=False)

        available = self.request.query_params.get("available")
        if available is not None and available == "true":
            qs = qs.filter(_is_used=False, available=True)

        return qs

    def list(self, request, *args, **kwargs):
        res = super().list(request, *args, **kwargs)
        return ok(res.data)

    def retrieve(self, request, *args, **kwargs):
        res = super().retrieve(request, *args, **kwargs)
        return ok(res.data)



@extend_schema_view(
    list=extend_schema(
        tags=["Admin"],
        summary="관리자 좌석 목록 조회",
        responses={
            200: OpenApiResponse(
                description="관리자 좌석 목록 조회 성공",
                examples=[
                    OpenApiExample(
                        "AdminSeatListSuccess",
                        value={
                            "data": [
                                {
                                    "id": 1,
                                    "seat_no": "N1",
                                    "seat_type": "normal",
                                    "available": True,
                                }
                            ],
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
        },
    ),
    retrieve=extend_schema(
        tags=["Admin"],
        summary="관리자 좌석 상세 조회",
        responses={
            200: OpenApiResponse(
                description="관리자 좌석 상세 조회 성공",
                examples=[
                    OpenApiExample(
                        "AdminSeatDetailSuccess",
                        value={
                            "data": {
                                "id": 1,
                                "seat_no": "N1",
                                "seat_type": "normal",
                                "available": True,
                            },
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
        },
    ),
    create=extend_schema(
        tags=["Admin"],
        summary="관리자 좌석 생성",
        request=SeatAdminWriteSerializer,
        responses={
            201: OpenApiResponse(
                description="관리자 좌석 생성 성공",
                examples=[
                    OpenApiExample(
                        "AdminSeatCreateSuccess",
                        value={
                            "data": {
                                "id": 11,
                                "seat_no": "F1",
                                "seat_type": "fixed",
                                "available": True,
                            },
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            400: VALIDATION_ERROR_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
        },
    ),
    partial_update=extend_schema(
        tags=["Admin"],
        summary="관리자 좌석 수정",
        request=SeatAdminWriteSerializer,
        responses={
            200: OpenApiResponse(
                description="관리자 좌석 수정 성공",
                examples=[
                    OpenApiExample(
                        "AdminSeatUpdateSuccess",
                        value={
                            "data": {
                                "id": 11,
                                "seat_no": "F1",
                                "seat_type": "fixed",
                                "available": False,
                            },
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            400: VALIDATION_ERROR_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
        },
    ),
)
class AdminSeatViewSet(viewsets.ModelViewSet):
    """
    POST    /admin/seats
    PATCH   /admin/seats/{id}
    GET     /admin/seats
    GET     /admin/seats/{id}
    """
    serializer_class = SeatAdminWriteSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    http_method_names = ["get","post","patch","head","options"]

    def get_queryset(self):
        return Seat.objects.all().order_by("id")

    def list(self, request, *args, **kwargs):
        res = super().list(request, *args, **kwargs)
        return ok(res.data)

    def retrieve(self, request, *args, **kwargs):
        res = super().retrieve(request, *args, **kwargs)
        return ok(res.data)

    def create(self, request, *args, **kwargs):
        res = super().create(request, *args, **kwargs)
        return ok(res.data, status_code=201)

    def partial_update(self, request, *args, **kwargs):
        res = super().partial_update(request, *args, **kwargs)
        return ok(res.data)


@extend_schema_view(
    list=extend_schema(
        tags=["Admin"],
        summary="관리자 사물함 목록 조회",
        responses={
            200: OpenApiResponse(
                description="관리자 사물함 목록 조회 성공",
                examples=[
                    OpenApiExample(
                        "AdminLockerListSuccess",
                        value={
                            "data": [
                                {
                                    "id": 1,
                                    "locker_no": "L1",
                                    "available": True,
                                }
                            ],
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
        },
    ),
    retrieve=extend_schema(
        tags=["Admin"],
        summary="관리자 사물함 상세 조회",
        responses={
            200: OpenApiResponse(
                description="관리자 사물함 상세 조회 성공",
                examples=[
                    OpenApiExample(
                        "AdminLockerDetailSuccess",
                        value={
                            "data": {
                                "id": 1,
                                "locker_no": "L1",
                                "available": True,
                            },
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
        },
    ),
    create=extend_schema(
        tags=["Admin"],
        summary="관리자 사물함 생성",
        request=LockerAdminWriteSerializer,
        responses={
            201: OpenApiResponse(
                description="관리자 사물함 생성 성공",
                examples=[
                    OpenApiExample(
                        "AdminLockerCreateSuccess",
                        value={
                            "data": {
                                "id": 11,
                                "locker_no": "L11",
                                "available": True,
                            },
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            400: VALIDATION_ERROR_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
        },
    ),
    partial_update=extend_schema(
        tags=["Admin"],
        summary="관리자 사물함 수정",
        request=LockerAdminWriteSerializer,
        responses={
            200: OpenApiResponse(
                description="관리자 사물함 수정 성공",
                examples=[
                    OpenApiExample(
                        "AdminLockerUpdateSuccess",
                        value={
                            "data": {
                                "id": 11,
                                "locker_no": "L11",
                                "available": False,
                            },
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            400: VALIDATION_ERROR_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
        },
    ),
)
class AdminLockerViewSet(viewsets.ModelViewSet):
    """
    POST    /admin/lockers
    PATCH   /admin/lockers/{id}
    GET     /admin/lockers
    GET     /admin/lockers/{id}
    """
    serializer_class = LockerAdminWriteSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    http_method_names = ["get","post","patch","head","options"]


    def get_queryset(self) :
        return Locker.objects.all().order_by("id")

    def list(self, request, *args, **kwargs) :
        res = super().list(request, *args, **kwargs)
        return ok(res.data)

    def retrieve(self, request, *args, **kwargs) :
        res = super().retrieve(request, *args, **kwargs)
        return ok(res.data)

    def create(self, request, *args, **kwargs) :
        res = super().create(request, *args, **kwargs)
        return ok(res.data, status_code=201)

    def partial_update(self, request, *args, **kwargs) :
        res = super().partial_update(request, *args, **kwargs)
        return ok(res.data)


@extend_schema(
    tags=["Admin"],
    summary="관리자 강제 퇴실",
    request=AdminForceCheckoutSerializer,
    responses={
        200: OpenApiResponse(
            description="강제 퇴실 성공",
            examples=[
                OpenApiExample(
                    "AdminForceCheckoutSuccess",
                    value={
                        "data": {
                            "seat_usage_id": 1,
                            "seat_id": 3,
                            "seat_no": "N3",
                            "user_id": 7,
                            "pass_id": 12,
                            "pass_kind": "time",
                            "checked_out_at": "2026-04-21T18:00:00+09:00",
                            "used_minutes": 60,
                            "remaining_minutes_before": 180,
                            "remaining_minutes_after": 120,
                            "reason": "운영자 강제 퇴실",
                        },
                        "meta": {},
                    },
                    response_only=True,
                )
            ],
        ),
        400: VALIDATION_ERROR_RESPONSE,
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
    },
)
class AdminForceCheckoutAPIView(APIView):
    """
    POST /admin/usage/force-checkout
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request) :
        s = AdminForceCheckoutSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        result = force_checkout_normal_seat(
            admin_user=request.user,
            target_user_id=s.validated_data["user_id"],
            reason=s.validated_data.get("reason"),
        )

        return ok(
            {
                "seat_usage_id" : result["seat_usage_id"],
                "seat_id" : result["seat_id"],
                "seat_no" : result["seat_no"],
                "user_id" : result["user_id"],
                "pass_id" : result["pass_id"],
                "pass_kind" : result["pass_kind"],
                "checked_out_at" : result["checked_out_at"],
                "used_minutes" : result["used_minutes"],
                "remaining_minutes_before" : result["remaining_minutes_before"],
                "remaining_minutes_after" : result["remaining_minutes_after"],
                "reason" : result.get("reason"),
            }
        )


@extend_schema(
    tags=["Usage"],
    summary="일반석 입실",
    request=NormalSeatCheckinSerializer,
    responses={
        201: OpenApiResponse(
            description="입실 성공",
            examples=[
                OpenApiExample(
                    "CheckinSuccess",
                    value={
                        "data": {
                            "seat": {"id": 3},
                            "expected_end_at": "2026-01-20T21:00:00+09:00",
                        }
                    },
                    response_only=True,
                )
            ],
        ),
        400: VALIDATION_ERROR_RESPONSE,
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
    },
)
class NormalSeatCheckinAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = NormalSeatCheckinSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        seat_usage = checkin_normal_seat(user=request.user, seat_id=s.validated_data["seat_id"])

        return ok(
            {
                "seat_usage_id":seat_usage.id,
                "seat_id":seat_usage.seat_id,
                "pass_id":seat_usage.pass_obj_id,
                "pass_kind":seat_usage.pass_obj.pass_kind,
                "check_in_at":seat_usage.check_in_at,
                "expected_end_at":seat_usage.expected_end_at,
            },
            status_code=201,
        )


@extend_schema(
    tags=["Usage"],
    summary="일반석 퇴실",
    request={
        "application/json": {
            "type": "object",
            "properties": {},
        }
    },
    responses={
        200 : OpenApiResponse(
            description="퇴실 성공",
            examples=[
                OpenApiExample(
                    "CheckoutSuccess",
                    value={
                        "data" : {
                            "seat_usage_id" : 1,
                            "seat_id" : 3,
                            "pass_id" : 12,
                            "pass_kind" : "time",
                            "checked_out_at" : "2026-04-21T19:00:00+09:00",
                            "used_minutes" : 60,
                            "remaining_minutes_before" : 180,
                            "remaining_minutes_after" : 120,
                        },
                        "meta" : {},
                    },
                    response_only=True,
                )
            ],
        ),
        401 : UNAUTHORIZED_RESPONSE,
        403 : FORBIDDEN_RESPONSE,
    },
)
class NormalSeatCheckoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        result = checkout_normal_seat(user=request.user)
        return ok(result)


@extend_schema(
    tags=["Usage"],
    summary="좌석 이동",
    request=SeatMoveSerializer,
    responses={
        200 : OpenApiResponse(
            description="좌석 이동 성공",
            examples=[
                OpenApiExample(
                    "SeatMoveSuccess",
                    value={
                        "data" : {
                            "seat_usage_id" : 1,
                            "seat_id" : 5,
                            "pass_id" : 12,
                            "pass_kind" : "time",
                            "check_in_at" : "2026-04-21T18:00:00+09:00",
                            "expected_end_at" : "2026-04-21T21:00:00+09:00",
                        },
                        "meta" : {},
                    },
                    response_only=True,
                )
            ],
        ),
        400 : VALIDATION_ERROR_RESPONSE,
        401 : UNAUTHORIZED_RESPONSE,
        403 : FORBIDDEN_RESPONSE,
    },
)
class SeatMoveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = SeatMoveSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        result = move_seat(
            user=request.user,
            to_seat_id=s.validated_data["to_seat_id"],
        )

        return ok(result)


@extend_schema(
    tags=["Usage"],
    summary="사물함 이동",
    request=LockerMoveSerializer,
    responses={
        200 : OpenApiResponse(
            description="사물함 이동 성공",
            examples=[
                OpenApiExample(
                    "LockerMoveSuccess",
                    value={
                        "data" : {
                            "locker_usage_id" : 1,
                            "locker_id" : 3,
                            "pass_id" : 12,
                            "unassign_at" : "2026-05-01T00:00:00+09:00",
                        },
                        "meta" : {},
                    },
                    response_only=True,
                )
            ],
        ),
        400 : VALIDATION_ERROR_RESPONSE,
        401 : UNAUTHORIZED_RESPONSE,
        403 : FORBIDDEN_RESPONSE,
    },
)
class LockerMoveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = LockerMoveSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        locker_usage = move_locker(
            user=request.user,
            to_locker_id=s.validated_data["to_locker_id"],
        )

        return ok(
            {
                "locker_usage_id": locker_usage.id,
                "locker_id": locker_usage.locker_id,
                "pass_id": locker_usage.pass_obj_id,
                "unassign_at": locker_usage.unassign_at,
            }
        )


@extend_schema(
    tags=["Usage"],
    summary="일반석 이용 시간 연장",
    request=NormalSeatExtendSerializer,
    responses={
        200 : OpenApiResponse(
            description="연장 성공",
            examples=[
                OpenApiExample(
                    "ExtendSuccess",
                    value={
                        "data" : {
                            "seat_usage_id" : 1,
                            "seat_id" : 3,
                            "pass_id" : 12,
                            "pass_kind" : "time",
                            "expected_end_at" : "2026-04-21T23:00:00+09:00",
                        },
                        "meta" : {},
                    },
                    response_only=True,
                )
            ],
        ),
        400 : VALIDATION_ERROR_RESPONSE,
        401 : UNAUTHORIZED_RESPONSE,
        403 : FORBIDDEN_RESPONSE,
    },
)
class NormalSeatExtendAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = NormalSeatExtendSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        seat_usage = extend_normal_seat_usage(
            user=request.user,
            hours=s.validated_data["hours"],
        )

        return ok(
            {
                "seat_usage_id": seat_usage.id,
                "seat_id": seat_usage.seat_id,
                "pass_id": seat_usage.pass_obj_id,
                "pass_kind": seat_usage.pass_obj.pass_kind,
                "expected_end_at": seat_usage.expected_end_at,
            }
        )