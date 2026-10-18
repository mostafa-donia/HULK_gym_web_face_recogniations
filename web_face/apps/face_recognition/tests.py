import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User, UserRole
from apps.core.models import GymProfile
from apps.members.models import Member, MemberStatus, CheckInEvent


class FaceRecognitionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username="admin",
            password="password123",
            role=UserRole.MANAGER,
        )
        self.profile = GymProfile.get_solo()
        self.profile.gym_name = "Face Test Gym"
        self.profile.face_match_threshold = 65.0
        self.profile.save()

        self.member = Member.objects.create(
            member_id="M100",
            name="أحمد علي",
            mobile="01012345678",
            gender="male",
            current_status=MemberStatus.ACTIVE,
            last_subscription_end=timezone.now().date() + timezone.timedelta(days=20),
            current_paid=Decimal("500.00"),
            current_remaining=Decimal("0.00"),
        )

    def test_kiosk_page_accessible(self):
        res = self.client.get(reverse("face_recognition:kiosk"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "بوابة التعرف بالوجه")

    def test_kiosk_recent_checkins_api(self):
        CheckInEvent.objects.create(
            member=self.member,
            method="face",
            confidence=0.92,
            status_snapshot="active",
            days_left_snapshot=20,
            debt_snapshot=Decimal("0.00"),
        )
        res = self.client.get(reverse("face_recognition:api_recent_checkins"))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(data["events"][0]["member_id"], "M100")

    def test_delete_face_requires_login(self):
        url = reverse("face_recognition:api_delete_face", kwargs={"member_id": self.member.id})
        res = self.client.post(url)
        self.assertEqual(res.status_code, 302)

    def test_delete_face_as_manager(self):
        self.client.force_login(self.admin)
        self.member.has_face_enrolled = True
        self.member.face_embeddings = [[0.1] * 128]
        self.member.save()

        url = reverse("face_recognition:api_delete_face", kwargs={"member_id": self.member.id})
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])

        self.member.refresh_from_db()
        self.assertFalse(self.member.has_face_enrolled)
        self.assertEqual(len(self.member.face_embeddings), 0)
