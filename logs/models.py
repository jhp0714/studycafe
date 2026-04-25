from django.conf import settings
from django.db import models


User = settings.AUTH_USER_MODEL


class Log(models.Model):
    id = models.BigAutoField(primary_key=True)

    # 누가 실행했는지
    # 시스템/배치 로그도 남겨야 하므로 nullable 허용
    actor_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="acted_logs",
        null=True,
        blank=True,
    )

    # 누구에게 적용된 동작인지
    # 예: 관리자가 다른 사용자를 강제 퇴실시키는 경우 필요
    target_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="targeted_logs",
        null=True,
        blank=True,
    )

    # 어떤 동작인지
    # 예: seat_checked_in, payment_paid, refund_completed
    action = models.CharField(max_length=50)

    # 어떤 종류의 엔티티인지
    # 예: seat_usage, payment, pass, refund, batch
    entity_type = models.CharField(max_length=50)

    # 대상 엔티티 PK
    # 시스템 로그처럼 특정 row가 없을 수도 있으므로 nullable 허용
    entity_id = models.BigIntegerField(null=True, blank=True)

    # 관리자 사유나 간단 요약
    message = models.CharField(max_length=255, null=True, blank=True)

    # 부가 정보
    # 예: {"from_seat_id": 1, "to_seat_id": 3}
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "logs"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id", "created_at"]),
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["actor_user", "created_at"]),
            models.Index(fields=["target_user", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.action}] {self.entity_type}:{self.entity_id}"