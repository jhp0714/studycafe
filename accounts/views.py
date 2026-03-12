from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import SignUpSerializer, LoginSerializer, UserSerializer

class SignUpAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "data":{
                    "id":user.id,
                    "phone":user.phone,
                    "name":user.name,
                    "role":user.role,
                },
                "meta":{},
            },
            status=status.HTTP_201_CREATED,
        )


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request":request})
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "data":{
                    "acces_token":str(refresh.access_token),
                    "refresh_token":str(refresh),
                    "user":UserSerializer(user).data
                },
                "meta":{},
            },
            status=status.HTTP_200_OK,
        )


class RefreshAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh_token")
        if not refresh_token:
            return Response(
                {
                    "error":{
                        "code":"VALIDATION_ERROR",
                        "message":"refresh_token은 필수입니다.",
                        "details":{},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            return Response(
                {
                    "data":{
                        "access_token":access_token,
                    },
                    "meta":{},
                },
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {
                    "error":{
                        "code":"UNAUTHORIZED",
                        "message":"유효하지 않은 refresh_token 입니다.",
                        "details":{},
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )


class LogoutAPIView(APIView):
    def post(self, requeset):
        refresh_token = requeset.data.get("refresh_token")
        if not refresh_token:
            return Response(
                {
                    "error":{
                        "code":"VALIDATION_ERROR",
                        "message":"refresh_token은 필수입니다.",
                        "details":{},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(
                {
                    "data": {
                        "message": "로그아웃 되었습니다."
                    },
                    "meta": {},
                },
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "유효하지 않은 refresh_token 입니다.",
                        "details": {},
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )