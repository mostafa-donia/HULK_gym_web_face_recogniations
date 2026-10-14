from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch

from apps.accounts.models import User, UserRole
from apps.core.models import GymProfile
from apps.messaging.models import WhatsAppMessage, MessageStatus, MessageType
from apps.messaging.services import get_pending_summary, dispatch_all_pending


class WhatsAppRoutineAndPendingReminderTests(TestCase):
    def setUp(self):
        self.profile = GymProfile.objects.create(gym_name="HULK GYM")
        self.user = User.objects.create_user(
            username="assistant_user",
            password="password123",
            role=UserRole.ASSISTANT,
        )
        self.client = Client()
        self.client.login(username="assistant_user", password="password123")

        # Create routine test messages
        self.msg_receipt = WhatsAppMessage.objects.create(
            mobile="01011111111",
            recipient_name="عضو فاتورة",
            message="إيصال سداد رقم INV-001",
            msg_type=MessageType.RECEIPT,
            status=MessageStatus.PENDING,
            dedup_key="receipt_1",
        )
        self.msg_rem1 = WhatsAppMessage.objects.create(
            mobile="01022222222",
            recipient_name="عضو آخر يوم",
            message="تنبيه: متبقي يوم واحد على نهاية اشتراكك",
            msg_type=MessageType.REMINDER_1,
            status=MessageStatus.PENDING,
            dedup_key="rem1_1",
        )
        self.msg_rem3 = WhatsAppMessage.objects.create(
            mobile="01033333333",
            recipient_name="عضو 3 أيام",
            message="تنبيه: متبقي 3 أيام على نهاية اشتراكك",
            msg_type=MessageType.REMINDER_3,
            status=MessageStatus.PENDING,
            dedup_key="rem3_1",
        )
        self.msg_expired = WhatsAppMessage.objects.create(
            mobile="01044444444",
            recipient_name="عضو منتهي",
            message="تنبيه: اشتراكك انتهى، نتشرف بتجديدك",
            msg_type=MessageType.EXPIRED,
            status=MessageStatus.PENDING,
            dedup_key="exp_1",
        )
        self.msg_custom = WhatsAppMessage.objects.create(
            mobile="01055555555",
            recipient_name="عضو مخصص",
            message="رسالة عامة عروض خاصة",
            msg_type=MessageType.CUSTOM,
            status=MessageStatus.PENDING,
            dedup_key="custom_1",
        )

    def test_get_pending_summary(self):
        summary = get_pending_summary()
        self.assertEqual(summary["pending_count"], 5)
        self.assertTrue(summary["has_pending"])
        self.assertEqual(summary["breakdown"]["receipt"], 1)
        self.assertEqual(summary["breakdown"]["reminder_1"], 1)
        self.assertEqual(summary["breakdown"]["reminder_3"], 1)
        self.assertEqual(summary["breakdown"]["expired"], 1)
        self.assertEqual(summary["breakdown"]["other"], 1)

    def test_pending_summary_api(self):
        resp = self.client.get(reverse("messaging:whatsapp_pending_summary"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["pending_count"], 5)
        self.assertEqual(data["breakdown"]["reminder_1"], 1)
        self.assertEqual(data["breakdown"]["reminder_3"], 1)
        self.assertEqual(data["breakdown"]["expired"], 1)
        self.assertEqual(data["breakdown"]["receipt"], 1)

    def test_pending_messages_api_all_and_filtered(self):
        # 1. Fetch all
        resp_all = self.client.get(reverse("messaging:whatsapp_pending_messages"))
        self.assertEqual(resp_all.status_code, 200)
        data_all = resp_all.json()
        self.assertTrue(data_all["success"])
        self.assertEqual(data_all["count"], 5)

        # 2. Filter by reminder_1
        resp_rem1 = self.client.get(reverse("messaging:whatsapp_pending_messages") + "?msg_type=reminder_1")
        self.assertEqual(resp_rem1.status_code, 200)
        data_rem1 = resp_rem1.json()
        self.assertEqual(data_rem1["count"], 1)
        self.assertEqual(data_rem1["messages"][0]["msg_type"], "reminder_1")

        # 3. Filter by receipt
        resp_rec = self.client.get(reverse("messaging:whatsapp_pending_messages") + "?msg_type=receipt")
        self.assertEqual(resp_rec.status_code, 200)
        data_rec = resp_rec.json()
        self.assertEqual(data_rec["count"], 1)
        self.assertEqual(data_rec["messages"][0]["msg_type"], "receipt")

    @patch("apps.messaging.services.dispatch_message_record", return_value=True)
    def test_dispatch_batch_api_send_10(self, mock_dispatch):
        resp = self.client.post(
            reverse("messaging:whatsapp_dispatch_batch"),
            data={"limit": "10"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["processed"], 5)
        self.assertEqual(data["sent"], 5)

    @patch("apps.messaging.services.dispatch_message_record", return_value=True)
    def test_dispatch_batch_api_send_selected_only(self, mock_dispatch):
        # Only send reminder_1 and reminder_3
        selected = [str(self.msg_rem1.id), str(self.msg_rem3.id)]
        resp = self.client.post(
            reverse("messaging:whatsapp_dispatch_batch"),
            data={"selected_ids": selected, "limit": "2"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["processed"], 2)
        self.assertEqual(data["sent"], 2)

        self.msg_rem1.refresh_from_db()
        self.msg_rem3.refresh_from_db()
        self.msg_expired.refresh_from_db()

        # Check that expired is still pending (because it was not selected!)
        self.assertEqual(self.msg_expired.status, MessageStatus.PENDING)

    @patch("apps.messaging.services.dispatch_message_record", return_value=True)
    def test_batch_action_view_send_selected_pending(self, mock_dispatch):
        resp = self.client.post(
            reverse("messaging:whatsapp_batch_action"),
            data={"action": "send_selected_pending", "selected_ids": [str(self.msg_receipt.id)]},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "تمت معالجة إرسال 1 رسالة محددة")
