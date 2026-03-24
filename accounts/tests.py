from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

class AuthAPITest(APITestCase):
    def test_signup_success(self):
        response = self.client.post(
            "/api/auth/signup",
            {
                "phone":"01012345678",
                "name":"홍길동"
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("data",response.data)
        self.assertEqual(response.data["data"]["phone"],"01012345678")
        self.assertEqual(response.data["data"]["role"],"USER")

        user = User.objects.get(phone="01012345678")
        self.assertTrue(user.check_password("5678"))

    def test_login_success(self):
        User.objects.create_user(phone='01012345678', name="홍길동")

        response = self.client.post(
            "/api/auth/login",
            {
                "phone" : "01012345678",
                "password" : "5678",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.data["data"])
        self.assertIn("refresh_token", response.data["data"])
        self.assertEqual(response.data["data"]["user"]["role"], "USER")


    def test_login_fail_with_wrong_password(self):
        User.objects.create_user(phone="01012345678", name="홍길동")

        response = self.client.post(
            "/api/auth/login",
            {
                "phone": "01012345678",
                "password": "0000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")

    def test_refresh_success(self):
        user = User.objects.create_user(phone="01012345678", name="홍길동")

        login_response = self.client.post(
            "/api/auth/login",
            {
                "phone": "01012345678",
                "password": "5678",
            },
            format="json",
        )
        refresh_token = login_response.data["data"]["refresh_token"]

        response = self.client.post(
            "/api/auth/refresh",
            {
                "refresh_token": refresh_token,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.data["data"])

    def test_refresh_fail_with_invalid_token(self):
        response = self.client.post(
            "/api/auth/refresh",
            {
                "refresh_token": "invalid-token",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_me_requires_authentication(self):
        response = self.client.get("/api/me")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_me_success(self):
        user = User.objects.create_user(phone="01012345678", name="홍길동")

        login_response = self.client.post(
            "/api/auth/login",
            {
                "phone": "01012345678",
                "password": "5678",
            },
            format="json",
        )
        access_token = login_response.data["data"]["access_token"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get("/api/me")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["phone"], "01012345678")
        self.assertEqual(response.data["data"]["name"], "홍길동")


class AdminPermissionTest(APITestCase):
    def test_normal_user_cannot_access_admin_api(self):
        user = User.objects.create_user(phone="01011112222", name="일반유저")

        login_response = self.client.post(
            "/api/auth/login",
            {
                "phone": "01011112222",
                "password": "2222",
            },
            format="json",
        )
        access_token = login_response.data["data"]["access_token"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get("/api/admin/products/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_admin_user_can_access_admin_api(self):
        admin_user = User.objects.create_user(phone="01099998888", name="관리자")
        admin_user.is_admin = True
        admin_user.save()

        login_response = self.client.post(
            "/api/auth/login",
            {
                "phone": "01099998888",
                "password": "8888",
            },
            format="json",
        )
        access_token = login_response.data["data"]["access_token"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = self.client.get("/api/admin/products/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)