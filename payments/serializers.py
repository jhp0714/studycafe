from rest_framework import serializers
from .models import Product

class ProductReadSerializer(serializers.ModelSerializer):
    duration_minutes = serializers.SerializerMethodField(required=False, allow_null=True)
    duration_days = serializers.IntegerField(required=False, allow_null=True)
    available = serializers.BooleanField(source="is_active")

    class Meta:
        models = Product
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
        duration_minutes = attrs.get("duration_minutes", None)
        duration_days = attrs.get("duration_days", None)

        if product_type is None:
            raise serializers.ValidationError({"product_type":"product_type은 필수입니다."})

        if product_type == "time":
            # 시간제 일 경우 hours 필수, days 금지
            if duration_minutes is None and not(instance and instance.duration_minutes is not None) and not self.partial:
                raise serializers.ValidationError({"duration_minutes":"시간제 상품은 duration_minutes가 필수입니다."})
            if "duration_days" in attrs and duration_days is not None:
                raise serializers.ValidationError({"duration_days":"시간제 상품은 duration_days를 가질 수 없습니다."})
        else:
            # 기간제 일 경우 days 필수, hours 금지
            if duration_days is None and not(instance and instance.duration_days is not None) and not self.partial:
                raise serializers.ValidationError({"duration_days" : "기간제 상품은 duration_days가 필수입니다."})
            if "duration_minutes" in attrs and duration_minutes is not None:
                raise serializers.ValidationError({"duration_minutes":"기간제 상품은 duration_minutes을 가질 수 없습니다."})

        return attrs

    def create(self, validated_data):
        return super().create(validated_data)

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)
