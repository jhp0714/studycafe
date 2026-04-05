from rest_framework import serializers
from .models import Product, Order, Payment, Refund
from cafe.models import Seat, Locker, Pass

class ProductReadSerializer(serializers.ModelSerializer):
    duration_hours = serializers.IntegerField(required=False, allow_null=True)
    duration_days = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "product_type",
            "duration_hours",
            "duration_days",
            "price",
            "is_active"
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
            if duration_hours is None and not(instance and instance.duration_hours is not None) and not self.partial:
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
    """
    상품 검증
    selection 검증
    fixed/locker라면 점유 확정
    time/flat이면 selection 금지
    """
    product_id = serializers.IntegerField()
    selection = serializers.DictField(required=False)

    def validate(self, attrs):
        user = self.context["request"].user
        selection = attrs.get("selection") or {}

        try:
            product = Product.objects.get(id=attrs["product_id"], is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError({
                "product_id": "존재하지 않거나 비활성화된 상품입니다."
            })

        pt = product.product_type
        seat_id = selection.get("seat_id")
        locker_id = selection.get("locker_id")

        selected_seat = None
        selected_locker = None

        existing_fixed = (
            Pass.objects
            .select_related("fixed_seat")
            .filter(user=user, pass_kind="fixed", status="active")
            .first()
        )
        existing_locker = (
            Pass.objects
            .select_related("locker")
            .filter(user=user, pass_kind="locker", status="active")
            .first()
        )

        if pt == "fixed":
            if existing_fixed:
                if seat_id is not None or locker_id is not None:
                    raise serializers.ValidationError({
                        "selection": "이미 지정석 이용권이 있어 좌석 선택 없이 연장됩니다."
                    })
                selected_seat = existing_fixed.fixed_seat
            else:
                if locker_id is not None:
                    raise serializers.ValidationError({
                        "selection.locker_id": "fixed 상품은 locker_id를 받을 수 없습니다."
                    })
                if seat_id is None:
                    raise serializers.ValidationError({
                        "selection.seat_id": "fixed 상품은 seat_id가 반드시 필요합니다."
                    })

                try:
                    selected_seat = Seat.objects.get(
                        id=seat_id,
                        seat_type="fixed",
                        available=True,
                    )
                except Seat.DoesNotExist:
                    raise serializers.ValidationError({
                        "selection.seat_id": "사용 가능한 지정석이 아닙니다."
                    })

                if Pass.objects.filter(
                    pass_kind="fixed",
                    status="active",
                    fixed_seat=selected_seat,
                ).exists():
                    raise serializers.ValidationError({
                        "selection.seat_id": "이미 사용 중인 지정석입니다."
                    })

        elif pt == "locker":
            if existing_locker:
                if seat_id is not None or locker_id is not None:
                    raise serializers.ValidationError({
                        "selection": "이미 사물함 이용권이 있어 선택 없이 연장됩니다."
                    })
                selected_locker = existing_locker.locker
            else:
                if seat_id is not None:
                    raise serializers.ValidationError({
                        "selection.seat_id": "locker 상품은 seat_id를 받을 수 없습니다."
                    })
                if locker_id is None:
                    raise serializers.ValidationError({
                        "selection.locker_id": "locker 상품은 locker_id가 반드시 필요합니다."
                    })

                try:
                    selected_locker = Locker.objects.get(
                        id=locker_id,
                        available=True,
                    )
                except Locker.DoesNotExist:
                    raise serializers.ValidationError({
                        "selection.locker_id": "사용 가능한 사물함이 아닙니다."
                    })

                if Pass.objects.filter(
                    pass_kind="locker",
                    status="active",
                    locker=selected_locker,
                ).exists():
                    raise serializers.ValidationError({
                        "selection.locker_id": "이미 사용 중인 사물함입니다."
                    })

        else:
            if seat_id is not None or locker_id is not None:
                raise serializers.ValidationError({
                    "selection": "time/flat 상품은 selection을 가질 수 없습니다."
                })

        attrs["product"] = product
        attrs["selected_seat"] = selected_seat
        attrs["selected_locker"] = selected_locker
        return attrs

class PaymentCreateSerailizer(serializers.Serializer):
    """
    내 주문, created 상태인지, 이미 결제되었는지인지 확인 가능
    fixed/locker 주문 중 점유가 빠졌는지 체크
    """
    order_id = serializers.IntegerField()
    payment_method = serializers.CharField(
        required=False,
        allow_blank=True,
        default="mock",
    )

    def validate(self, attrs) :
        user = self.context["request"].user

        try :
            order = (
                Order.objects
                .select_related("product", "selected_seat", "selected_locker")
                .get(id=attrs["order_id"], user=user)
            )
        except Order.DoesNotExist :
            raise serializers.ValidationError({
                "order_id" : "주문을 찾을 수 없습니다."
            })

        if order.status != Order.Status.CREATED :
            raise serializers.ValidationError({
                "order_id" : "결제 가능한 주문 상태가 아닙니다."
            })

        if order.payments.filter(status=Payment.Status.PAID).exists() :
            raise serializers.ValidationError({
                "order_id" : "이미 결제된 주문입니다."
            })

        pt = order.product.product_type

        if pt == "fixed" and order.selected_seat_id is None :
            raise serializers.ValidationError({
                "order_id" : "fixed 주문에 selected_seat이 없습니다."
            })

        if pt == "locker" and order.selected_locker_id is None :
            raise serializers.ValidationError({
                "order_id" : "locker 주문에 selected_locker가 없습니다."
            })

        if pt in ("time", "flat") :
            if order.selected_seat_id is not None or order.selected_locker_id is not None :
                raise serializers.ValidationError({
                    "order_id" : "time/flat 주문은 선택 자원을 가지면 안 됩니다."
                })

        attrs["order"] = order
        return attrs


class OrderReadSerializer(serializers.ModelSerializer):
    """
    주문 조회용 Serializer
    - 주문은 viwer에서 user로 필터
    """
    product = serializers.SerializerMethodField()
    selection = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_no",
            "status",
            "product",
            "selection",
            "created_at"
        ]

    def get_product(self, obj:Order):
        # 결제 화면/주문 상세에서 필요한 정보만
        return {
            "id":obj.product_id,
            "name":getattr(obj.product,"name",None),
            "product_type":getattr(obj.product,"product_type",None),
            "duration_hours":getattr(obj.product,"duration_hours",None),
            "duration_days" : getattr(obj.product, "duration_days", None),
            "price":getattr(obj.product,"price",None)

        }

    def get_selection(self, obj:Order):
        # Order에 selected_seat이나 selected_locker가 있다면 동작
        # 없다면 항상 None으로 반환
        return {
            "seat_id":getattr(obj, "selected_seat_id", None),
            "locker_id":getattr(obj, "selected_locker_id", None)
        }


