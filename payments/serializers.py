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
        selection = attrs.get("selection") or {}

        try :
            product = Product.objects.get(id=attrs["product_id"], is_active=True)
        except Product.DoesNotExist :
            raise serializers.ValidationError({"product_id" : "존재하지 않거나 비활성화된 상품입니다."})

        pt = product.product_type
        seat_id = selection.get("seat_id")
        locker_id = selection.get("locker_id")

        selected_seat = None
        selected_locker = None

        # 상품 연장 : 이미 pass가 있는 경우 이므로 selection 없이 주문 생성(기존 좌석/사물함 유지)
        existing_fixed = Pass.objects.filter(user=user, pass_kind="fixed", status="active").selected_reated("fixed_seat").first()
        existing_locker = Pass.objects.filter(user=user, pass_kind="locker", status="active").selected_reated("locker").first()

        if pt == "fixed":
            # 연장은 selection은 받지 않음
            if existing_fixed:
                if seat_id is not None:
                    raise serializers.ValidationError({"selection":"이미 지정석 이용권이 있어 좌석 선택 없이 연장됩니다. "})
                selected_seat = existing_fixed.fixed_seat
            else:
                if locker_id is not None:
                    raise serializers.ValidationError({"selection.locker_id" : "fixed 상품은 locker_id를 받을 수 없습니다."})
                if seat_id is None:
                    raise serializers.ValidationError({"selection.seat_id" : "fixed 상품은 seat_id가 반드시 있어야합니다."})

                try:
                    selected_seat = Seat.objects.get(id=seat_id, seat_type="fixed", available=True)
                except Seat.DoesNotExist:
                    raise serializers.ValidationError({"selection.seat_id":"사용 불가한 지정석입니다."})

                # 현재 사용 중인 좌석 선택시 주문 단계에서 차단
                if Pass.objects.filter(pass_kind="fixed", status="active", fixed_seat=selected_seat).exists():
                    raise serializers.ValidationError({"selection.seat_id":"해당 지정석은 사용 중입니다."})

        elif pt == "locker":
            if existing_locker:
                if locker_id is not None:
                    raise serializers.ValidationError({"selection" : "이미 사물함 이용권이 있어 사물함 선택 없이 연장됩니다."})
                selected_locker = existing_locker.locker
            else:
                if seat_id is not None:
                    raise serializers.ValidationError({"selection.seat_id":"locker 상품은 seat_id를 받을 수 없습니다."})
                if locker_id is None:
                    raise serializers.ValidationError({"selection.locker_id":"locker 상품은 locker_id가 반드시 있어야 합니다."})

                try:
                    selected_locker = Locker.objects.get(id-locker_id, available=True)
                except Locker.DoesNotExist:
                    raise serializers.ValidationError({"selection.locker_id":"사용 불가한 사물함입니다."})

                if Pass.objects.filter(pass_kind="locker", status="active", locker=selected_locker).exists():
                    raise serializers.ValidationError({"selection.locker_id":"해당 사물함은 사용 중인 사물함입니다."})

        else:   #time/flat
            if seat_id is not None or locker_id is not None:
                raise serializers.ValidationError({"selection":"time/flat 상품은 selection을 가질 수 없습니다."})

        attrs["product"] = product
        attrs["selected_seat"] = selected_seat
        attrs["selected_locker"] = selected_locker
        return attrs

class PaymentCreateSerailizer(serializers.Serializer):
    order_id = serializers.IntegerField()
    payment_method = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        user = self.context["request"].user
        try:
            order = Order.objects.selected_related("product","selected_seat","selected_locker").get(id=attrs["order_id"], user=user)
        except Order.DoesNotExist:
            raise serializers.ValidationError({"order_id":"주문을 찾을 수 없습니다."})

        if order.status != Order.Status.CREATE:
            raise serializers.ValidationError({"order_id":"결제 가능한 주문 상태(created)가 아닙니다."})

        # selection은 order에 저장되므로 여기서 추가 입력이 필요하지 않음
        pt = order.product.product_type
        if pt == "fixed" and order.selected_seat_id is None:
            raise serializers.ValidationError({"order_id":"fixed 주문에 selected_seat이 없습니다."})
        if pt == "locker" and order.selected_locker_id is None:
            raise serializers.ValidationError({"order_id":"locker 주문에 selected_locker이 없습니다."})

        attrs["order"] = order
        return attrs
