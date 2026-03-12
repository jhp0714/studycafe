from django.urls import path

from .views import SignUpAPIView, LoginAPIView                                      , RefreshAPIView, LogoutAPIView

urlpatterns = [
path("auth/signup", SignUpAPIView.as_view(), name="auth-signup"),
    path("auth/login", LoginAPIView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshAPIView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutAPIView.as_view(), name="auth-logout"),
]