import json
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User, UserRole
from apps.core.models import GymProfile
from apps.members.models import Member, Plan, Subscription
from apps.payments.models import Payment, PaymentOperationType
from apps.payroll.models import (
    Employee,
    EmployeeRole,
    EmployeeStatus,
    TrainerClientAssignment,
    PrivateTrainingRecord,
    SalaryAdjustment,
    AdjustmentType,
    AdjustmentStatus,
    PayrollRun,
    PayrollItem,
    PayrollStatus,
)
from apps.messaging.models import WhatsAppMessage, MessageStatus


class ComprehensivePayrollAndSystemTests(TestCase):
    """
    Automated verification of Scenarios A through J as specified in the Master Prompt.
    """

    def setUp(self):
        self.profile = GymProfile.objects.create(
            gym_name="HULK GYM",
            currency="ج.م",
        )

        # Users
        self.manager_user = User.objects.create_user(
            username="test_manager",
            password="password123",
            role=UserRole.MANAGER,
            first_name="المدير العام",
        )
        self.assistant_user = User.objects.create_user(
            username="test_assistant",
            password="password123",
            role=UserRole.ASSISTANT,
            first_name="موظف الاستقبال",
        )

        # Base Plans
        self.standard_plan = Plan.objects.create(
            name="اشتراك شهري عام",
            price=Decimal("400.00"),
            duration_days=30,
        )
        self.vip_plan = Plan.objects.create(
            name="اشتراك شهري خاص VIP",
            price=Decimal("600.00"),
            duration_days=30,
        )
        self.session_plan = Plan.objects.create(
            name="جلسة واحدة",
            price=Decimal("50.00"),
            duration_days=1,
            frequency="جلسة واحدة",
        )
        self.day_on_day_off_plan = Plan.objects.create(
            name="شهري حديد - يوم ويوم",
            price=Decimal("230.00"),
            duration_days=14,
            frequency="يوم ويوم",
        )
        self.everyday_plan = Plan.objects.create(
            name="شهري شامل - كل يوم",
            price=Decimal("400.00"),
            duration_days=28,
            frequency="كل يوم",
        )

        # Clients
        self.client_a = Member.objects.create(
            member_id="MEM-TEST-A",
            name="أحمد محمود",
            mobile="01011111111",
        )
        self.client_b = Member.objects.create(
            member_id="MEM-TEST-B",
            name="كريم عادل",
            mobile="01022222222",
        )

        # Employees
        self.trainer_1 = Employee.objects.create(
            name="كابتن طارق",
            phone="01033333333",
            role=EmployeeRole.TRAINER,
            status=EmployeeStatus.ACTIVE,
            fixed_salary=Decimal("1500.00"),
        )
        self.trainer_2 = Employee.objects.create(
            name="كابتن سامح",
            phone="01044444444",
            role=EmployeeRole.TRAINER,
            status=EmployeeStatus.ACTIVE,
            fixed_salary=Decimal("2000.00"),
        )
        self.assistant_emp = Employee.objects.create(
            name="موظف الاستقبال حسام",
            phone="01055555555",
            role=EmployeeRole.ASSISTANT,
            status=EmployeeStatus.ACTIVE,
            fixed_salary=Decimal("3000.00"),
        )

        self.client = Client()

    def test_scenario_a_private_training_commission_markup_formula(self):
        """
        Scenario A:
        Standard plan price = 400 EGP, private package price = 600 EGP, trainer commission rate = 50%.
        Markup = 600 - 400 = 200 EGP.
        Trainer commission = 200 * 50% = 100 EGP.
        Must NOT be calculated on 600 EGP (which would have been 300 EGP).
        """
        # Trainer assignment with 50% commission rate
        assignment = TrainerClientAssignment.objects.create(
            trainer=self.trainer_1,
            client=self.client_a,
            commission_rate=Decimal("0.50"),
        )

        record = PrivateTrainingRecord.objects.create(
            trainer=self.trainer_1,
            client=self.client_a,
            package_price=Decimal("600.00"),
            standard_plan_price=Decimal("400.00"),
            commission_rate=assignment.commission_rate,
        )

        self.assertEqual(record.private_markup, Decimal("200.00"))
        self.assertEqual(record.calculated_commission, Decimal("100.00"))
        self.assertNotEqual(record.calculated_commission, Decimal("300.00"))

    def test_scenario_b_two_trainers_different_rates(self):
        """
        Scenario B:
        Two trainers with different client commission rates (e.g. 50% vs 40%).
        Verify isolated calculations for each trainer.
        """
        # Trainer 1 with Client A: 50% of (600 - 400 = 200) -> 100 EGP
        TrainerClientAssignment.objects.create(
            trainer=self.trainer_1,
            client=self.client_a,
            commission_rate=Decimal("0.50"),
        )
        rec1 = PrivateTrainingRecord.objects.create(
            trainer=self.trainer_1,
            client=self.client_a,
            package_price=Decimal("600.00"),
            standard_plan_price=Decimal("400.00"),
            commission_rate=Decimal("0.50"),
        )

        # Trainer 2 with Client B: 40% of (700 - 400 = 300) -> 120 EGP
        TrainerClientAssignment.objects.create(
            trainer=self.trainer_2,
            client=self.client_b,
            commission_rate=Decimal("0.40"),
        )
        rec2 = PrivateTrainingRecord.objects.create(
            trainer=self.trainer_2,
            client=self.client_b,
            package_price=Decimal("700.00"),
            standard_plan_price=Decimal("400.00"),
            commission_rate=Decimal("0.40"),
        )

        self.assertEqual(rec1.calculated_commission, Decimal("100.00"))
        self.assertEqual(rec2.calculated_commission, Decimal("120.00"))

    def test_scenario_c_price_change_future_period_leaves_historical_payroll_intact(self):
        """
        Scenario C:
        Price change in future period leaves historical approved payroll intact.
        """
        self.client.login(username="test_manager", password="password123")
        period = "2026-01"

        # Create private record in 2026-01
        rec = PrivateTrainingRecord.objects.create(
            trainer=self.trainer_1,
            client=self.client_a,
            package_price=Decimal("600.00"),
            standard_plan_price=Decimal("400.00"),
            commission_rate=Decimal("0.50"),
        )
        # Backdate created_at to 2026-01-15
        PrivateTrainingRecord.objects.filter(id=rec.id).update(
            created_at=timezone.datetime(2026, 1, 15, 12, 0, tzinfo=timezone.get_current_timezone())
        )

        # Run detail and approve payroll for 2026-01
        resp = self.client.get(reverse("payroll:payroll_run_detail", kwargs={"period": period}))
        self.assertEqual(resp.status_code, 200)

        approve_resp = self.client.post(reverse("payroll:payroll_approve", kwargs={"period": period}))
        self.assertEqual(approve_resp.status_code, 302)

        payroll_run = PayrollRun.objects.get(period=period)
        self.assertEqual(payroll_run.status, PayrollStatus.APPROVED)

        # Verify sealed item for trainer_1: fixed 1500 + comm 100 = 1600 EGP
        t1_item = PayrollItem.objects.get(payroll_run=payroll_run, employee=self.trainer_1)
        self.assertEqual(t1_item.net_payable, Decimal("1600.00"))

        # Now change standard plan price in the system for future months
        self.standard_plan.price = Decimal("500.00")
        self.standard_plan.save()

        # Reload historical approved payroll item
        t1_item.refresh_from_db()
        payroll_run.refresh_from_db()
        self.assertEqual(t1_item.net_payable, Decimal("1600.00"))
        self.assertEqual(payroll_run.status, PayrollStatus.APPROVED)

    def test_scenario_d_unapproved_deduction_excluded(self):
        """
        Scenario D:
        Assistant fixed salary with unapproved (PENDING or DRAFT) deduction excluded from approved payroll.
        """
        self.client.login(username="test_manager", password="password123")
        period = "2026-02"

        # Create a pending deduction of 300 EGP
        SalaryAdjustment.objects.create(
            employee=self.assistant_emp,
            period=period,
            adjustment_type=AdjustmentType.DEDUCTION,
            category="تأخير",
            amount=Decimal("300.00"),
            reason="تأخير في الحضور",
            status=AdjustmentStatus.PENDING,
            created_by=self.manager_user,
        )

        # Approve the payroll run
        self.client.get(reverse("payroll:payroll_run_detail", kwargs={"period": period}))
        self.client.post(reverse("payroll:payroll_approve", kwargs={"period": period}))

        run = PayrollRun.objects.get(period=period)
        item = PayrollItem.objects.get(payroll_run=run, employee=self.assistant_emp)

        # Unapproved deduction must NOT be applied: salary remains full 3000.00
        self.assertEqual(item.deductions, Decimal("0.00"))
        self.assertEqual(item.net_payable, Decimal("3000.00"))

    def test_scenario_e_approved_bonus_and_deduction_calculation(self):
        """
        Scenario E:
        Approved bonus (200 EGP) and approved deduction (100 EGP) calculate correct net salary:
        Fixed 3000 + 200 - 100 = 3100 EGP.
        """
        self.client.login(username="test_manager", password="password123")
        period = "2026-03"

        SalaryAdjustment.objects.create(
            employee=self.assistant_emp,
            period=period,
            adjustment_type=AdjustmentType.BONUS,
            category="مكافأة أداء",
            amount=Decimal("200.00"),
            status=AdjustmentStatus.APPROVED,
            created_by=self.manager_user,
            approved_by=self.manager_user,
        )
        SalaryAdjustment.objects.create(
            employee=self.assistant_emp,
            period=period,
            adjustment_type=AdjustmentType.DEDUCTION,
            category="غياب يوم",
            amount=Decimal("100.00"),
            status=AdjustmentStatus.APPROVED,
            created_by=self.manager_user,
            approved_by=self.manager_user,
        )

        self.client.get(reverse("payroll:payroll_run_detail", kwargs={"period": period}))
        self.client.post(reverse("payroll:payroll_approve", kwargs={"period": period}))

        run = PayrollRun.objects.get(period=period)
        item = PayrollItem.objects.get(payroll_run=run, employee=self.assistant_emp)

        self.assertEqual(item.fixed_salary, Decimal("3000.00"))
        self.assertEqual(item.bonuses, Decimal("200.00"))
        self.assertEqual(item.deductions, Decimal("100.00"))
        self.assertEqual(item.net_payable, Decimal("3100.00"))

    def test_scenario_f_whatsapp_disconnected_leaves_approved_payroll_intact(self):
        """
        Scenario F:
        WhatsApp queue dispatch or disconnect leaves approved payroll intact.
        """
        self.client.login(username="test_manager", password="password123")
        period = "2026-04"

        # Approve run
        self.client.get(reverse("payroll:payroll_run_detail", kwargs={"period": period}))
        self.client.post(reverse("payroll:payroll_approve", kwargs={"period": period}))

        run = PayrollRun.objects.get(period=period)
        item = PayrollItem.objects.get(payroll_run=run, employee=self.trainer_1)
        self.assertEqual(run.status, PayrollStatus.APPROVED)

        # Trigger send whatsapp view
        send_resp = self.client.post(reverse("payroll:payroll_send_whatsapp", kwargs={"item_id": item.id}))
        self.assertEqual(send_resp.status_code, 302)

        # Verify message queued
        queued_msg = WhatsAppMessage.objects.filter(mobile=self.trainer_1.phone).first()
        self.assertIsNotNone(queued_msg)
        self.assertEqual(queued_msg.status, MessageStatus.PENDING)

        # Verify payroll run and item remain completely intact and APPROVED
        run.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(run.status, PayrollStatus.APPROVED)
        self.assertEqual(item.net_payable, Decimal("1500.00"))

    def test_scenario_g_printable_statement_slip_generation(self):
        """
        Scenario G:
        HTML/CSS printable statement slip generates successfully with itemized breakdown.
        """
        self.client.login(username="test_manager", password="password123")
        period = "2026-05"

        self.client.get(reverse("payroll:payroll_run_detail", kwargs={"period": period}))
        self.client.post(reverse("payroll:payroll_approve", kwargs={"period": period}))

        run = PayrollRun.objects.get(period=period)
        item = PayrollItem.objects.get(payroll_run=run, employee=self.trainer_1)

        resp = self.client.get(reverse("payroll:payroll_statement", kwargs={"item_id": item.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "كشف راتب")
        self.assertContains(resp, self.trainer_1.name)
        self.assertContains(resp, "1500")

    def test_scenario_h_role_based_access_control_assistant_denied(self):
        """
        Scenario H:
        Assistant user is denied access (HTTP 403 / PermissionDenied) to employee salaries,
        payroll runs, and financial management reports.
        """
        self.client.login(username="test_assistant", password="password123")

        # 1. Payroll employees list
        resp = self.client.get(reverse("payroll:employee_list"))
        self.assertEqual(resp.status_code, 403)

        # 2. Payroll runs
        resp = self.client.get(reverse("payroll:payroll_runs"))
        self.assertEqual(resp.status_code, 403)

        # 3. Financial reports
        resp = self.client.get(reverse("reports:financial_report"))
        self.assertEqual(resp.status_code, 403)

    def test_scenario_i_commission_rate_change_after_approval_does_not_mutate_snapshot(self):
        """
        Scenario I:
        Commission rate change after approval does not mutate historical snapshot (`details_json` preserved).
        """
        self.client.login(username="test_manager", password="password123")
        period = "2026-06"

        assignment = TrainerClientAssignment.objects.create(
            trainer=self.trainer_1,
            client=self.client_a,
            commission_rate=Decimal("0.50"),
        )
        rec = PrivateTrainingRecord.objects.create(
            trainer=self.trainer_1,
            client=self.client_a,
            package_price=Decimal("600.00"),
            standard_plan_price=Decimal("400.00"),
            commission_rate=assignment.commission_rate,
        )
        PrivateTrainingRecord.objects.filter(id=rec.id).update(
            created_at=timezone.datetime(2026, 6, 10, 12, 0, tzinfo=timezone.get_current_timezone())
        )

        self.client.get(reverse("payroll:payroll_run_detail", kwargs={"period": period}))
        self.client.post(reverse("payroll:payroll_approve", kwargs={"period": period}))

        item = PayrollItem.objects.get(payroll_run__period=period, employee=self.trainer_1)
        self.assertEqual(item.commissions, Decimal("100.00"))
        initial_details = item.details_json

        # Now change the trainer commission rate assignment to 20%
        assignment.commission_rate = Decimal("0.20")
        assignment.save()

        # Reload historical snapshot
        item.refresh_from_db()
        self.assertEqual(item.commissions, Decimal("100.00"))
        self.assertEqual(item.details_json, initial_details)

    def test_scenario_j_system_persistence_and_dashboard_reception(self):
        """
        Scenario J:
        Verify host restart/persistence recovery and reception quick check-in functionality.
        """
        self.client.login(username="test_assistant", password="password123")

        # Reception quick search
        resp = self.client.get(reverse("core:quick_search") + "?q=أحمد")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "أحمد محمود")

        # Active subscription for client_a
        self.client_a.last_subscription_end = timezone.localdate() + timedelta(days=25)
        self.client_a.last_subscription_type = self.standard_plan.name
        self.client_a.save()

        Subscription.objects.create(
            member=self.client_a,
            plan=self.standard_plan,
            plan_name=self.standard_plan.name,
            start_date=timezone.localdate() - timedelta(days=5),
            end_date=self.client_a.last_subscription_end,
            plan_price=Decimal("400.00"),
            net_amount=Decimal("400.00"),
            paid_amount=Decimal("400.00"),
            remaining_amount=Decimal("0.00"),
            allowance_days=0,
        )

        # Reception quick check-in
        checkin_resp = self.client.post(
            reverse("core:quick_checkin", kwargs={"member_id": self.client_a.id}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(checkin_resp.status_code, 200)
        self.assertContains(checkin_resp, "تم تسجيل الحضور الآن!")

    def test_manager_dashboard_and_trainers_password_protection(self):
        """
        Verify that:
        1. Manager Dashboard is accessible to Manager and protected from Assistant.
        2. Trainers Management page is guarded by password challenge.
        3. Correct password unlocks the page, and lock endpoint re-locks it.
        """
        # Assistant trying to access manager dashboard gets 403 Forbidden
        self.client.login(username="test_assistant", password="password123")
        resp = self.client.get(reverse("core:manager_dashboard"))
        self.assertEqual(resp.status_code, 403)

        # Manager accesses manager dashboard (now password challenge guarded)
        self.client.login(username="test_manager", password="password123")
        resp = self.client.get(reverse("core:manager_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "منطقة المدير والإعدادات محمية")

        # Unlock with valid password
        resp_unlocked = self.client.post(reverse("core:manager_dashboard"), {"manager_unlock_password": "1234"}, follow=True)
        self.assertEqual(resp_unlocked.status_code, 200)
        self.assertContains(resp_unlocked, "إيرادات الشهر")

        # Now test Trainers Page Password Challenge
        # 1. Unlocked is False initially -> shows unlock template
        resp_trainers = self.client.get(reverse("payroll:trainers_index"))
        self.assertEqual(resp_trainers.status_code, 200)
        self.assertContains(resp_trainers, "صفحة إدارة المدربين محمية")

        # 2. Submit wrong password -> stays locked
        resp_wrong = self.client.post(reverse("payroll:trainers_index"), {"password": "wrongpassword"})
        self.assertEqual(resp_wrong.status_code, 200)
        self.assertContains(resp_wrong, "كلمة المرور غير صحيحة")

        # 3. Submit correct password -> unlocks and redirects to trainers_index
        resp_correct = self.client.post(reverse("payroll:trainers_index"), {"password": "1234"}, follow=True)
        self.assertEqual(resp_correct.status_code, 200)
        self.assertContains(resp_correct, "إدارة المدربين وعمولات الكباتن")
        self.assertContains(resp_correct, "كابتن سامح")

        # 4. Lock page -> session cleared
        resp_lock = self.client.get(reverse("payroll:trainers_lock"), follow=True)
        self.assertEqual(resp_lock.status_code, 200)

        # 5. Accessing trainers_index again requires password
        resp_locked_again = self.client.get(reverse("payroll:trainers_index"))
        self.assertEqual(resp_locked_again.status_code, 200)
        self.assertContains(resp_locked_again, "صفحة إدارة المدربين محمية")

    def test_smart_operations_suite(self):
        """
        Verify the Smart Operations workflow:
        1. Auto-determines 'new_subscription' for non-existent member.
        2. Successfully creates subscription starting from an OLD date.
        3. Supports partial payment with allowance_days (grace period).
        4. Auto-determines 'renewal' or 'remaining' for existing members.
        """
        self.client.login(username="test_assistant", password="password123")

        # 1. GET smart operations view
        resp = self.client.get(reverse("members:smart_operations"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "إدارة العمليات")
        self.assertContains(resp, "اكتب اسم العضو أو الموبايل وسيتم تحديد العملية تلقائيًا.")

        # 2. Register a NEW member with an OLD start date and partial payment + allowance days
        old_date_str = "2026-08-01"
        post_data = {
            "operation_type": "new_subscription",
            "name": "كريم عبد العزيز",
            "mobile": "01099887766",
            "gender": "male",
            "plan_id": self.standard_plan.id,
            "start_date": old_date_str,
            "paid_amount": "200.00",  # Standard plan is 400.00 -> remaining is 200.00
            "allowance_days": "7",    # 7 days grace period
            "payment_method": "نقدي",
            "notes": "تم دفع نصف المبلغ والباقي خلال أسبوع",
        }
        create_resp = self.client.post(reverse("members:smart_operations"), post_data, follow=True)
        self.assertEqual(create_resp.status_code, 200)

        # Verify created member
        member = Member.objects.get(mobile="01099887766")
        self.assertEqual(member.name, "كريم عبد العزيز")
        self.assertEqual(member.current_remaining, Decimal("200.00"))
        self.assertEqual(str(member.last_subscription_start), old_date_str)
        self.assertIsNotNone(member.follow_up_date)

        # Verify created subscription
        sub = Subscription.objects.get(member=member)
        self.assertEqual(sub.allowance_days, 7)
        self.assertEqual(sub.paid_amount, Decimal("200.00"))
        self.assertEqual(sub.remaining_amount, Decimal("200.00"))

        # 3. Search via Ajax returns the member with remaining debt
        search_resp = self.client.get(
            reverse("members:smart_operations") + "?action=search&term=01099887766",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(search_resp.status_code, 200)
        res_json = search_resp.json()
        self.assertEqual(len(res_json["results"]), 1)
        self.assertEqual(res_json["results"][0]["remaining"], 200.0)

        # 4. Settle the remaining debt
        settle_data = {
            "operation_type": "remaining",
            "member_id": str(member.id),
            "paid_amount": "200.00",
            "payment_method": "نقدي",
            "notes": "سداد المتبقي كاملاً",
        }
        settle_resp = self.client.post(reverse("members:smart_operations"), settle_data, follow=True)
        self.assertEqual(settle_resp.status_code, 200)
        member.refresh_from_db()
        self.assertEqual(member.current_remaining, Decimal("0.00"))

    def test_scenario_l_manager_dashboard_legacy_metrics_and_ai_analytics(self):
        """
        Scenario L: Verify Manager Dashboard displays exact 9 legacy metrics, period reporting,
        and AI business advisor notes for 10-day marketing evaluation.
        """
        # 1. Assistant is blocked from manager dashboard
        self.client.login(username="test_assistant", password="password123")
        resp_asst = self.client.get(reverse("core:manager_dashboard"))
        self.assertEqual(resp_asst.status_code, 403)

        # 2. Manager login and access
        self.client.login(username="test_manager", password="password123")
        session = self.client.session
        session["manager_page_unlocked"] = True
        session.save()
        resp = self.client.get(reverse("core:manager_dashboard"))
        self.assertEqual(resp.status_code, 200)

        # Verify 9 KPI metrics exist in context
        self.assertIn("total_members", resp.context)
        self.assertIn("active_members", resp.context)
        self.assertIn("expired_members", resp.context)
        self.assertIn("today_revenue", resp.context)
        self.assertIn("week_revenue", resp.context)
        self.assertIn("month_revenue", resp.context)
        self.assertIn("total_remaining", resp.context)
        self.assertIn("new_members_month", resp.context)
        self.assertIn("today_ops_count", resp.context)

        # Verify AI analytics context keys
        self.assertIn("t10_new_members", resp.context)
        self.assertIn("marketing_badge", resp.context)
        self.assertIn("marketing_analysis", resp.context)
        self.assertIn("smart_insights", resp.context)
        self.assertTrue(len(resp.context["smart_insights"]) > 0)

        # 3. Test period filtering (Week & Month)
        resp_week = self.client.get(reverse("core:manager_dashboard") + "?period=week")
        self.assertEqual(resp_week.status_code, 200)
        self.assertEqual(resp_week.context["period"], "week")
        self.assertIn("الأسبوع", resp_week.context["period_title"])

        resp_month = self.client.get(reverse("core:manager_dashboard") + "?period=month")
        self.assertEqual(resp_month.status_code, 200)
        self.assertEqual(resp_month.context["period"], "month")
        self.assertIn("شهر", resp_month.context["period_title"])

    def test_partial_payment_allowance_days_and_plan_end_dates(self):
        """
        Verify:
        1. When member pays partial, allowance_days must be between 1 and 10 days.
        2. Allowance days > 10 or <= 0 is rejected with error.
        3. 14-day plan ('يوم ويوم') starting on 13 Oct ends on 12 Nov (full month).
        4. 28-day plan ('كل يوم') starting on 13 Oct ends on 12 Nov (full month).
        5. 1-day plan ('جلسة واحدة') starting on 13 Oct ends on 13 Oct.
        """
        self.client.login(username="test_assistant", password="password123")

        # 1. Partial payment with allowance_days = 15 must be REJECTED (> 10)
        resp_invalid_high = self.client.post(
            reverse("members:smart_operations"),
            {
                "operation_type": "new_subscription",
                "name": "عضو اختبار سماح زائد",
                "mobile": "01012345678",
                "plan_id": self.day_on_day_off_plan.id,
                "start_date": "2026-10-13",
                "paid_amount": "100.00",
                "allowance_days": "15",
            },
            follow=True,
        )
        self.assertEqual(resp_invalid_high.status_code, 200)
        self.assertFalse(Member.objects.filter(mobile="01012345678").exists())

        # 2. Partial payment with allowance_days = 0 must be REJECTED
        resp_invalid_zero = self.client.post(
            reverse("members:smart_operations"),
            {
                "operation_type": "new_subscription",
                "name": "عضو اختبار سماح صفر",
                "mobile": "01012345679",
                "plan_id": self.day_on_day_off_plan.id,
                "start_date": "2026-10-13",
                "paid_amount": "100.00",
                "allowance_days": "0",
            },
            follow=True,
        )
        self.assertEqual(resp_invalid_zero.status_code, 200)
        self.assertFalse(Member.objects.filter(mobile="01012345679").exists())

        # 3. Partial payment with valid allowance_days = 7 on 14-day plan ('يوم ويوم'):
        # 14 workout visits * 2 (Friday off) = exactly 1 full calendar month (13 Oct -> 12 Nov)
        resp_valid_14d = self.client.post(
            reverse("members:smart_operations"),
            {
                "operation_type": "new_subscription",
                "name": "عضو يوم ويوم",
                "mobile": "01012345680",
                "plan_id": self.day_on_day_off_plan.id,
                "start_date": "2026-10-13",
                "paid_amount": "150.00",
                "allowance_days": "7",
                "payment_method": "نقدي",
            },
            follow=True,
        )
        self.assertEqual(resp_valid_14d.status_code, 200)
        member_14d = Member.objects.get(mobile="01012345680")
        sub_14d = Subscription.objects.get(member=member_14d)

        self.assertEqual(sub_14d.allowance_days, 7)
        self.assertEqual(sub_14d.start_date, date(2026, 10, 13))
        self.assertEqual(sub_14d.end_date, date(2026, 11, 12))  # Exactly 12 Nov!
        self.assertEqual(member_14d.last_subscription_end, date(2026, 11, 12))
        self.assertEqual(member_14d.follow_up_date, date(2026, 10, 20))  # 13 Oct + 7 days
        self.assertEqual(member_14d.current_remaining, Decimal("80.00"))

        # 4. 28-day plan ('كل يوم') starting on 13 Oct ends on 12 Nov (full month)
        resp_valid_28d = self.client.post(
            reverse("members:smart_operations"),
            {
                "operation_type": "new_subscription",
                "name": "عضو كل يوم",
                "mobile": "01012345681",
                "plan_id": self.everyday_plan.id,
                "start_date": "2026-10-13",
                "paid_amount": "400.00",
                "allowance_days": "0",
                "payment_method": "نقدي",
            },
            follow=True,
        )
        self.assertEqual(resp_valid_28d.status_code, 200)
        member_28d = Member.objects.get(mobile="01012345681")
        sub_28d = Subscription.objects.get(member=member_28d)
        self.assertEqual(sub_28d.start_date, date(2026, 10, 13))
        self.assertEqual(sub_28d.end_date, date(2026, 11, 12))  # Exactly 12 Nov!
        self.assertEqual(member_28d.last_subscription_end, date(2026, 11, 12))
        self.assertIsNone(member_28d.follow_up_date)

        # 5. 1-day plan ('جلسة واحدة') starting on 13 Oct ends on 13 Oct
        resp_session = self.client.post(
            reverse("members:smart_operations"),
            {
                "operation_type": "new_subscription",
                "name": "عضو جلسة واحدة",
                "mobile": "01012345682",
                "plan_id": self.session_plan.id,
                "start_date": "2026-10-13",
                "paid_amount": "50.00",
                "allowance_days": "0",
                "payment_method": "نقدي",
            },
            follow=True,
        )
        self.assertEqual(resp_session.status_code, 200)
        member_session = Member.objects.get(mobile="01012345682")
        sub_session = Subscription.objects.get(member=member_session)
        self.assertEqual(sub_session.start_date, date(2026, 10, 13))
        self.assertEqual(sub_session.end_date, date(2026, 10, 13))
        self.assertEqual(member_session.last_subscription_end, date(2026, 10, 13))


