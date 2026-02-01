from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from .models import Product
from .serializers import ProductReadSerializer, AdminProductWriteSerializer

def ok(data=None, meta=None, status_code=200):
    payload = {"data":data if data is not None else {}}
    if meta is not None:
        payload["meta"] = meta
    return Response(payload, status=status_code)


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