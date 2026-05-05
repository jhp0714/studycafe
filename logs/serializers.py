from rest_framework import serializers

from .models import Log


class AdminLogReadSerializer(serializers.ModelSerializer):
    actor_user = serializers.SerializerMethodField()
    target_user = serializers.SerializerMethodField()

    class Meta:
        model = Log
        fields = [
            "id",
            "actor_user",
            "target_user",
            "action",
            "entity_type",
            "entity_id",
            "message",
            "metadata",
            "created_at",
        ]

    def get_actor_user(self, obj):
        user = obj.actor_user_id

        if user is None:
            return None

        return {
            "id":user.id,
            "phone":user.phone,
            "name":user.name,
            "is_admin":getattr(user, "is_admin",False)
        }

    def get_target_user(self, obj) :
        user = obj.target_user

        if user is None :
            return None

        return {
            "id" : user.id,
            "phone" : user.phone,
            "name" : user.name,
            "is_admin" : getattr(user, "is_admin", False),
        }