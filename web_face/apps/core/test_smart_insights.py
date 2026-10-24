import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User, UserRole
from apps.core.models import GymProfile
from apps.members.models import Member, Plan, Subscription
from apps.payments.models import Payment, PaymentMethod, PaymentOperationType
from apps.payments.services import queue_payment_receipt_whatsapp
from apps.messaging.models import WhatsAppMessage, MessageType
from apps.payroll.models import Employee, EmployeeRole, EmployeeStatus, PayrollRun, PayrollItem
from apps.payroll.services import get_default_salary_message


class SmartInsightsAndEnhancementsTests(TestCase):
    def setUp(self):
        self.profile = GymProfile.get_solo()
        self.profile.manager_password = "1234"
        self.profile.save()

        self.manager_user = User.objects.create_user(
            username="manager_test",
            password="password123",
            role=UserRole.MANAGER
        )
        self.client = Client()
        self.client.login(username="manager_test", password="password123")

    def test_new_member_welcome_message_and_invoice(self):
        """Verify new member welcome WhatsApp message is queued with member code and invoice."""
        member = Member.objects.create(
            member_id="MEM-TEST-99",
            name="أحمد طارق البطل",
            mobile="01011112222",
        )
        plan = Plan.objects.create(
            name="باقة القوة الشهرية",
            duration_days=30,
            price=Decimal("500.00"),
        )
        payment_method = PaymentMethod.objects.create(name="نقدي")
        sub = Subscription.objects.create(
            member=member,
            plan=plan,
            plan_name=plan.name,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timezone.timedelta(days=30),
            plan_price=Decimal("500.00"),
            net_amount=Decimal("500.00"),
            paid_amount=Decimal("500.00"),
            remaining_amount=Decimal("0.00"),
            payment_method=payment_method,
        )
        payment = Payment.objects.create(
            payment_id="PAY-WELCOME-01",
            invoice_no="INV-WELCOME-01",
            member=member,
            operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
            amount=Decimal("500.00"),
            payment_method=payment_method,
        )

        msg = queue_payment_receipt_whatsapp(payment, subscription=sub)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.msg_type, MessageType.WELCOME)
        self.assertIn(member.name, msg.message)
        self.assertIn(member.member_id, msg.message)
        self.assertTrue(bool(msg.attachment))

    def test_salary_preview_api_and_cheerful_message(self):
        """Verify salary preview API returns cheerful editable message and slip image path."""
        emp = Employee.objects.create(
            name="كابتن مروان",
            phone="01200001111",
            role=EmployeeRole.TRAINER,
            status=EmployeeStatus.ACTIVE,
            fixed_salary=Decimal("3000.00"),
        )
        run = PayrollRun.objects.create(
            period="2026-10",
            net_payable=Decimal("3500.00"),
        )
        item = PayrollItem.objects.create(
            payroll_run=run,
            employee=emp,
            employee_name_snapshot=emp.name,
            role_snapshot=emp.role,
            fixed_salary=Decimal("3000.00"),
            bonuses=Decimal("500.00"),
            net_payable=Decimal("3500.00"),
        )

        # Unlock manager session first
        session = self.client.session
        session["manager_page_unlocked"] = True
        session.save()

        resp = self.client.get(reverse("payroll:payroll_preview_salary_api", kwargs={"item_id": item.id}))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("employee_name"), emp.name)
        self.assertEqual(data.get("net_payable"), "3500.00")
        self.assertIn("كابتن مروان", data.get("message"))
        self.assertIn("3500.00", data.get("message"))
        self.assertTrue(bool(data.get("image_url")))

    def test_smart_insights_quick_advice_and_calc_structure(self):
        """Verify manager dashboard provides quick advice cards with mathematical formulas and numbers."""
        session = self.client.session
        session["manager_page_unlocked"] = True
        session["trainers_page_unlocked"] = True
        session.save()

        resp = self.client.get(reverse("core:manager_dashboard"))
        self.assertEqual(resp.status_code, 200)

        smart_insights = resp.context.get("smart_insights")
        self.assertIsNotNone(smart_insights)
        self.assertTrue(len(smart_insights) > 0)

        # Check telemetry fields on each insight
        for insight in smart_insights:
            self.assertIn("id", insight)
            self.assertIn("quick_advice", insight)
            self.assertIn("formula_title", insight)
            self.assertIn("formula_text", insight)
            self.assertIn("data_rows", insight)
            self.assertIn("calc_steps", insight)

        smart_insights_json = resp.context.get("smart_insights_json")
        self.assertIsNotNone(smart_insights_json)
        parsed_json = json.loads(smart_insights_json)
        self.assertEqual(len(parsed_json), len(smart_insights))

        # Check DOM elements
        self.assertContains(resp, "smartCalcDetailModal")
        self.assertContains(resp, "openSmartCalcModal")
        self.assertContains(resp, "كيف تم الاحتساب؟ (المعادلة والأرقام)")
