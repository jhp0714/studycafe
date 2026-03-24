from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import viewsets

class IsAdminRole(BasePermission):
    """
    accounts.User의 is_admin bool 타입 기반
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, "is_admin", False))


class AdminAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]


class AdminModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminRole]
