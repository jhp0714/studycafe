from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.conf import settings

import uuid

User = settings.AUTH_USER_MODEL

def generate_order_no():
    return f"ORD-{uuid.uuid4().hex[:20]}"
class Product(models.Model):
    class ProductType(models.TextChoices) :
        TIME = "time", "시간제"  # 일반석 시간제
        FLAT = "flat" , "기간제" # 일반석 기간제
        FIXED = "fixed", "지정석"  # 지정석 기간제
        LOCKER = "locker", "사물함"  # 사물함 기간제

    id = models.BigAutoField(primary_key=True)

    scode = models.CharField(max_length=20, help_text="1H, 7D....")
    name = models.CharField(max_length=100, help_text="상품명")
    product_type = models.CharField(max_length=10, choices=ProductType.choices, help_text="상품 타입")

    duration_hours = models.PositiveIntegerField(null=True, blank=True, help_text="시간제 전용")
    duration_days = models.PositiveIntegerField(null=True, blank=True, help_text="기간제 전용")

    price = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product_type", "scode"], name="unique_product_type_scode"),
            models.CheckConstraint(
                name="chk_product_duration_shape",
                check=(
                    (Q(product_type="time") & Q(duration_hours__isnull=False) & Q(duration_days__isnull=True))
                    | (Q(product_type__in=["flat", "fixed", "locker"]) & Q(duration_hours__isnull=True) & Q(duration_days__isnull=False))
                )
            )
        ]


class Order(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "주문 생성"
        PAID = "paid", "요금 지불"
        CANCELED = "canceled", "주문 취소"
        EXPIRED = "expired", "기한 만료"

    id = models.BigAutoField(primary_key = True)

    order_no = models.CharField(max_length=40, unique=True, default=generate_order_no, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="orders")
    pass_obj = models.ForeignKey(
        "cafe.Pass", null=True, blank=True, on_delete=models.PROTECT, related_name="orders",
    )
    selected_seat = models.ForeignKey(
        "cafe.Seat", null=True, blank=True, on_delete=models.PROTECT, related_name="orders_selected_seat"
    )
    selected_locker = models.ForeignKey(
        "cafe.Locker", null=True, blank=True, on_delete=models.PROTECT, related_name="orders_selected_locker"
    )

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta :
        indexes = [
            models.Index(fields=["user", "status", "created_at"], name="idx_order_user_status_created"),
        ]

    def clean(self) :
        super().clean()

        if not self.product_id :
            return

        pt = self.product.product_type

        if pt in (Product.ProductType.TIME, Product.ProductType.FLAT) :
            if self.selected_seat_id or self.selected_locker_id :
                raise ValidationError("시간권/기간권 상품은 좌석/사물함을 선택할 수 없습니다.")
            return

        if pt == Product.ProductType.FIXED :
            if self.selected_locker_id :
                raise ValidationError("지정석 상품에는 사물함을 선택할 수 없습니다.")
            # seat 필수 여부는 create_order() 서비스에서 판단
            return

        if pt == Product.ProductType.LOCKER :
            if self.selected_seat_id :
                raise ValidationError("사물함 상품에는 좌석을 선택할 수 없습니다.")
            # locker 필수 여부는 create_order() 서비스에서 판단
            return

        raise ValidationError("지원하지 않는 상품 유형입니다.")


class Payment(models.Model):
    class Status(models.TextChoices):
        READY = "ready", "결제 준비"
        PAID = "paid", "지불 완료"
        CANCELED = "canceled", "결제 취소"
        REFUNDED = "refunded", "환불"

    id = models.BigAutoField(primary_key=True)

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    amount = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.READY)
    method = models.CharField(max_length=20, default="mock")
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class Refund(models.Model):
    id = models.BigAutoField(primary_key=True)

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    admin_user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="refunds_admin")

    amount = models.PositiveIntegerField()
    reason = models.CharField(max_length=255, null=True, blank=True)

    refunded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)