from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AccountProfile, ActivityTag, Availability, Block, Booking, CompanionProfile, Report


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


class RegistrationRoleTests(TestCase):
    def test_companion_signup_persists_role_and_starts_onboarding(self):
        response = self.client.post(reverse("signup"), {
            "username": "companion-user",
            "email": "companion@example.test",
            "role": AccountProfile.Role.COMPANION,
            "password1": "Distinct-Strong-Passphrase-984!",
            "password2": "Distinct-Strong-Passphrase-984!",
        })

        self.assertRedirects(response, reverse("companion_apply"))
        account = AccountProfile.objects.get(user__username="companion-user")
        self.assertEqual(account.role, AccountProfile.Role.COMPANION)

    def test_client_signup_persists_client_role(self):
        response = self.client.post(reverse("signup"), {
            "username": "client-user",
            "email": "client@example.test",
            "role": AccountProfile.Role.CLIENT,
            "password1": "Distinct-Strong-Passphrase-984!",
            "password2": "Distinct-Strong-Passphrase-984!",
        })

        self.assertRedirects(response, reverse("home"))
        account = AccountProfile.objects.get(user__username="client-user")
        self.assertEqual(account.role, AccountProfile.Role.CLIENT)


class RoleDashboardTests(TestCase):
    def create_account(self, username, role):
        user = get_user_model().objects.create_user(
            username=username,
            password="Distinct-Strong-Passphrase-984!",
        )
        AccountProfile.objects.create(user=user, role=role)
        self.client.force_login(user)
        return user

    def test_client_dashboard_router_and_view(self):
        self.create_account("client-dashboard-user", AccountProfile.Role.CLIENT)

        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("client_dashboard"))

        response = self.client.get(reverse("client_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upcoming plans")

    def test_companion_dashboard_router_and_view(self):
        self.create_account("companion-dashboard-user", AccountProfile.Role.COMPANION)

        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("companion_dashboard"))

        response = self.client.get(reverse("companion_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create your listing")

    def test_companion_cannot_open_client_dashboard(self):
        self.create_account("companion-client-route", AccountProfile.Role.COMPANION)

        response = self.client.get(reverse("client_dashboard"))

        self.assertRedirects(response, reverse("companion_dashboard"))


class BookingValidationTests(TestCase):
    def setUp(self):
        companion_user = get_user_model().objects.create_user(username="booking-companion")
        self.profile = CompanionProfile.objects.create(
            user=companion_user,
            display_name="A Companion",
            date_of_birth=date(1990, 1, 1),
            gender=CompanionProfile.Gender.PREFER_NOT_TO_SAY,
            city="Mumbai",
            bio="Enjoys museums and coffee.",
            hourly_rate=500,
            min_hours=1,
            languages="English, Hindi",
            status=CompanionProfile.Status.APPROVED,
        )
        self.activity = ActivityTag.objects.create(name="Coffee", slug="coffee")
        self.profile.activities.add(self.activity)
        self.booking_date = timezone.localdate() + timedelta(days=1)
        Availability.objects.create(
            profile=self.profile,
            weekday=self.booking_date.weekday(),
            start_time=time(9),
            end_time=time(17),
        )
        self.client_user = get_user_model().objects.create_user(username="booking-client")

    def make_booking(self, start_time, hours=1, status=Booking.Status.REQUESTED):
        return Booking(
            client=self.client_user,
            companion=self.profile,
            activity=self.activity,
            date=self.booking_date,
            start_time=start_time,
            hours=hours,
            location="Central Cafe",
            status=status,
        )

    def test_booking_must_fit_configured_availability(self):
        booking = self.make_booking(time(16), hours=2)

        with self.assertRaises(ValidationError) as error:
            booking.full_clean()

        self.assertIn("outside the companion's available hours", str(error.exception))

    def test_request_cannot_overlap_accepted_booking(self):
        self.make_booking(time(10), hours=2, status=Booking.Status.ACCEPTED).save()
        booking = self.make_booking(time(11), hours=1)

        with self.assertRaises(ValidationError) as error:
            booking.full_clean()

        self.assertIn("already has an accepted booking", str(error.exception))

    def test_booking_within_availability_is_valid(self):
        booking = self.make_booking(time(13), hours=2)

        booking.full_clean()

    def test_booking_requires_availability_for_selected_day(self):
        self.profile.availability.all().delete()
        booking = self.make_booking(time(13), hours=2)

        with self.assertRaises(ValidationError) as error:
            booking.full_clean()

        self.assertIn("has not set availability", str(error.exception))


class SafetyActionTests(TestCase):
    def setUp(self):
        companion_user = get_user_model().objects.create_user(username="reported-companion")
        self.profile = CompanionProfile.objects.create(
            user=companion_user,
            display_name="Safety Test Companion",
            date_of_birth=date(1990, 1, 1),
            gender=CompanionProfile.Gender.PREFER_NOT_TO_SAY,
            city="Mumbai",
            bio="Enjoys museums and coffee.",
            hourly_rate=500,
            min_hours=1,
            languages="English, Hindi",
            status=CompanionProfile.Status.APPROVED,
        )
        self.user = get_user_model().objects.create_user(username="safety-client")
        AccountProfile.objects.create(user=self.user, role=AccountProfile.Role.CLIENT)
        self.client.force_login(self.user)

    def test_profile_report_is_created_for_staff_review(self):
        response = self.client.post(reverse("report_profile", args=[self.profile.slug]), {
            "reason": "This profile appears to violate the community guidelines.",
        })

        self.assertRedirects(response, reverse("profile_detail", args=[self.profile.slug]))
        report = Report.objects.get(reporter=self.user, target_user=self.profile.user)
        self.assertEqual(report.status, Report.Status.OPEN)

    def test_blocked_profile_is_hidden_from_discovery(self):
        self.client.post(reverse("block_profile", args=[self.profile.slug]))

        response = self.client.get(reverse("home"))

        self.assertTrue(Block.objects.filter(blocker=self.user, target=self.profile.user).exists())
        self.assertNotContains(response, "Safety Test Companion")

    def test_user_can_unblock_only_their_own_block(self):
        block = Block.objects.create(blocker=self.user, target=self.profile.user)

        response = self.client.post(reverse("unblock_user", args=[block.pk]))

        self.assertRedirects(response, reverse("blocked_users"))
        self.assertFalse(Block.objects.filter(pk=block.pk).exists())