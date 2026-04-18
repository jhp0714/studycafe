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


class SeatAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seat
        fields = [
            "id",
            "seat_no",
            "seat_type",
            "available"
        ]


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


class LockerAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Locker
        fields = [
            "id",
            "locker_no",
            "available",
        ]


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