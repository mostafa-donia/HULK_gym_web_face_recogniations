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

    def test_dual_camera_profile_fields(self):
        self.assertEqual(self.profile.face_camera_index, 0)
        self.assertEqual(self.profile.face_camera_url, "")
        self.assertEqual(self.profile.enrollment_camera_mode, "same")
        self.assertEqual(self.profile.enrollment_camera_index, 1)

        self.profile.enrollment_camera_mode = "separate_index"
        self.profile.enrollment_camera_index = 2
        self.profile.face_camera_index = 1
        self.profile.face_camera_url = "rtsp://192.168.1.100:554/live"
        self.profile.save()

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.enrollment_camera_mode, "separate_index")
        self.assertEqual(self.profile.enrollment_camera_index, 2)
        self.assertEqual(self.profile.face_camera_index, 1)
        self.assertEqual(self.profile.face_camera_url, "rtsp://192.168.1.100:554/live")

    def test_api_test_camera_endpoint(self):
        self.client.force_login(self.admin)
        url = reverse("face_recognition:api_test_camera")
        # Testing non-existent or test source returns json with success flag and message
        res = self.client.get(f"{url}?source=999")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("success", data)
        self.assertIn("message", data)
        self.assertEqual(data["source"], "999")

    def test_api_capture_frame_enrollment_source(self):
        url = reverse("face_recognition:api_capture_frame")
        res = self.client.get(f"{url}?source=enrollment")
        # May be 200 (if camera available) or 503 (if headless/no camera), but valid JSON
        self.assertIn(res.status_code, [200, 503])
        data = res.json()
        self.assertIn("success", data)
        self.assertIn("message", data)

    def test_face_engine_camera_helpers(self):
        from apps.face_recognition.engine import get_face_engine
        engine = get_face_engine()
        self.assertTrue(hasattr(engine, "test_or_capture_source"))
        self.assertTrue(hasattr(engine, "capture_enrollment_frame"))
        self.assertTrue(hasattr(engine, "restart_camera"))

        # Test enrollment frame capture in "same" mode
        self.profile.enrollment_camera_mode = "same"
        self.profile.save()
        success, b64, msg = engine.capture_enrollment_frame()
        self.assertIsInstance(msg, str)
