from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ProductViewSet, AdminProductViewSet

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="products")

admin_router = DefaultRouter()
admin_router.register(r"products", AdminProductViewSet, basename="admin-products")

urlpatterns = [
    path("", include(router.urls)),
    path("admin/", include(admin_router.urls))
]