from rest_framework import serializers
from .models import Seat, Locker

class SeatReadSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    class Meta:
        model = Seat
        fields = [
            "id",
            "seat_no",
            "seat_type",
            "status",
            "available"
        ]

    def get_status(self, obj):
        is_used=getattr(obj,"_is_used", False)
        return "used" if is_used else "unused"


class AdminSeatReadSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    current_usage = serializers.SerializerMethodField()

    class Meta:
        model = Seat
        fields = [
            "id",
            "seat_no",
            "seat_type",
            "status",
            "available",
            "current_usage",
        ]

    def get_status(self, obj):
        is_used = getattr(obj, "_is_used", False)
        return "used" if is_used else "unused"

    def get_current_usage(self, obj):
        usage = (
            SeatUsage.objects
            .select_related("user", "pass_obj", "pass_obj__product")
            .filter(seat=obj)
            .first()
        )

        if usage is None:
            return None

        return {
            "id": usage.id,
            "user": {
                "id": usage.user_id,
                "phone": usage.user.phone,
                "name": usage.user.name,
                "is_admin": getattr(usage.user, "is_admin", False),
            },
            "pass": {
                "id": usage.pass_obj_id,
                "pass_kind": usage.pass_obj.pass_kind,
                "status": usage.pass_obj.status,
                "product": {
                    "id": usage.pass_obj.product_id,
                    "name": usage.pass_obj.product.name,
                    "product_type": usage.pass_obj.product.product_type,
                },
            },
            "check_in_at": usage.check_in_at,
            "expected_end_at": usage.expected_end_at,
        }

class SeatAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seat
        fields = [
            "id",
            "seat_no",
            "seat_type",
            "available"
        ]
        read_only_fields = ["id"]


class LockerReadSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()

    class Meta:
        model = Locker
        fields = [
            "id",
            "locker_no",
            "status",
            "available",
        ]

    def get_status(self, obj):
        is_used = getattr(obj, "_is_used",False)
        return "used" if is_used else "unused"


class AdminLockerReadSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    current_usage = serializers.SerializerMethodField()

    class Meta:
        model = Locker
        fields = [
            "id",
            "locker_no",
            "status",
            "available",
            "current_usage",
        ]

    def get_status(self, obj):
        is_used = getattr(obj, "_is_used", False)
        return "used" if is_used else "unused"

    def get_current_usage(self, obj):
        usage = (
            LockerUsage.objects
            .select_related("user", "pass_obj", "pass_obj__product")
            .filter(locker=obj)
            .first()
        )

        if usage is None:
            return None

        return {
            "id": usage.id,
            "user": {
                "id": usage.user_id,
                "phone": usage.user.phone,
                "name": usage.user.name,
                "is_admin": getattr(usage.user, "is_admin", False),
            },
            "pass": {
                "id": usage.pass_obj_id,
                "pass_kind": usage.pass_obj.pass_kind,
                "status": usage.pass_obj.status,
                "end_at": usage.pass_obj.end_at,
                "product": {
                    "id": usage.pass_obj.product_id,
                    "name": usage.pass_obj.product.name,
                    "product_type": usage.pass_obj.product.product_type,
                },
            },
            "assign_at": usage.assign_at,
        }


class LockerAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Locker
        fields = [
            "id",
            "locker_no",
            "available",
        ]
        read_only_fields = ["id"]


class AdminForceCheckoutSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class NormalSeatCheckinSerializer(serializers.Serializer):
    seat_id = serializers.IntegerField(min_value=1)


class SeatMoveSerializer(serializers.Serializer):
    to_seat_id = serializers.IntegerField(min_value=1)


class LockerMoveSerializer(serializers.Serializer):
    to_locker_id = serializers.IntegerField(min_value=1)


class NormalSeatExtendSerializer(serializers.Serializer):
    hours = serializers.IntegerField(min_value=1, max_value=6)