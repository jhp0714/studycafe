from rest_framework import serializers
from .models import Product, Order, Payment, Refund
from cafe.models import Seat, Locker, Pass
from .services.products import get_product_purchase_status

class ProductReadSerializer(serializers.ModelSerializer):
    duration_hours = serializers.IntegerField(required=False, allow_null=True)
    duration_days = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField()

    is_purchasable = serializers.SerializerMethodField()
    purchase_block_reason = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "product_type",
            "duration_hours",
            "duration_days",
            "price",
            "is_active",
            "is_purchasable",
            "purchase_block_reason",
        ]

    def _get_status_info(self, obj):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None
        return get_product_purchase_status(product=obj, user=user)

    def get_is_purchasable(self, obj):
        return self._get_status_info(obj)["is_purchasable"]

    def get_purchase_block_reason(self, obj):
        return self._get_status_info(obj)["reason_code"]



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
    product_id = serializers.IntegerField(min_value=1)
    seat_id = serializers.IntegerField(min_value=1, required=False)
    locker_id = serializers.IntegerField(min_value=1, required=False)

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