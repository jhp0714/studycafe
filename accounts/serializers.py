from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from .models import User

class SignUpSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["phone","name"]

    def validate_phone(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("전화번호는 숫자만 입력해야 합니다.")
        if len(value) != 11:
            raise serializers.ValidationError("전화번호 길이가 11이 아닙니다.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            phone=validated_data["phone"],
            name=validated_data["name"]
        )

class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        phone = attrs.get("phone")
        password = attrs.get("password")

        user = authenticate(
            request=self.context.get("request"),
            phone=phone,
            password=password
        )

        if not user:
            raise AuthenticationFailed("전화번호 또는 비밀번호가 올바르지 않습니다.")

        attrs["user"] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "name", "role"]


class MeSerializer(serializers.ModelSerializer):
    current_seat = serializers.SerializerMethodField()
    current_locker = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id","name","phone","current_seat","current_locker"]

    def get_current_seat(self, obj):
        seat_usage = getattr(obj, "active_seat_usage",None)
        if not seat_usage or not seat_usage.seat_id:
            return None

        return {
            "id":seat_usage.seat_id,
            "seat_type":seat_usage.seat.seat_type,
        }

    def get_current_locker(self, obj):
        locker_usage = getattr(obj, "active_locker_usage", None)
        if not locker_usage or not locker_usage.locker_id :
            return None

        return {
            "id" : locker_usage.locker_id,
        }