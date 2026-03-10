from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.conf import settings

User = settings.AUTH_USER_MODEL

class Log(models.Model):
    id = models.BigAutoField(primary_key=True)

    actor_user_id = models.ForeignKey(User, on_delete=models.PROTECT, related_name="actor_user")
    entity_type = models.CharField(max_length=20, help_text="문제의 종류")
    action = models.CharField(max_length=20, help_text="조치 사항")
    entity_id = models.IntegerField(help_text="", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)