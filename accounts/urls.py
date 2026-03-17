from django.urls import path

from .views import (
    SignUpAPIView,
    LoginAPIView,
    RefreshAPIView,
    LogoutAPIView,
    MeAPIView,
    MyPassListAPIView,
    MyOrderListAPIView,
)

urlpatterns = [
    path("auth/signup", SignUpAPIView.as_view(), name="auth-signup"),
    path("auth/login", LoginAPIView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshAPIView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutAPIView.as_view(), name="auth-logout"),

    path("me", MeAPIView.as_view(), name="me"),
    path("me/passes", MyPassListAPIView.as_view(), name="my-passes"),
    path("me/orders", MyOrderListAPIView.as_view(), name="my-orders"),
]