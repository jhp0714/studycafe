from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.conf import settings

User = settings.AUTH_USER_MODEL

class Seat(models.Model):
    class SeatType(models.TextChoices):
        NORMAL = "normal", "일반석"
        FIXED = "fixed", "지정석"


    id = models.BigAutoField(primary_key=True)

    seat_no = models.CharField(max_length=20, unique=True)
    seat_type = models.CharField(max_length=10, choices=SeatType.choices)
    available = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class Locker(models.Model):

    id = models.BigAutoField(primary_key=True)

    locker_no = models.CharField(max_length=20, unique=True)
    available = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class Pass(models.Model):
    class PassKind(models.TextChoices):
        TIME = "time", "시간제"
        FLAT = "flat", "기간제"
        FIXED = "fixed", "지정석"
        LOCKER = "locker", "사물함"

    class Status(models.TextChoices):
        ACTIVE = "active", "사용 가능한"
        EXPIRED = "expired", "만료된"
        CANCELED = "canceled", "취소된"

    id = models.BigAutoField(primary_key=True)

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="passes")
    product = models.ForeignKey("payments.Product", on_delete=models.PROTECT, related_name="passes")
    order = models.OneToOneField("payments.Order", on_delete=models.PROTECT, related_name="pass_obj")

    pass_kind = models.CharField(max_length=10, choices=PassKind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    start_at = models.DateTimeField(null=True, blank=True, help_text="결제 후 생성")
    end_at = models.DateTimeField(null=True, blank=True, help_text="기간제 상품 끝나는 시점")
    remaining_minutes = models.PositiveIntegerField(null=True, blank=True, help_text="시간제 상품 남은 시간 분으로 관리")

    fixed_seat = models.ForeignKey(Seat, null=True, blank=True, on_delete=models.PROTECT, related_name="fixed_passes",
                                   help_text="사용자가 지정한 지정석 번호")
    locker = models.ForeignKey(Locker, null=True, blank=True, on_delete=models.PROTECT, related_name="locker_passes",
                               help_text="사용자가 지정한 사물함 번호")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="chk_pass_resource_shape",
                check=(
                        (Q(pass_kind="fixed") & Q(fixed_seat__isnull=False) & Q(locker__isnull=True))
                        | (Q(pass_kind="locker") & Q(locker__isnull=False) & Q(fixed_seat__isnull=True))
                        | (Q(pass_kind__in=["time", "flat"]) & Q(fixed_seat__isnull=True) & Q(locker__isnull=True))
                )
            ),

            # 지정석/사물함은 결제 기간 동안 항상 점유 유지 -> active 종복 방지
            models.UniqueConstraint(
                fields=["fixed_seat"],
                condition=Q(status="active"),
                name="uniq_active_fixed_seat_pass"
            ),
            models.UniqueConstraint(
                fields=["locker"],
                condition=Q(status="active"),
                name="uniq_active_locker_pass"
            )
        ]

    def clean(self):
        # pass_kind는 product_type과 일치
        if self.product_id and self.pass_kind and self.product.product_type != self.pass_kind:
            raise ValidationError({"pass_kind":"pass_kind와 product.product_type이 맞이 않습니다."})

        # 시간제만 remainging_minutes 사용
        if self.pass_kind != "time" and self.remaining_minutes is not None:
            raise ValidationError({"remaining_minutes":"시간제만 remaining_minutes를 가질 수 있습니다."})

        # 기간제만 end_at 사용
        if self.pass_kind == "time" and self.end_at is not None :
            raise ValidationError({"end_at" : "시간제는 end_at을 사용할 수 없습니다."})


class SeatUsage(models.Model):

    id = models.BigAutoField(primary_key=True)

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="seat_usage")
    pass_obj = models.ForeignKey(Pass, on_delete=models.PROTECT, related_name="seat_usage")
    seat = models.ForeignKey(Seat, on_delete=models.PROTECT, related_name="Usages")

    check_in_at = models.DateTimeField()
    expected_end_at = models.DateTimeField(help_text="자동 퇴실 시간")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            # 좌석 1개엔 1명만
            models.UniqueConstraint(
                fields=["seat"],
                name="uniq_active_seat_usage_per_seat"
            ),
            # 유저는 1개의 좌석만
            models.UniqueConstraint(
                fields=["user"],
                name="uniq_active_seat_usage_per_user"
            )
        ]


class LockerUsage(models.Model):

    id = models.BigAutoField(primary_key=True)

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="locker_usages")
    pass_obj = models.ForeignKey(Pass, on_delete=models.PROTECT, related_name="locker_usages")
    locker = models.ForeignKey(Locker, on_delete=models.PROTECT, related_name="usages")

    assign_at = models.DateTimeField()
    unassign_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta :
        constraints = [
            # 1개의 락커엔 1명만
            models.UniqueConstraint(
                fields=["locker"],
                name="uniq_active_locker_usage_per_locker",
            ),
            # 유저는 1개의 락커만
            models.UniqueConstraint(
                fields=["user"],
                name="uniq_active_locker_usage_per_user",
            ),
        ]