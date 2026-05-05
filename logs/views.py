from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from .models import Log
from .serializers import AdminLogReadSerializer


def ok(data=None, meta=None, status_code=200):
    payload = {"data": data if data is not None else {}}
    if meta is not None:
        payload["meta"] = meta
    return Response(payload, status=status_code)


class AdminLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AdminLogReadSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        qs = (
            Log.objects
            .select_related("actor_user", "target_user")
            .order_by("-created_at", "-id")
        )

        action = self.request.query_params.get("action")
        if action:
            qs = qs.filter(action=action)

        entity_type = self.request.query_params.get("entity_type")
        if entity_type:
            qs = qs.filter(entity_type=entity_type)

        entity_id = self.request.query_params.get("entity_id")
        if entity_id:
            qs = qs.filter(entity_id=entity_id)

        actor_user_id = self.request.query_params.get("actor_user_id")
        if actor_user_id:
            qs = qs.filter(actor_user_id=actor_user_id)

        target_user_id = self.request.query_params.get("target_user_id")
        if target_user_id:
            qs = qs.filter(target_user_id=target_user_id)

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return ok(serializer.data, meta={"count": len(serializer.data)})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return ok(serializer.data)