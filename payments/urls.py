from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ProductViewSet, AdminProductViewSet,
    OrderAPIView, OrderRetrieveAPIView,
    PaymentAPIView, PaymentRetrieveAPIView,
    PassAPIView, PassRetrieveAPIView,
    AdminRefundAPIView, AdminRefundRetrieveAPIView
)

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="products")

admin_router = DefaultRouter()
admin_router.register(r"products", AdminProductViewSet, basename="admin-products")

urlpatterns = [
    path("", include(router.urls)),
    path("admin/", include(admin_router.urls)),

    path("orders", OrderAPIView.as_view()),
    path("orders/<int:order_id>", OrderRetrieveAPIView()),

    path("payments", PaymentAPIView.as_view()),
    path("payments<int:payment_id>", PaymentRetrieveAPIView.as_view()),

    path("passes", PassAPIView.as_view()),
    path("passes/<int:pass_id>", PassRetrieveAPIView()),

    # 관리자 환불
    path("admin/refunds", AdminRefundAPIView.as_view()),
    path("admin/refunds/<int:refund_id>", AdminRefundRetrieveAPIView.as_view()),

]