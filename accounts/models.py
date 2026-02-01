from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager

class UserManager(BaseUserManager):
    def create_user(self, phone:str, password:str|None = None, name:str=""):
        if not phone:
            raise ValueError("전화번호를 입력하지 않았습니다.")
        if not name:
            raise ValueError("이름을 입력하지 않았습니다.")

        user = self.model(phone=phone, name=name)

        # 비밀번호 부분은 조금 더 생각을 해보자
        if password:
            user.set_password(password)
        else:
            user.set_unsable_password()

        user.save(using=self._db)
        return user

class User(AbstractBaseUser, PermissionsMixin):
    id = models.BigAutoField(primary_key=True)

    phone = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50)

    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["name"]

    @property
    def role(self) -> str:
        return "ADMIN" if self.is_admin else "USER"

    def __str__(self) -> str:
        return f"{self.phone} ({self.role})"

