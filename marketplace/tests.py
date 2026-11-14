from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AdminDashboardAccessTests(TestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("admin_dashboard"))

        self.assertRedirects(response, f"/accounts/login/?next={reverse('admin_dashboard')}")

    def test_non_staff_user_cannot_open_dashboard(self):
        user = get_user_model().objects.create_user(username="client", password="test-pass-12345")
        self.client.force_login(user)

        response = self.client.get(reverse("admin_dashboard"))

        self.assertRedirects(response, f"/accounts/login/?next={reverse('admin_dashboard')}")

    def test_staff_user_sees_overview(self):
        staff_user = get_user_model().objects.create_superuser(
            username="operator",
            email="operator@example.test",
            password="test-pass-12345",
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin overview")
        self.assertContains(response, "Registered users")