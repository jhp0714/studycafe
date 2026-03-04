import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from .models import Product, Order, Payment
from cafe.models import Pass, SeatUsage, LockerUsage
from .serializers import ProductReadSerializer, AdminProductWriteSerializer, OrderCreateSerializer, PaymentCreateSerailizer

def ok(data=None, meta=None, status_code=201):
    payload = {"data":data if data is not None else {}}
    if meta is not None:
        payload["meta"] = meta
    return Response(payload, status=status_code)

def gen_order_no() -> str:
    return f"ORD-{uuid.uuid4().hex[:20]}"

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /products?available=true&product_type=time|flat|fixed|locker
    GET /products/{id}
    """
    serializer_class = ProductReadSerializer
    permission_classes = [IsAuthenticated]      # 회원만

    def get_queryset(self):
        qs = Product.objects.all().order_by("id")
        product_type = self.request.query_params.get("product_type")

        if product_type:
            qs = qs.filter(product_type=product_type)

        available = self.request.query_params.get("available")
        if available is not None:
            if available == "true":
                qs = qs.filter(is_active=True)
            elif available == "false":
                qs = qs.filter(is_active=False)

        return qs

    def list(self, request, *args, **kwargs):
        res = super().list(request, *args, **kwargs)
        return ok(res.data)

    def retrieve(self, request, *args, **kwargs):
        res = super().retrieve(request, *args, **kwargs)
        return ok(res.data)


class AdminProductViewSet(viewsets.ModelViewSet):
    """
    POST    /admin/products
    PATCH   /admin/products/{id}
    GET     /admin/products
    GET     /admin/products/{id}
    """
    serializer_class = AdminProductWriteSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        return Product.objects.all().order_by("id")

    def list(self, request, *args, **kwargs):
        res = super().list(request, *args, **kwargs)
        return ok(res.data)

    def retrieve(self, request, *args, **kwargs):
        res = super().retrieve(request, *args, **kwargs)
        return ok(res.data)

    def create(self, request, *args, **kwargs):
        res = super().create(request, *args, **kwargs)
        return ok(res.data)

class OrderCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = OrderCreateSerializer(data=request.data, context={"request":request})
        s.is_valid(raise_exception=True)

        product = s.validated_data["product"]
        selected_seat = s.validated_data.get("selected_seat")
        selected_locker = s.validated_data.get("selected_locker")

        order = Order(
            order_no=gen_order_no(),
            user=request.user,
            product=product,
            selected_seat=selected_seat,
            selected_locker=selected_locker,
            status=Order.Status.CREATE,
        )
        order.full_clean()
        order.save()

        return ok(
            {"order_id":order.id, "order_status":order.status}, status_code=201
        )


class PaymentCreateAPIView(APIView):
    """
    결제 확정
    - Payment(amount/status/method/paid_at)
    - Order(status=paid)
    - Pass 생성/연장
    - fixed/locker: 결제 완료 시 Pass + 좌석 점유 생성
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        s = PaymentCreateSerailizer(data=request.data, context={"request":request})
        s.is_valid(raise_exception=True)

        order = (
            Order.objects
            .select_for_update()
            .select_related("product","selected_seat","selected_locker")
            .get(id=s.validated_data["order"].id)
        )

        if hasattr(order, "payment"):
            return ok({"message":"이미 결제된 주문입니다."}, status_code=400)

        now = timezone.now()
        product = order.product
        pt = product.product_type

        # 결제 생성: amount는 항상 product.price(수량은 항상 1이다.)
        payment = Payment.objects.create(
            order=order,
            amount=product.price,
            status=Payment.Status.PAID,
            method=(request.data.get("payment_method") or "mock"),
            paid_at=now,
        )

        order.status = Order.Status.PAID
        order.save(update_fields=["status"])

        # Pass 생성/연장
        base_end = None

        if pt in ("fixed","locker"):
            existing = (
                Pass.objects.select_for_update()
                .filter(user=order.user, pass_kind=pt, status="active").first()
            )
            if existing:
                base_end = existing.end_at or now
                existing.status = Pass.Status.EXPIRED
                existing.save(update_fields=["status"])

                # 기존 점유 종료
                if pt == "fixed" :
                    SeatUsage.objects.select_for_update().filter(user=order.user, status="used").update(
                        status="unused"
                    )
                else :
                    LockerUsage.objects.select_for_update().filter(user=order.user, status="used").update(
                        status="unused", unassign_at=now
                    )

            pass_obj = Pass(
                user=order.user,
                product=product,
                order=order,
                pass_kind=pt,
                status=Pass.Status.ACTIVE,
                start_at=now,
            )

            if pt == "time" :
                pass_obj.remaining_minutes = (product.duration_hours or 0) * 60
            else :
                start_base = base_end if (base_end and base_end > now) else now
                pass_obj.end_at = start_base + timedelta(days=(product.duration_days or 0))

            if pt == "fixed" :
                pass_obj.fixed_seat = order.selected_seat
            if pt == "locker" :
                pass_obj.locker = order.selected_locker

            pass_obj.full_clean()
            pass_obj.save()

            # fixed/locker는 결제 시점에 Usage 생성
            if pt == "fixed" :
                SeatUsage.objects.create(
                    user=order.user,
                    pass_obj=pass_obj,
                    seat=order.selected_seat,
                    check_in_at=now,
                    expected_end_at=pass_obj.end_at,
                    status=SeatUsage.Status.USED,
                )

            if pt == "locker" :
                LockerUsage.objects.create(
                    user=order.user,
                    pass_obj=pass_obj,
                    locker=order.selected_locker,
                    assign_at=now,
                    status=LockerUsage.Status.USED,
                )

            return ok(
                {
                    "payment_id" : payment.id,
                    "payment_status" : payment.status,
                    "order" : {"id" : order.id, "status" : order.status},
                    "pass" : {"id" : pass_obj.id, "pass_kind" : pass_obj.pass_kind, "status" : pass_obj.status},
                },
                status_code=201
            )