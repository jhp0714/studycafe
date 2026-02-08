from rest_framework import serializers
from .models import Product, Order, Payment
from cafe.models import Seat, Locker, Pass

class ProductReadSerializer(serializers.ModelSerializer):
    duration_hours = serializers.SerializerMethodField(required=False, allow_null=True)
    duration_days = serializers.IntegerField(required=False, allow_null=True)
    available = serializers.BooleanField(source="is_active")

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "product_type",
            "duration_hours",
            "duration_days",
            "price",
            "available"
        ]



class AdminProductWriteSerializer(serializers.ModelSerializer):
    duration_hours = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    duration_days = serializers.IntegerField(required=False, allow_null=True, min_value=7)

    class Meta:
        model = Product
        fields = [
            "id",
            "scode",
            "name",
            "product_type",
            "duration_hours",
            "duration_days",
            "price",
            "is_active"
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        # partial update 때문에 instance 값으로 보정
        instance: Product | None = getattr(self, "instance", None)

        product_type = attrs.get("product_type") or (instance.product_type if instance else None)
        duration_hours = attrs.get("duration_hours", None)
        duration_days = attrs.get("duration_days", None)

        if product_type is None:
            raise serializers.ValidationError({"product_type":"product_type은 필수입니다."})

        if product_type == "time":
            # 시간제 일 경우 hours 필수, days 금지
            if duration_hours is None and not(instance and instance.duration_minutes is not None) and not self.partial:
                raise serializers.ValidationError({"duration_hours":"시간제 상품은 duration_hours가 필수입니다."})
            if "duration_days" in attrs and duration_days is not None:
                raise serializers.ValidationError({"duration_days":"시간제 상품은 duration_days를 가질 수 없습니다."})
        else:
            # 기간제 일 경우 days 필수, hours 금지
            if duration_days is None and not(instance and instance.duration_days is not None) and not self.partial:
                raise serializers.ValidationError({"duration_days" : "기간제 상품은 duration_days가 필수입니다."})
            if "duration_hours" in attrs and duration_hours is not None:
                raise serializers.ValidationError({"duration_hours":"기간제 상품은 duration_hours를 가질 수 없습니다."})

        return attrs

    def create(self, validated_data):
        return super().create(validated_data)

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)


class OrderCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    selection = serializers.DictField(required=False)

    def validate(self, attrs):
        user = self.context["request"].user
        product_id = attrs["product_id"]
        selection = attrs.get("selection") or {}

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError({"product_id":"존재하지 않거나 비활성화된 상품입니다."})

        pt = product.product_type
        seat_id = selection.get("seat_id")
        locker_id = selection.get("locker_id")

        # 이미 지정석 Pass 보유하고 있으면 추가 결제 시 좌석 재선택을 하지 않는다.
        existing_fixed = Pass.objects.filter(user=user, pass_kind="fixed", status="active").first()
        existing_locker = Pass.objects.filter(user=user, pass_kind="locker", status="active").first()

        if pt == "ifxed":
            # 이미 pass 보유 중이면 같은 좌석만 허용
            if existing_fixed:
                if seat_id is not None and seat_id != existing_fixed.fixed_seat_id:
                    raise serializers.ValidationError({"selection.seat_id":"이미 보유한 지정석과"})