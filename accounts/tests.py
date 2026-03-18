from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

class AuthAPITest(APITestCase):
    def test_signup_success(self):
        response = self.client.post(
            "api/auth/signup",
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