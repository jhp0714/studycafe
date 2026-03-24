from rest_framework import serializers
from .models import Seat, Locker

class SeatReadSerializer(serializers.ModelSerializer):
    seatus = serializers.CharField(read_only=True)
    class Meta:
        model = Seat
        fields = [
            "id",
            "seat_no",
            "seat_type",
            "available"
        ]


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
    status = serializers.CharField(read_only=True)
    class Meta:
        model = Locker
        fields = [
            "id",
            "locker_no",
            "available",
        ]


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