from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import GymProfile, AuditLog
from apps.members.models import Member, Plan, Subscription
from apps.payments.models import (
    FinancialAccount,
    AccountType,
    Payment,
    PaymentOperationType,
    ReceptionCashHandover,
    HandoverStatus,
)
from apps.payments.services import (
    get_reception_drawer_summary,
    create_reception_handover,
    approve_reception_handover,
    reject_reception_handover,
    get_all_financial_accounts_summary,
)

User = get_user_model()


class ReceptionCashHandoverTests(TestCase):
    def setUp(self):
        self.profile = GymProfile.get_solo()
        self.profile.currency = "ج.م"
        self.profile.save()

        # Users
        self.manager = User.objects.create_user(
            username="manager_test",
            password="password123",
            role="MANAGER",
        )
        self.receptionist = User.objects.create_user(
            username="receptionist_test",
            password="password123",
            role="RECEPTION",
        )

        # Accounts
        self.cash_safe = FinancialAccount.objects.create(
            name="خزينة النقدية (الكاش)",
            account_type=AccountType.CASH,
            initial_balance=Decimal("1000.00"),
            is_default=True,
        )

        # Member & Payments
        self.member = Member.objects.create(
            member_id="MEM-9999",
            name="كابتن طارق البطل",
            mobile="01012345678",
            gender="male",
        )

        self.client = Client()

    def test_reception_drawer_summary_and_handover_cycle(self):
        # 1. Member pays 500 cash for subscription
        p1 = Payment.objects.create(
            payment_id="PAY-001",
            invoice_no="INV-001",
            operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
            member=self.member,
            amount=Decimal("500.00"),
            payment_method="نقدي",
            created_by=self.receptionist,
            account=self.cash_safe,
        )

        # 2. Check drawer summary: expected 500 in drawer
        summary = get_reception_drawer_summary()
        self.assertEqual(summary["total_cash_collected"], Decimal("500.00"))
        self.assertEqual(summary["current_drawer_balance"], Decimal("500.00"))

        # 3. Receptionist hands over 480 cash to manager (20 EGP shortage)
        handover = create_reception_handover(
            receptionist=self.receptionist,
            actual_amount=Decimal("480.00"),
            expected_amount=Decimal("500.00"),
            target_account=self.cash_safe,
            notes="تسليم وردية الصباح",
        )
        self.assertEqual(handover.status, HandoverStatus.PENDING)
        self.assertEqual(handover.difference, Decimal("-20.00"))
        self.assertTrue(handover.has_shortage)
        self.assertEqual(handover.shortage_amount, Decimal("20.00"))

        # 4. Check drawer while pending: pending is 480, drawer balance is 20
        summary_pending = get_reception_drawer_summary()
        self.assertEqual(summary_pending["total_handed_over_pending"], Decimal("480.00"))
        self.assertEqual(summary_pending["current_drawer_balance"], Decimal("20.00"))

        # 5. Check AuditLog entry created
        audit_entry = AuditLog.objects.filter(action="CASH_HANDOVER_SUBMITTED").first()
        self.assertIsNotNone(audit_entry)
        self.assertIn("عجز", audit_entry.details)

        # 6. Manager approves the handover
        approve_reception_handover(
            handover,
            manager=self.manager,
            manager_notes="تم العد ومطابقة المبلغ واستلام 480 ج.م",
        )
        handover.refresh_from_db()
        self.assertEqual(handover.status, HandoverStatus.APPROVED)
        self.assertEqual(handover.manager, self.manager)
        self.assertIsNotNone(handover.approved_at)

        # 7. Check AuditLog entry for approval
        approval_log = AuditLog.objects.filter(action="CASH_HANDOVER_APPROVED").first()
        self.assertIsNotNone(approval_log)
        self.assertIn("480", approval_log.details)

        # 8. Check drawer summary after approval: approved=480, shortages=20, drawer=20
        summary_approved = get_reception_drawer_summary()
        self.assertEqual(summary_approved["total_handed_over_approved"], Decimal("480.00"))
        self.assertEqual(summary_approved["total_shortages"], Decimal("20.00"))
        self.assertEqual(summary_approved["current_drawer_balance"], Decimal("20.00"))

    def test_handover_views_and_receipt(self):
        self.client.force_login(self.manager)

        # Payment
        Payment.objects.create(
            payment_id="PAY-002",
            invoice_no="INV-002",
            operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
            member=self.member,
            amount=Decimal("300.00"),
            payment_method="نقدي",
            created_by=self.receptionist,
            account=self.cash_safe,
        )

        # 1. Submit handover via POST
        resp_submit = self.client.post(
            reverse("payments:submit_reception_handover"),
            {
                "actual_amount": "300.00",
                "expected_amount": "300.00",
                "notes": "تسليم كاش كامل",
            },
        )
        self.assertEqual(resp_submit.status_code, 302)

        handover = ReceptionCashHandover.objects.filter(actual_amount=Decimal("300.00")).first()
        self.assertIsNotNone(handover)
        self.assertTrue(handover.is_matched)

        # 2. Test list view
        resp_list = self.client.get(reverse("payments:reception_handovers"))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, handover.handover_id)

        # 3. Test receipt view
        resp_receipt = self.client.get(
            reverse("payments:reception_handover_receipt", kwargs={"handover_id": handover.id})
        )
        self.assertEqual(resp_receipt.status_code, 200)
        self.assertContains(resp_receipt, "سند تسليم واستلام نقدية عهدة")
        self.assertContains(resp_receipt, handover.handover_id)

        # 4. Test API drawer balance
        resp_api = self.client.get(reverse("payments:api_drawer_balance"))
        self.assertEqual(resp_api.status_code, 200)
        json_data = resp_api.json()
        self.assertTrue(json_data["success"])
        self.assertIn("current_drawer_balance", json_data)
