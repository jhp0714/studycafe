from django.shortcuts import get_object_or_404
from django.db.models import Case, When, Value, IntegerField

from rest_framework.views import APIView
from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample, OpenApiParameter, OpenApiResponse

from common.swagger import UNAUTHORIZED_RESPONSE, FORBIDDEN_RESPONSE, VALIDATION_ERROR_RESPONSE, NOT_FOUND_RESPONSE

from accounts.permissions import AdminModelViewSet, AdminAPIView, IsAdminRole
from .models import Product, Order, Payment, Refund
from cafe.models import Pass
from .serializers import (
    ProductReadSerializer, AdminProductWriteSerializer,
    OrderCreateSerializer, PaymentCreateSerializer,
    OrderReadSerializer, PaymentReadSerializer, PassReadSerializer,
    AdminRefundReadSerializer, AdminRefundCreateSerializer
)
from .services.refunds import create_refund
from .services.payments import pay_order
from .services.orders import create_order
from .services.products import build_purchase_availability_context
from logs.services import LogAction, LogEntityType, write_log


def ok(data=None, meta=None, status_code=200):
    payload = {"data": data if data is not None else {}}
    if meta is not None:
        payload["meta"] = meta
    return Response(payload, status=status_code)



@extend_schema_view(
    list=extend_schema(
        tags=["Products"],
        summary="상품 목록 조회",
        parameters=[
            OpenApiParameter("product_type", str, OpenApiParameter.QUERY, enum=["time", "flat", "fixed", "locker"], required=False),
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
        },
    ),
)
class ProductViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    GET /products?is_active=true&product_type=time|flat|fixed|locker
    GET /products/{id}
    """
    permission_classes = [AllowAny]

    serializer_class = ProductReadSerializer

    def get_queryset(self):
        qs = (
            Product.objects
            .filter(is_active=True)
            .annotate(
                product_type_order=Case(
                    When(product_type="time", then=Value(1)),
                    When(product_type="flat", then=Value(2)),
                    When(product_type="fixed", then=Value(3)),
                    When(product_type="locker", then=Value(4)),
                    default=Value(99),
                    output_field=IntegerField(),
                )
            )
            .order_by(
                "product_type_order",
                "duration_hours",
                "duration_days",
                "price",
                "id",
            )
        )
        product_type = self.request.query_params.get("product_type")

        if product_type:
            qs = qs.filter(product_type=product_type)


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

    # def retrieve(self, request, *args, **kwargs) :
    #     instance = self.get_object()
    #
    #     context = {
    #         **self.get_serializer_context(),
    #         "product_purchase_context" : self._build_purchase_context(
    #             product_types={instance.product_type}
    #         ),
    #     }
    #
    #     serializer = self.get_serializer(instance, context=context)
    #     return ok(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=["Admin"],
        summary="관리자 상품 목록 조회",
        parameters=[
            OpenApiParameter(
                "product_id",
                int,
                OpenApiParameter.QUERY,
                required=False,
                description="상품 ID",
            ),
            OpenApiParameter(
                "product_type",
                str,
                OpenApiParameter.QUERY,
                enum=["time", "flat", "fixed", "locker"],
                required=False,
                description="상품 타입",
            ),
            OpenApiParameter(
                "is_active",
                bool,
                OpenApiParameter.QUERY,
                required=False,
                description="사용 가능 여부",
            ),
        ],
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
class AdminProductViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    POST    /admin/products
    PATCH   /admin/products/{id}
    GET     /admin/products
    """
    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = AdminProductWriteSerializer
    http_method_names = ["get","post","patch","head","options"]

    def get_queryset(self):
        qs = (
            Product.objects
            .all()
            .annotate(
                product_type_order = Case(
                    When(product_type="time",then=Value(1)),
                    When(product_type="flat", then=Value(2)),
                    When(product_type="fixed", then=Value(3)),
                    When(product_type="locker", then=Value(4)),
                    default=Value(99),
                    output_field=IntegerField(),
                )
            )
            .order_by(
                "product_type_order",
                "duration_hours",
                "price",
                "id",
            )
        )

        product_id = self.request.query_params.get("product_id")
        if product_id:
            qs = qs.filter(id=product_id)

        product_type = self.request.query_params.get("product_type")
        if product_type :
            qs = qs.filter(product_type=product_type)

        is_active = self.request.query_params.get("is_active")
        if is_active == "true" :
            qs = qs.filter(is_active=True)
        elif is_active == "false":
            qs = qs.filter(is_active=False)

        return qs

    def list(self, request, *args, **kwargs):
        res = super().list(request, *args, **kwargs)
        return ok(res.data)


    def create(self, request, *args, **kwargs):
        res = super().create(request, *args, **kwargs)
        product_id = res.data["id"]

        write_log(
            actor_user=request.user,
            action=LogAction.PRODUCT_CREATED,
            entity_type=LogEntityType.PRODUCT,
            entity_id=product_id,
            message="관리자 상품 생성",
            metadata={
                "after" : dict(res.data),
            },
        )

        return ok(res.data, status_code=201)


    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        before = {
            "scode" : instance.scode,
            "name":instance.name,
            "product_type":instance.product_type,
            "duration_hours":instance.duration_hours,
            "duration_days":instance.duration_days,
            "price":instance.price,
            "is_active":instance.is_active
        }

        res = super().partial_update(request, *args, **kwargs)

        write_log(
            actor_user=request.user,
            action=LogAction.PRODUCT_UPDATED,
            entity_type=LogEntityType.PRODUCT,
            entity_id=instance.id,
            message="관리자 상품 수정",
            metadata={
                "before" : before,
                "after" : dict(res.data),
            },
        )

        return ok(res.data)


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
                                "usage_summary": {
                                    "type": "time",
                                    "label": "일반석 시간제",
                                    "total_remaining_minutes": 180,
                                    "total_remaining_hours": 3,
                                    "total_remaining_minutes_remainder": 0,
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
                            "usage_summary": {
                                "type": "time",
                                "label": "일반석 시간제",
                                "total_remaining_minutes": 180,
                                "total_remaining_hours": 3,
                                "total_remaining_minutes_remainder": 0,
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



        payment, order, pass_obj = pay_order(
            user=request.user,
            order_id=s.validated_data["order"].id,
            payment_method=s.validated_data.get("payment_method", "mock")
        )

        pass_data = PassReadSerializer(pass_obj).data

        return ok(
            {
                "payment_id": payment.id,
                "payment_status": payment.status,
                "paid_at": payment.paid_at,
                "order": {
                    "id": order.id,
                    "order_status": order.status,
                },
                "pass": pass_data,
            },
            status_code=201,
        )


class AdminRefundAPIView(AdminAPIView):
    """
    GET  /admin/refunds
    POST /admin/refunds
    - 관리자만 접근 가능
    - GET은 환불 목록, payment_id로 필터 가능
    - POST는 환불 생성(전체 환불)
    """

    @extend_schema(
        tags=["Admin"],
        summary="관리자 환불 목록 조회",
        parameters=[
            OpenApiParameter(
                "payment_id",
                int,
                OpenApiParameter.QUERY,
                required=False,
                description="결제 ID",
            ),
            OpenApiParameter(
                "user_id",
                int,
                OpenApiParameter.QUERY,
                required=False,
                description="환불 대상 사용자 ID",
            ),
        ],
        responses={
            200 : OpenApiResponse(
                description="관리자 환불 목록 조회 성공",
                examples=[
                    OpenApiExample(
                        "AdminRefundListSuccess",
                        value={
                            "data" : [
                                {
                                    "id" : 1,
                                    "amount" : 6000,
                                    "reason" : "고객 요청",
                                    "refunded_at" : "2026-04-20T11:00:00+09:00",
                                    "payment" : {
                                        "id" : 3,
                                        "amount" : 6000,
                                        "status" : "refunded",
                                        "method" : "mock",
                                    },
                                    "order" : {
                                        "id" : 10,
                                        "order_no" : "ORD-1234567890",
                                        "status" : "paid",
                                    },
                                    "user" : {
                                        "id" : 2,
                                        "phone" : "01011112222",
                                        "name" : "테스트유저",
                                    },
                                    "admin" : {
                                        "id" : 1,
                                        "phone" : "01099998888",
                                        "name" : "관리자",
                                    },
                                }
                            ],
                            "meta" : {"count" : 1},
                        },
                        response_only=True,
                    )
                ],
            ),
            401 : UNAUTHORIZED_RESPONSE,
            403 : FORBIDDEN_RESPONSE,
        },
    )
    def get(self, request):
        qs = (
            Refund.objects
            .select_related(
                "payment",
                "payment__order",
                "payment__order__user",
                "payment__order__product",
                "admin_user",
            )
            .order_by("-refunded_at","id")
        )

        payment_id = request.query_params.get("payment_id")
        if payment_id:
            qs = qs.filter(payment_id=payment_id)

        user_id = request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(payment__order__user_id=user_id)

        data = AdminRefundReadSerializer(qs, many=True).data
        return ok(data, meta={"count":len(data)})

    @extend_schema(
        tags=["Admin"],
        summary="관리자 환불 생성",
        request=AdminRefundCreateSerializer,
        responses={
            201 : OpenApiResponse(
                description="관리자 환불 생성 성공",
                examples=[
                    OpenApiExample(
                        "AdminRefundCreateSuccess",
                        value={
                            "data" : {
                                "refund_id" : 1,
                                "payment_id" : 3,
                                "admin_user_id" : 99,
                                "amount" : 6000,
                                "reason" : "고객 요청",
                                "refunded_at" : "2026-04-20T11:00:00+09:00",
                            },
                            "meta" : {},
                        },
                        response_only=True,
                    )
                ],
            ),
            400 : VALIDATION_ERROR_RESPONSE,
            401 : UNAUTHORIZED_RESPONSE,
            403 : FORBIDDEN_RESPONSE,
        },
    )
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
            Refund.objects.select_related(
                "payment",
                "payment__order",
                "payment__order__user",
                "payment__order__product",
                "admin_user"
            ),
            id=refund_id,
        )
        return ok(AdminRefundReadSerializer(refund).data)