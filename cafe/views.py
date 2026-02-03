from django.db.models import Exists, OuterRef
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from .models import Seat, Locker, SeatUsage, LockerUsage
from .serializers import SeatReadSerializer, SeatAdminWriteSerializer, LockerReadSerializer, LockerAdminWriteSerializer

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
        used_exists = SeatUsage.objects.filter(seat_id=OuterRef("pk"), suatus="used")
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
        used_exists = LockerUsage.objects.filter(locker_id=OuterRef("pk"), status="used")
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
    permission_classes = [IsAdminRole]

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
    permission_classes = [IsAdminRole]

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