class PaymentReadSerializer(serializers.ModelSerializer):
    """
    결제 조회용 Serializer
    - Payment는 Order와 1:1, order.user로 소유권 판단
    - 응답에 order_id와 order_status 정도는 같이 내려주면 편할듯함
    """
    order = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "status",
            "method",
            "amount",
            "paid_at",
            "created_at",
            "order"
        ]

    def get_order(self, obj:Payment):
        return {
            "id":obj.order_id,
            "status":getattr(obj.order, "status",None),
            "order_no":getattr(obj.order, "order_no",None)
        }


class PassReadSerializer(serializers.ModelSerializer):
    """
    이용권 조회용 Serializer
    - Pass는 user 소유의 데이터
    """
    product = serializers.SerializerMethodField()

    class Meta:
        model = Pass
        fields = [
            "id",
            "pass_kind",
            "status",
            "start_at",
            "end_at",
            "remaining_minutes",
            "fixed_seat_id",
            "locker_id",
            "product",
            "created_at",
        ]

    def get_product(self, obj:Pass):
        return {
            "id" : obj.product_id,
            "name" : getattr(obj.product, "name", None),
            "product_type" : getattr(obj.product, "product_type", None),
            "price" : getattr(obj.product, "price", None),
        }


class AdminRefundCreateSerializer(serializers.Serializer):
    """
    관리자 환불 생성 요청용 Serializer
    - payment_id : 환불할 결제 pk
    - amount : 환불 금액(전체 환불)
    - reason : 환불 사유(null 가능)
    """
    payment_id = serializers.IntegerField()
    amount = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=256)


class AdminRefundReadSerializer(serializers.ModelSerializer):
    """
    관리자 환불 조회용 serializer
    - payment와 admin_user에 연결되어 있다.
    """
    payment = serializers.SerializerMethodField()
    admin = serializers.SerializerMethodField()

    class Meta:
        model = Refund
        fields = [
            "id",
            "amount",
            "reason",
            "refunded_at",
            "created_at",
            "payment",
            "admin",
        ]

    def get_payment(self, obj:Refund):
        p: Payment = obj.payment
        return {
            "id":p.id,
            "amount":p.amount,
            "status":p.status,
            "method":p.method,
            "paid_at":p.paid_at,
            "order_id":p.order_id,
        }

    def get_admin(self, obj:Refund):
        u = obj.admin_user
        return {
            "id":getattr(u,"id",None),
            "phone" : getattr(u, "phone", None),
            "name" : getattr(u, "name", None),
        }