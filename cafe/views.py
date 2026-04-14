from django.db.models import Exists, OuterRef
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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

class SeatViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /seats?seat_type=noraml|fixed&status=used|unused&available=true|false
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
            qs = qs.filter(_is_used=False)

        return qs

    def list(self, request, *args, **kwargs):
        res = super().list(request, *args, **kwargs)
        return ok(res.data)

    def retrieve(self, request, *args, **kwargs):
        res = super().retrieve(request, *args, **kwargs)
        return ok(res.data)


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
            qs = qs.filter(_is_used=False)

        return qs

    def list(self, request, *args, **kwargs):
        res = super().list(request, *args, **kwargs)
        return ok(res.data)

    def retrieve(self, request, *args, **kwargs):
        res = super().retrieve(request, *args, **kwargs)
        return ok(res.data)



class AdminSeatViewSet(viewsets.ModelViewSet):
    """
    POST    /admin/seats
    PATCH   /admin/seats/{id}
    GET     /admin/seats
    GET     /admin/seats/{id}
    """
    serializer_class = SeatAdminWriteSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]

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


class AdminLockerViewSet(viewsets.ModelViewSet):
    """
    POST    /admin/lockers
    PATCH   /admin/lockers/{id}
    GET     /admin/lockers
    GET     /admin/lockers/{id}
    """
    serializer_class = LockerAdminWriteSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]

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


class AdminForceCheckoutAPIView(APIView):
    """
    POST /admin/usage/force-checkout

    강제 퇴실 처리 로직은 추후 구현
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


class NormalSeatCheckoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        result = checkout_normal_seat(user=request.user)
        return ok(result)


class SeatMoveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = SeatMoveSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        result = move_seat(
            user=request.user,
            to_seat_id=s.validated_data["seat_id"],
        )

        return ok(result)


class LockerMoveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = LockerMoveSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        locker_usage = move_locker(
            user=request.user,
            to_locker_id=s.validated_data["locker_id"],
        )

        return ok(
            {
                "locker_usage_id": locker_usage.id,
                "locker_id": locker_usage.locker_id,
                "pass_id": locker_usage.pass_obj_id,
                "unassign_at": locker_usage.unassign_at,
            }
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