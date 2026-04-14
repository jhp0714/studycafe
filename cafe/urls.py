from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    SeatViewSet, LockerViewSet, AdminSeatViewSet, AdminLockerViewSet,
    AdminForceCheckoutAPIView, NormalSeatCheckinAPIView, NormalSeatCheckoutAPIView,
    SeatMoveAPIView, LockerMoveAPIView, NormalSeatExtendAPIView
)

router = DefaultRouter()
router.register(r"seats", SeatViewSet, basename="seats")
router.register(r"lockers", LockerViewSet, basename="lockers")

admin_router = DefaultRouter()
admin_router.register(r"seats", AdminSeatViewSet, basename="admin-seats")
admin_router.register(r"lockers", AdminLockerViewSet, basename="admin-lockers")

urlpatterns = [
    path("", include(router.urls)),
    path("admin/", include(admin_router.urls)),
    path("admin/usage/force-checkout",AdminForceCheckoutAPIView.as_view(),name="admin-foce-checkout"),

    path("usage/checkin", NormalSeatCheckinAPIView.as_view(), name="normal-seat_checkin"),
    path("usage/checkout", NormalSeatCheckoutAPIView.as_view(), name="normal-seat-checkout"),
    path("usage/move-seat", SeatMoveAPIView.as_view(), name="seat-move"),
    path("usage/move-locker", LockerMoveAPIView.as_view(), name="locker-move"),
    path("usage/extend", NormalSeatExtendAPIView.as_view(), name="normal-seat-extend"),
]