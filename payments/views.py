import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample, OpenApiParameter, OpenApiResponse

from common.swagger import UNAUTHORIZED_RESPONSE, FORBIDDEN_RESPONSE, VALIDATION_ERROR_RESPONSE, NOT_FOUND_RESPONSE

from accounts.permissions import IsAdminRole, AdminModelViewSet, AdminAPIView
from .models import Product, Order, Payment, Refund
from cafe.models import Pass, SeatUsage, LockerUsage
from .serializers import (
    ProductReadSerializer, AdminProductWriteSerializer,
    OrderCreateSerializer, PaymentCreateSerializer,
    OrderReadSerializer, PaymentReadSerializer, PassReadSerializer,
    AdminRefundReadSerializer, AdminRefundCreateSerializer
)
from .services.refunds import create_refund, RefundError
from .services.payments import pay_order
from .services.orders import create_order
from .services.products import get_product_purchase_status, build_purchase_availability_context


def ok(data=None, meta=None, status_code=200):
    payload = {"data": data if data is not None else {}}
    if meta is not None:
        payload["meta"] = meta
    return Response(payload, status=status_code)

def gen_order_no() -> str:
    return f"ORD-{uuid.uuid4().hex[:20]}"

@extend_schema_view(
    list=extend_schema(
        tags=["Products"],
        summary="상품 목록 조회",
        parameters=[
            OpenApiParameter("product_type", str, OpenApiParameter.QUERY, enum=["time", "flat", "fixed", "locker"], required=False),
            OpenApiParameter("is_active", bool, OpenApiParameter.QUERY, required=False),
        ],
        responses={
            200 : OpenApiResponse(
                description="상품 목록 조회 성공",
                examples=[
                    OpenApiExample(
                        "ProductListSuccess",
                        value={
                            "data" : [
                                {
                                    "id" : 1,
                                    "name" : "3시간권",
                                    "product_type" : "time",
                                    "price" : 6000,
                                    "duration_hours" : 3,
                                    "duration_days" : None,
                                    "is_active" : True,
                                    "can_purchase" : True,
                                    "purchase_block_reason" : None,
                                }
                            ],
                            "meta" : {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401 : UNAUTHORIZED_RESPONSE,
        },
    ),
    retrieve=extend_schema(
        tags=["Products"],
        summary="상품 상세 조회",
        responses={
            200 : OpenApiResponse(
                description="상품 상세 조회 성공",
                examples=[
                    OpenApiExample(
                        "ProductDetailSuccess",
                        value={
                            "data" : {
                                "id" : 1,
                                "name" : "3시간권",
                                "product_type" : "time",
                                "price" : 6000,
                                "duration_hours" : 3,
                                "duration_days" : None,
                                "is_active" : True,
                                "can_purchase" : True,
                                "purchase_block_reason" : None,
                            },
                            "meta" : {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401 : UNAUTHORIZED_RESPONSE,
            404 : NOT_FOUND_RESPONSE,
        },
    ),
)
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

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            if is_active == "true":
                qs = qs.filter(is_active=True)
            elif is_active == "false":
                qs = qs.filter(is_active=False)

        return qs

    def _build_purchase_context(self, *, product_types) :
        request = self.request
        user = request.user if request.user.is_authenticated else None
        return build_purchase_availability_context(
            user=user,
            needed_product_types=product_types,
        )

    def list(self, request, *args, **kwargs) :
        queryset = self.filter_queryset(self.get_queryset())
        product_types = set(queryset.values_list("product_type", flat=True).distinct())

        context = {
            **self.get_serializer_context(),
            "product_purchase_context" : self._build_purchase_context(product_types=product_types),
        }

        serializer = self.get_serializer(queryset, many=True, context=context)
        return ok(serializer.data)

    def retrieve(self, request, *args, **kwargs) :
        instance = self.get_object()

        context = {
            **self.get_serializer_context(),
            "product_purchase_context" : self._build_purchase_context(
                product_types={instance.product_type}
            ),
        }

        serializer = self.get_serializer(instance, context=context)
        return ok(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=["Admin"],
        summary="관리자 상품 목록 조회",
        responses={
            200: OpenApiResponse(
                description="관리자 상품 목록 조회 성공",
                examples=[
                    OpenApiExample(
                        "AdminProductListSuccess",
                        value={
                            "data": [
                                {
                                    "id": 1,
                                    "name": "3시간권",
                                    "product_type": "time",
                                    "price": 6000,
                                    "duration_hours": 3,
                                    "duration_days": None,
                                    "is_active": True,
                                }
                            ],
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
        },
    ),
    retrieve=extend_schema(
        tags=["Admin"],
        summary="관리자 상품 상세 조회",
        responses={
            200: OpenApiResponse(
                description="관리자 상품 상세 조회 성공",
                examples=[
                    OpenApiExample(
                        "AdminProductDetailSuccess",
                        value={
                            "data": {
                                "id": 1,
                                "name": "3시간권",
                                "product_type": "time",
                                "price": 6000,
                                "duration_hours": 3,
                                "duration_days": None,
                                "is_active": True,
                            },
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
        },
    ),
    create=extend_schema(
        tags=["Admin"],
        summary="관리자 상품 생성",
        request=AdminProductWriteSerializer,
        responses={
            201: OpenApiResponse(
                description="관리자 상품 생성 성공",
                examples=[
                    OpenApiExample(
                        "AdminProductCreateSuccess",
                        value={
                            "data": {
                                "id": 11,
                                "name": "1일권",
                                "product_type": "flat",
                                "price": 15000,
                                "duration_hours": None,
                                "duration_days": 1,
                                "is_active": True,
                            },
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            400: VALIDATION_ERROR_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
        },
    ),
    partial_update=extend_schema(
        tags=["Admin"],
        summary="관리자 상품 수정",
        request=AdminProductWriteSerializer,
        responses={
            200: OpenApiResponse(
                description="관리자 상품 수정 성공",
                examples=[
                    OpenApiExample(
                        "AdminProductUpdateSuccess",
                        value={
                            "data": {
                                "id": 11,
                                "name": "1일권",
                                "product_type": "flat",
                                "price": 17000,
                                "duration_hours": None,
                                "duration_days": 1,
                                "is_active": True,
                            },
                            "meta": {},
                        },
                        response_only=True,
                    )
                ],
            ),
            400: VALIDATION_ERROR_RESPONSE,
            401: UNAUTHORIZED_RESPONSE,
            403: FORBIDDEN_RESPONSE,
            404: NOT_FOUND_RESPONSE,
        },
    ),
)
class AdminProductViewSet(AdminModelViewSet):
    """
    POST    /admin/products
    PATCH   /admin/products/{id}
    GET     /admin/products
    GET     /admin/products/{id}
    """
    serializer_class = AdminProductWriteSerializer
    http_method_names = ["get","post","patch","head","options"]

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
        return ok(res.data, status_code=201)



@extend_schema(
    tags=["Orders/Payments/Passes"],
    summary="주문 상세 조회",
    responses={
        200 : OpenApiResponse(
            description="주문 상세 조회 성공",
            examples=[
                OpenApiExample(
                    "OrderDetailSuccess",
                    value={
                        "data" : {
                            "id" : 10,
                            "order_no" : "ORD-1234567890ABCDEFGH",
                            "status" : "created",
                            "product" : {
                                "id" : 1,
                                "name" : "3시간권",
                                "product_type" : "time",
                                "price" : 6000,
                            },
                            "selected_seat_id" : None,
                            "selected_locker_id" : None,
                            "created_at" : "2026-04-20T10:00:00+09:00",
                        },
                        "meta" : {},
                    },
                    response_only=True,
                )
            ],
        ),
        401 : UNAUTHORIZED_RESPONSE,
        404 : NOT_FOUND_RESPONSE,
    },
)
class OrderRetrieveAPIView(APIView):
    """
    GET /orders/{id}
    - 소유권 : 반드시 order.user == request.user 여야 함
    - pk로 조회할 때 user 필터를 걸어아햠
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id:int):
        order = get_object_or_404(
            Order.objects.select_related("product"),
            id=order_id,
            user=request.user
        )
        data = OrderReadSerializer(order).data
        return ok(data)


@extend_schema(
    tags=["Orders/Payments/Passes"],
    summary="결제 상세 조회",
    responses={
        200 : OpenApiResponse(
            description="결제 상세 조회 성공",
            examples=[
                OpenApiExample(
                    "PaymentDetailSuccess",
                    value={
                        "data" : {
                            "id" : 3,
                            "status" : "paid",
                            "amount" : 6000,
                            "method" : "mock",
                            "paid_at" : "2026-04-20T10:05:00+09:00",
                            "order" : {
                                "id" : 10,
                                "status" : "paid",
                                "product" : {
                                    "id" : 1,
                                    "name" : "3시간권",
                                    "product_type" : "time",
                                    "price" : 6000,
                                },
                            },
                            "created_at" : "2026-04-20T10:05:00+09:00",
                        },
                        "meta" : {},
                    },
                    response_only=True,
                )
            ],
        ),
        401 : UNAUTHORIZED_RESPONSE,
        404 : NOT_FOUND_RESPONSE,
    },
)
class PaymentRetrieveAPIView(APIView):
    """
    GET /payments/{id}
    - 소유권 : payment.order.user == request.user
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, payment_id:int):
        payment = get_object_or_404(
            Payment.objects.select_related("order","order__product"),
            id=payment_id,
            order__user=request.user
        )
        data = PaymentReadSerializer(payment).data
        return ok(data)


@extend_schema(
    tags=["Orders/Payments/Passes"],
    summary="패스 목록 조회",
    parameters=[
        OpenApiParameter("status", str, OpenApiParameter.QUERY, enum=["active", "expired", "canceled"], required=False),
        OpenApiParameter("pass_kind", str, OpenApiParameter.QUERY, enum=["time", "flat", "fixed", "locker"], required=False),
    ],
    responses={
        200 : OpenApiResponse(
            description="패스 목록 조회 성공",
            examples=[
                OpenApiExample(
                    "PassListSuccess",
                    value={
                        "data" : [
                            {
                                "id" : 1,
                                "pass_kind" : "time",
                                "status" : "active",
                                "start_at" : "2026-04-20T10:05:00+09:00",
                                "end_at" : None,
                                "remaining_minutes" : 180,
                                "fixed_seat_id" : None,
                                "locker_id" : None,
                                "product" : {
                                    "id" : 1,
                                    "name" : "3시간권",
                                    "product_type" : "time",
                                    "price" : 6000,
                                },
                                "created_at" : "2026-04-20T10:05:00+09:00",
                            }
                        ],
                        "meta" : {
                            "count" : 1
                        },
                    },
                    response_only=True,
                )
            ],
        ),
        401 : UNAUTHORIZED_RESPONSE,
    },
)
class PassAPIView(APIView):
    """
    get /passes
    - 사용자 보유 이용권 목록
    - status 필터로 active/expired/canceled 조회 가능
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Pass.objects
            .select_related('product')
            .filter(user=request.user)
            .order_by("-created_at","-id")
        )

        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        pass_kind = request.query_params.get("pass_kind")
        if pass_kind:
            qs = qs.filter(pass_kind=pass_kind)

        data = PassReadSerializer(qs, many=True).data
        return ok(data, meta={"count":len(data)})


@extend_schema(
    tags=["Orders/Payments/Passes"],
    summary="패스 상세 조회",
    responses={
        200 : OpenApiResponse(
            description="패스 상세 조회 성공",
            examples=[
                OpenApiExample(
                    "PassDetailSuccess",
                    value={
                        "data" : {
                            "id" : 1,
                            "pass_kind" : "time",
                            "status" : "active",
                            "start_at" : "2026-04-20T10:05:00+09:00",
                            "end_at" : None,
                            "remaining_minutes" : 180,
                            "fixed_seat_id" : None,
                            "locker_id" : None,
                            "product" : {
                                "id" : 1,
                                "name" : "3시간권",
                                "product_type" : "time",
                                "price" : 6000,
                            },
                            "created_at" : "2026-04-20T10:05:00+09:00",
                        },
                        "meta" : {},
                    },
                    response_only=True,
                )
            ],
        ),
        401 : UNAUTHORIZED_RESPONSE,
        404 : NOT_FOUND_RESPONSE,
    },
)
class PassRetrieveAPIView(APIView):
    """
    GET /passes/{id}
    - 소유권 : pass.user == request.user
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pass_id:int):
        p = get_object_or_404(
            Pass.objects.select_related("product"),
            id=pass_id,
            user=request.user,
        )
        data = PassReadSerializer(p).data
        return ok(data)


class OrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="orders_list",
        tags=["Orders/Payments/Passes"],
        summary="주문 목록 조회",
        responses={
            200 : OpenApiResponse(
                description="주문 목록 조회 성공",
                examples=[
                    OpenApiExample(
                        "OrderListSuccess",
                        value={
                            "data" : [
                                {
                                    "id" : 10,
                                    "order_no" : "ORD-1234567890ABCDEFGH",
                                    "status" : "paid",
                                    "product" : {
                                        "id" : 1,
                                        "name" : "3시간권",
                                        "product_type" : "time",
                                        "price" : 6000,
                                    },
                                    "selected_seat_id" : None,
                                    "selected_locker_id" : None,
                                    "created_at" : "2026-04-20T10:00:00+09:00",
                                }
                            ],
                            "meta" : {
                                "count" : 1
                            },
                        },
                        response_only=True,
                    )
                ],
            ),
            401 : UNAUTHORIZED_RESPONSE,
        },
    )
    
    def get(self, request):
        qs = (
            Order.objects
            .select_related("product")
            .filter(user=request.user)
            .order_by("-created_at", "-id")
        )

        data = OrderReadSerializer(qs, many=True).data
        return ok(data, meta={"count" : len(data)})

    @extend_schema(
        tags=["Orders/Payments/Passes"],
        summary="주문 생성",
        request=OrderCreateSerializer,
        responses={
            201 : OpenApiResponse(
                description="주문 생성 성공",
                examples=[
                    OpenApiExample(
                        "OrderCreateSuccess",
                        value={
                            "data" : {
                                "order_id" : 10,
                                "order_status" : "created",
                            },
                            "meta" : {},
                        },
                        response_only=True,
                    )
                ],
            ),
            400 : VALIDATION_ERROR_RESPONSE,
            401 : UNAUTHORIZED_RESPONSE,
        },
    )
    def post(self, request) :
        s = OrderCreateSerializer(data=request.data, context={"request" : request})
        s.is_valid(raise_exception=True)

        order =create_order(
            user=request.user,
            product_id=s.validated_data["product_id"],
            seat_id=s.validated_data.get("seat_id"),
            locker_id=s.validated_data.get("locker_id"),
        )

        return ok(
            {"order_id" : order.id, "order_status" : order.status},
            status_code=201,
        )


class PaymentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Orders/Payments/Passes"],
        summary="결제 목록 조회",
        responses={
            200 : OpenApiResponse(
                description="결제 목록 조회 성공",
                examples=[
                    OpenApiExample(
                        "PaymentListSuccess",
                        value={
                            "data" : [
                                {
                                    "id" : 3,
                                    "status" : "paid",
                                    "amount" : 6000,
                                    "method" : "mock",
                                    "paid_at" : "2026-04-20T10:05:00+09:00",
                                    "order" : {
                                        "id" : 10,
                                        "status" : "paid",
                                        "product" : {
                                            "id" : 1,
                                            "name" : "3시간권",
                                            "product_type" : "time",
                                            "price" : 6000,
                                        },
                                    },
                                    "created_at" : "2026-04-20T10:05:00+09:00",
                                }
                            ],
                            "meta" : {
                                "count" : 1
                            },
                        },
                        response_only=True,
                    )
                ],
            ),
            401 : UNAUTHORIZED_RESPONSE,
        },
    )
    def get(self, request) :
        """
        GET /payments
        - Payment는 order와 1:1
        - 소유권은 payment.order.user 로 판단해야 함
        """
        qs = (
            Payment.objects
            .select_related("order", "order__product")
            .filter(order__user=request.user)
            .order_by("-created_at", "-id")
        )

        data = PaymentReadSerializer(qs, many=True).data
        return ok(data, meta={"count" : len(data)})

    @extend_schema(
        tags=["Orders/Payments/Passes"],
        summary="결제 생성",
        request=PaymentCreateSerializer,
        responses={
            201 : OpenApiResponse(
                description="결제 성공",
                examples=[
                    OpenApiExample(
                        "PaymentCreateSuccess",
                        value={
                            "data" : {
                                "payment_id" : 3,
                                "payment_status" : "paid",
                                "paid_at" : "2026-04-20T10:05:00+09:00",
                                "order" : {
                                    "id" : 10,
                                    "order_status" : "paid",
                                },
                                "pass" : {
                                    "id" : 1,
                                    "status" : "active",
                                    "pass_kind" : "time",
                                    "remaining_minutes" : 180,
                                    "end_at" : None,
                                    "fixed_seat_id" : None,
                                    "locker_id" : None,
                                },
                            },
                            "meta" : {},
                        },
                        response_only=True,
                    )
                ],
            ),
            400 : VALIDATION_ERROR_RESPONSE,
            401 : UNAUTHORIZED_RESPONSE,
        },
    )
    def post(self, request) :
        """
        결제 확정
        - 요청 검증은 serializer
        - 실제 로직은 service
        """
        s = PaymentCreateSerializer(data=request.data, context={"request" : request})
        s.is_valid(raise_exception=True)

        # order = (
        #     Order.objects
        #     .select_for_update()
        #     .select_related("product", "selected_seat", "selected_locker", "user")
        #     .get(id=s.validated_data["order"].id)
        # )
        #
        # if hasattr(order, "payment") :
        #     return ok({"message" : "이미 결제된 주문입니다."}, status_code=400)
        #
        # now = timezone.now()
        # product = order.product
        # pt = product.product_type
        #
        # payment = Payment.objects.create(
        #     order=order,
        #     amount=product.price,
        #     status=Payment.Status.PAID,
        #     method=s.validated_data.get("payment_method", "mock"),
        #     paid_at=now,
        # )
        #
        # order.status = Order.Status.PAID
        # order.save(update_fields=["status"])
        #
        # base_end = None
        #
        # if pt in ("fixed", "locker") :
        #     existing = (
        #         Pass.objects
        #         .select_for_update()
        #         .filter(user=order.user, pass_kind=pt, status=Pass.Status.ACTIVE)
        #         .first()
        #     )
        #
        #     if existing :
        #         base_end = existing.end_at if existing.end_at and existing.end_at > now else now
        #
        #         existing.status = Pass.Status.EXPIRED
        #         existing.save(update_fields=["status"])
        #
        #         if pt == "fixed" :
        #             SeatUsage.objects.select_for_update().filter(user=order.user).delete()
        #         else :
        #             LockerUsage.objects.select_for_update().filter(user=order.user).delete()
        #
        # pass_obj = Pass(
        #     user=order.user,
        #     product=product,
        #     order=order,
        #     pass_kind=pt,
        #     status=Pass.Status.ACTIVE,
        #     start_at=now,
        # )
        #
        # if pt == "time" :
        #     pass_obj.remaining_minutes = (product.duration_hours or 0) * 60
        # else :
        #     start_base = base_end if base_end else now
        #     pass_obj.end_at = start_base + timedelta(days=(product.duration_days or 0))
        #
        # if pt == "fixed" :
        #     pass_obj.fixed_seat = order.selected_seat
        # elif pt == "locker" :
        #     pass_obj.locker = order.selected_locker
        #
        # pass_obj.full_clean()
        # pass_obj.save()
        #
        # if pt == "fixed" :
        #     SeatUsage.objects.create(
        #         user=order.user,
        #         pass_obj=pass_obj,
        #         seat=order.selected_seat,
        #         check_in_at=now,
        #         expected_end_at=pass_obj.end_at,
        #     )
        #
        # elif pt == "locker" :
        #     LockerUsage.objects.create(
        #         user=order.user,
        #         pass_obj=pass_obj,
        #         locker=order.selected_locker,
        #         assign_at=now,
        #         unassign_at=pass_obj.end_at,
        #     )
        #
        # return ok(
        #     {
        #         "payment_id" : payment.id,
        #         "payment_status" : payment.status,
        #         "order" : {
        #             "id" : order.id,
        #             "status" : order.status,
        #         },
        #         "pass" : {
        #             "id" : pass_obj.id,
        #             "pass_kind" : pass_obj.pass_kind,
        #             "status" : pass_obj.status,
        #         },
        #     },
        #     status_code=201,
        # )
        payment, order, pass_obj = pay_order(
            user=request.user,
            order_id=s.validated_data["order"].id,
            payment_method=s.validated_data.get("payment_method", "mock")
        )

        return ok(
            {
                "payment_id": payment.id,
                "payment_status": payment.status,
                "paid_at": payment.paid_at,
                "order": {
                    "id": order.id,
                    "order_status": order.status,
                },
                "pass": {
                    "id": pass_obj.id,
                    "status": pass_obj.status,
                    "pass_kind": pass_obj.pass_kind,
                    "remaining_minutes": pass_obj.remaining_minutes,
                    "end_at": pass_obj.end_at,
                    "fixed_seat_id": pass_obj.fixed_seat_id,
                    "locker_id": pass_obj.locker_id,
                },
            },
            status_code=201,
        )

@extend_schema(
    tags=["Admin"],
    summary="관리자 환불 생성",
    request=AdminRefundCreateSerializer,
    responses={
        201: OpenApiResponse(
            description="관리자 환불 생성 성공",
            examples=[
                OpenApiExample(
                    "AdminRefundCreateSuccess",
                    value={
                        "data": {
                            "refund_id": 1,
                            "payment_id": 3,
                            "admin_user_id": 99,
                            "amount": 6000,
                            "reason": "고객 요청",
                            "refunded_at": "2026-04-20T11:00:00+09:00",
                        },
                        "meta": {},
                    },
                    response_only=True,
                )
            ],
        ),
        400: VALIDATION_ERROR_RESPONSE,
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
    },
)
class AdminRefundAPIView(AdminAPIView):
    """
    GET  /admin/refunds
    POST /admin/refunds
    - 관리자만 접근 가능
    - GET은 환불 목록, payment_id로 필터 가능
    - POST는 환불 생성(전체 환불)
    """

    def post(self, request):
        s = AdminRefundCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        refund = create_refund(
            admin_user=request.user,
            payment_id=s.validated_data["payment_id"],
            amount=s.validated_data.get("amount"),
            reason=s.validated_data.get("reason"),
        )

        return ok(
            {
                "refund_id": refund.id,
                "payment_id": refund.payment_id,
                "admin_user_id": refund.admin_user_id,
                "amount": refund.amount,
                "reason": refund.reason,
                "refunded_at": refund.refunded_at,
            },
            status_code=201,
        )


@extend_schema(
    tags=["Admin"],
    summary="관리자 환불 상세 조회",
    responses={
        200: OpenApiResponse(
            description="관리자 환불 상세 조회 성공",
            examples=[
                OpenApiExample(
                    "AdminRefundDetailSuccess",
                    value={
                        "data": {
                            "id": 1,
                            "payment": {
                                "id": 3,
                                "amount": 6000,
                            },
                            "admin_user": {
                                "id": 99,
                                "name": "관리자",
                            },
                            "amount": 6000,
                            "reason": "고객 요청",
                            "refunded_at": "2026-04-20T11:00:00+09:00",
                        },
                        "meta": {},
                    },
                    response_only=True,
                )
            ],
        ),
        401: UNAUTHORIZED_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
    },
)
class AdminRefundRetrieveAPIView(AdminAPIView):
    """
    GET /admin/refunds/{id}
    - 관리자만 접근 가능
    - 환불 상세 조회
    """

    def get(self, request, refund_id:int):
        refund = get_object_or_404(
            Refund.objects.select_related("payment","payment__order","admin_user"),
            id=refund_id,
        )
        return ok(AdminRefundReadSerializer(refund).data)