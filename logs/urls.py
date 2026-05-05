from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminLogViewSet


admin_router = DefaultRouter()
admin_router.register(r"logs", AdminLogViewSet, basename="admin-logs")

urlpatterns = [
    path("admin/", include(admin_router.urls)),
]