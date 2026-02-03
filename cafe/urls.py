from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import SeatViewSet, LockerViewSet, AdminSeatViewSet, AdminLockerViewSet

router = DefaultRouter()
router.register(r"seats", SeatViewSet, basename="seats")
router.register(r"lockers", LockerViewSet, basename="lockers")

admin_router = DefaultRouter()
admin_router.register(r"seats", AdminSeatViewSet, basename="admin-seats")
admin_router.register(r"lockers", AdminLockerViewSet, basename="admin-lockers")

urlpatterns = [
    path("", include(router.urls)),
    path("admin/", include(admin_router.urls))
]