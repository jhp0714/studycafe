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

    def validate(self, attrs):
        try:
            product = Product.objects.get(id=attrs["product_id"], is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError({"product_id":"존재하지 않거나 비활성화된 상품입니다."})

        attrs["product"] = product
        return attrs


class PaymentCreateSerailizer(serializers.Serializer):
    order_id = serializers.IntegerField()
    payment_method = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.IntegerField(min_value=0)