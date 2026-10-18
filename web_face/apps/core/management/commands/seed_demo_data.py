import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.core.models import Branch, GymProfile, SystemLicense, AuditLog
from apps.members.models import Member, MemberStatus, Plan, Subscription, CheckInEvent
from apps.payments.models import Payment, PaymentMethod, PaymentOperationType, BarProduct, BarProductCategory, BarSale
from apps.expenses.models import Expense, ExpenseCategory
from apps.payroll.models import Employee, EmployeeRole, EmployeeStatus, SalaryAdjustment, AdjustmentType, AdjustmentStatus, TrainerClientAssignment, PrivateTrainingRecord
from apps.messaging.models import WhatsAppMessage, MessageStatus, MessageType


class Command(BaseCommand):
    help = "Seeds a complete, realistic, comprehensive Demo dataset for testing all features of the gym management system."

    def handle(self, *args, **options):
        import sys
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.MIGRATE_HEADING("   SYSTEMIZE GYM OS - FULL DEMO DATA SEEDING ENGINE               "))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))

        today = timezone.localdate()
        now = timezone.now()

        # -------------------------------------------------------------
        # 1. Gym Profile & Branding
        # -------------------------------------------------------------
        self.stdout.write("[1/10] Initializing Gym Profile & Branding...")
        profile = GymProfile.get_solo()
        profile.gym_name = "سيستمايز فيتنس كلوب | SYSTEMIZE FITNESS CLUB"
        profile.gym_tagline = "المنظومة الذكية المتكاملة لإدارة الصالات الرياضية بالذكاء الاصطناعي وبصمة الوجه"
        profile.primary_color = "#84CC16"
        profile.secondary_color = "#121723"
        profile.tertiary_color = "#0B0E14"
        profile.accent_theme = "lime"
        profile.currency = "ج.م"
        profile.timezone = "Africa/Cairo"
        profile.manager_mobile = "01080922432"
        profile.daily_report_time = "22:00"
        profile.face_camera_enabled = True
        profile.face_match_threshold = 0.363
        profile.face_min_confidence = 0.55
        profile.face_debounce_seconds = 60
        profile.gate_relay_enabled = True
        profile.gate_relay_type = "lan_http"
        profile.gate_ip_address = "192.168.1.50"
        profile.gate_ip_port = 80
        profile.gate_pulse_seconds = 2.5
        profile.whatsapp_enabled = True
        profile.whatsapp_randomize_templates = True
        profile.whatsapp_send_mode = "paste"
        profile.trainers_page_password = "1234"
        profile.save()
        self.stdout.write(self.style.SUCCESS(f"  [OK] Gym Profile set to: {profile.gym_name}"))

        # -------------------------------------------------------------
        # 2. System License (Demo Mode + All Features Active)
        # -------------------------------------------------------------
        self.stdout.write("[2/10] Configuring System License in Demo Mode with Multi-Branch Add-on...")
        lic = SystemLicense.objects.first()
        if not lic:
            lic = SystemLicense.objects.create(
                machine_id="DEMO-SYSTEM-MACHINE-HWID-001",
                client_name="Systemize Fitness Club (Demo Mode)",
            )
        lic.status = "demo"
        lic.license_type = "demo"
        lic.valid_until = now + timedelta(days=7)
        lic.feature_face_recognition = True
        lic.feature_gate_relay = True
        lic.feature_whatsapp = True
        lic.feature_telegram = True
        lic.feature_bar = True
        lic.feature_payroll = True
        lic.feature_retention = True
        lic.feature_reports = True
        lic.feature_barcode = True
        lic.feature_expenses = True
        lic.feature_multi_branch = True  # Enable Multi-Branch Add-on for full testing!
        lic.developer_contact_phone = "01080922432"
        lic.last_clock_check = now
        lic.save()
        self.stdout.write(self.style.SUCCESS(f"  [OK] License configured: Status={lic.status}, Multi-Branch={lic.feature_multi_branch}"))

        # -------------------------------------------------------------
        # 3. Branches (3 Multi-Branch Locations)
        # -------------------------------------------------------------
        self.stdout.write("[3/10] Seeding Multi-Branch Locations...")
        b_maadi, _ = Branch.objects.get_or_create(
            code="BR-MAADI",
            defaults={
                "name": "الفرع الرئيسي - المعادي",
                "address": "شارع النصر، المعادي الجديدة، القاهرة",
                "phone": "01080922432",
                "manager_name": "كابتن مصطفى دنيا",
                "is_main": True,
                "is_active": True,
            },
        )
        b_maadi.is_main = True
        b_maadi.save()

        b_nasr, _ = Branch.objects.get_or_create(
            code="BR-NASR",
            defaults={
                "name": "فرع مدينة نصر",
                "address": "شارع عباس العقاد، المنطقة الأولى، مدينة نصر",
                "phone": "01011223344",
                "manager_name": "كابتن طارق الديب",
                "is_main": False,
                "is_active": True,
            },
        )

        b_zayed, _ = Branch.objects.get_or_create(
            code="BR-ZAYED",
            defaults={
                "name": "فرع الشيخ زايد",
                "address": "محور 26 يوليو، أمام هايبر وان، الشيخ زايد",
                "phone": "01099887766",
                "manager_name": "كابتن هاني جمال",
                "is_main": False,
                "is_active": True,
            },
        )
        branches = [b_maadi, b_nasr, b_zayed]
        self.stdout.write(self.style.SUCCESS(f"  [OK] 3 Branches seeded: {b_maadi.name}, {b_nasr.name}, {b_zayed.name}"))

        # -------------------------------------------------------------
        # 4. User Accounts & Access Roles
        # -------------------------------------------------------------
        self.stdout.write("[4/10] Seeding Demo Users & Role Matrix (All Passwords: 1234)...")
        users_meta = [
            # Username, Role, Branch, IsSuperuser, First Name, Last Name
            ("demo", UserRole.OWNER, None, True, "المدير العام", "المالك"),
            ("admin", UserRole.OWNER, None, True, "Admin", "System"),
            ("manager_maadi", UserRole.MANAGER, b_maadi, False, "مصطفى", "دنيا"),
            ("reception_maadi", UserRole.RECEPTION, b_maadi, False, "كريم", "سامي"),
            ("manager_nasr", UserRole.MANAGER, b_nasr, False, "طارق", "الديب"),
            ("reception_nasr", UserRole.RECEPTION, b_nasr, False, "ندى", "عبد الرحمن"),
            ("manager", UserRole.MANAGER, b_maadi, True, "مدير", "المعادي"),
            ("assistant", UserRole.RECEPTION, b_maadi, False, "استقبال", "المعادي"),
        ]

        for u_name, u_role, u_branch, u_super, f_name, l_name in users_meta:
            usr, _ = User.objects.get_or_create(username=u_name)
            usr.role = u_role
            usr.branch = u_branch
            usr.is_superuser = u_super
            usr.is_staff = True
            usr.first_name = f_name
            usr.last_name = l_name
            usr.set_password("1234")
            usr.save()

        demo_user = User.objects.get(username="demo")
        self.stdout.write(self.style.SUCCESS("  [OK] Seeded Users: demo (Owner), manager_maadi, reception_maadi, manager_nasr, reception_nasr"))

        # -------------------------------------------------------------
        # 5. Subscription Plans
        # -------------------------------------------------------------
        self.stdout.write("[5/10] Seeding Subscription Plans...")
        plans_data = [
            {"name": "شهر شامل حديد ولياقة", "price": Decimal("450.00"), "duration_days": 30, "months": 1, "frequency": "كل يوم"},
            {"name": "شهر يوم ويوم (تمرين 4 ساعات)", "price": Decimal("350.00"), "duration_days": 30, "months": 1, "frequency": "يوم ويوم"},
            {"name": "3 شهور شامل سبا ومسبح", "price": Decimal("1200.00"), "duration_days": 90, "months": 3, "frequency": "كل يوم"},
            {"name": "6 شهور بلاتينيوم VIP", "price": Decimal("2200.00"), "duration_days": 180, "months": 6, "frequency": "كل يوم"},
            {"name": "سنوي VIP الذهبي", "price": Decimal("4000.00"), "duration_days": 365, "months": 12, "frequency": "كل يوم"},
            {"name": "باقة الملاكمة والكروس فيت", "price": Decimal("600.00"), "duration_days": 30, "months": 1, "frequency": "3 أيام بالأسبوع"},
            {"name": "حصة تدريبية (Day Use)", "price": Decimal("70.00"), "duration_days": 1, "months": 0, "frequency": "يوم واحد"},
        ]
        plan_objs = {}
        for pd in plans_data:
            p_obj, _ = Plan.objects.get_or_create(name=pd["name"], defaults=pd)
            p_obj.price = pd["price"]
            p_obj.duration_days = pd["duration_days"]
            p_obj.months = pd["months"]
            p_obj.frequency = pd["frequency"]
            p_obj.is_active = True
            p_obj.save()
            plan_objs[pd["name"]] = p_obj
        self.stdout.write(self.style.SUCCESS(f"  [OK] {len(plan_objs)} Subscription Plans ready."))

        # Payment Methods
        methods = ["كاش نقدي (Cash)", "إنستاباي / فودافون كاش (InstaPay)", "فيزا / ماستركارد (POS Card)"]
        for m in methods:
            PaymentMethod.objects.get_or_create(name=m, defaults={"is_active": True})

        # -------------------------------------------------------------
        # 6. Employees & Coaches (Payroll)
        # -------------------------------------------------------------
        self.stdout.write("[6/10] Seeding Coaches & Staff Employees...")
        staff_data = [
            ("كابتن إسلام عادل", "01011112222", EmployeeRole.TRAINER, Decimal("6000.00"), Decimal("50.00")),
            ("كابتن أحمد شريف", "01033334444", EmployeeRole.TRAINER, Decimal("5500.00"), Decimal("50.00")),
            ("كابتن سارة محمود", "01055556666", EmployeeRole.TRAINER, Decimal("5000.00"), Decimal("45.00")),
            ("كريم سامي", "01077778888", EmployeeRole.ASSISTANT, Decimal("4200.00"), Decimal("0.00")),
            ("ندى عبد الرحمن", "01099990000", EmployeeRole.ASSISTANT, Decimal("4000.00"), Decimal("0.00")),
        ]
        staff_objs = {}
        for name, phone, role, salary, comm in staff_data:
            emp, _ = Employee.objects.get_or_create(name=name, defaults={"phone": phone, "role": role})
            emp.phone = phone
            emp.role = role
            emp.status = EmployeeStatus.ACTIVE
            emp.fixed_salary = salary
            emp.commission_percentage = comm
            emp.hire_date = date(2025, 1, 15)
            emp.save()
            staff_objs[name] = emp

        c_islam = staff_objs["كابتن إسلام عادل"]
        c_ahmed = staff_objs["كابتن أحمد شريف"]

        # Seed Salary Adjustments for this month
        current_period = today.strftime("%Y-%m")
        SalaryAdjustment.objects.get_or_create(
            employee=c_islam,
            period=current_period,
            adjustment_type=AdjustmentType.BONUS,
            defaults={
                "category": "مكافأة تميز",
                "amount": Decimal("500.00"),
                "reason": "مكافأة تحقيق تارجت المشتركين الجدد لشهر الجاري",
                "status": AdjustmentStatus.APPROVED,
                "created_by": demo_user,
                "approved_by": demo_user,
                "approved_at": now,
            },
        )
        SalaryAdjustment.objects.get_or_create(
            employee=staff_objs["كريم سامي"],
            period=current_period,
            adjustment_type=AdjustmentType.ADVANCE,
            defaults={
                "category": "سلفة على الراتب",
                "amount": Decimal("1000.00"),
                "reason": "سلفة مستردة من راتب الشهر الحالي",
                "status": AdjustmentStatus.APPROVED,
                "created_by": demo_user,
                "approved_by": demo_user,
                "approved_at": now,
            },
        )
        SalaryAdjustment.objects.get_or_create(
            employee=staff_objs["ندى عبد الرحمن"],
            period=current_period,
            adjustment_type=AdjustmentType.DEDUCTION,
            defaults={
                "category": "خصم تأخير",
                "amount": Decimal("150.00"),
                "reason": "تأخير متكرر عن موعد بدء الشفت المسائي",
                "status": AdjustmentStatus.APPROVED,
                "created_by": demo_user,
                "approved_by": demo_user,
                "approved_at": now,
            },
        )
        self.stdout.write(self.style.SUCCESS("  [OK] Employees, Bonuses, Advances, and Deductions seeded."))

        # -------------------------------------------------------------
        # 7. Expense Categories & Operating Expenses
        # -------------------------------------------------------------
        self.stdout.write("[7/10] Seeding Operating Expenses across branches...")
        exp_cats = [
            "إيجار المقر والفرع",
            "فواتير الكهرباء والمياه",
            "صيانة الأجهزة والمعدات",
            "نظافة ومستلزمات تعقيم",
            "تسويق وإعلانات سبونسر",
            "بوفيه واستقبال وضيافة",
        ]
        cat_objs = {}
        for c in exp_cats:
            obj, _ = ExpenseCategory.objects.get_or_create(name=c, defaults={"is_active": True})
            cat_objs[c] = obj

        expenses_sample = [
            (cat_objs["إيجار المقر والفرع"], Decimal("22000.00"), "إيجار مقر الفرع الرئيسي لشهر الجاري", today.replace(day=1), b_maadi),
            (cat_objs["إيجار المقر والفرع"], Decimal("18000.00"), "إيجار فرع مدينة نصر لشهر الجاري", today.replace(day=1), b_nasr),
            (cat_objs["إيجار المقر والفرع"], Decimal("16000.00"), "إيجار فرع الشيخ زايد لشهر الجاري", today.replace(day=1), b_zayed),
            (cat_objs["فواتير الكهرباء والمياه"], Decimal("3850.00"), "فاتورة كهرباء فرع المعادي والتكييف المركزي", today - timedelta(days=5), b_maadi),
            (cat_objs["فواتير الكهرباء والمياه"], Decimal("2900.00"), "فاتورة كهرباء ومياه فرع مدينة نصر", today - timedelta(days=6), b_nasr),
            (cat_objs["صيانة الأجهزة والمعدات"], Decimal("1450.00"), "تغيير سيور المشايات الرياضية وتزييت الوايرات", today - timedelta(days=2), b_maadi),
            (cat_objs["صيانة الأجهزة والمعدات"], Decimal("800.00"), "صيانة أجهزة الكابل كروس والأوزان", today - timedelta(days=8), b_nasr),
            (cat_objs["نظافة ومستلزمات تعقيم"], Decimal("1200.00"), "شراء معقمات ومطهرات أرضيات ورولات مناشف", today - timedelta(days=3), b_maadi),
            (cat_objs["نظافة ومستلزمات تعقيم"], Decimal("950.00"), "مستلزمات نظافة دورات المياه والساونا", today - timedelta(days=7), b_zayed),
            (cat_objs["تسويق وإعلانات سبونسر"], Decimal("3500.00"), "حملة إعلانات ممولة فيسبوك وإنستجرام لعروض التجديد", today - timedelta(days=10), b_maadi),
            (cat_objs["بوفيه واستقبال وضيافة"], Decimal("650.00"), "مشروبات واستضافة كبار العملاء والزوار", today - timedelta(days=1), b_maadi),
        ]
        for c_cat, amount, desc, exp_date, exp_branch in expenses_sample:
            Expense.objects.get_or_create(
                category=c_cat,
                amount=amount,
                expense_date=exp_date,
                branch=exp_branch,
                defaults={"description": desc, "created_by": demo_user},
            )
        self.stdout.write(self.style.SUCCESS(f"  [OK] {len(expenses_sample)} Operating Expenses recorded."))

        # -------------------------------------------------------------
        # 8. Bar & Supplements Inventory & POS Sales
        # -------------------------------------------------------------
        self.stdout.write("[8/10] Seeding Bar Products and Sales...")
        products_data = [
            ("مياه معدنية طبيعية 600 مل", BarProductCategory.DRINKS, Decimal("10.00"), Decimal("5.00"), 48, 10),
            ("مشروب طاقة ريد بول أوريجينال", BarProductCategory.DRINKS, Decimal("45.00"), Decimal("30.00"), 24, 6),
            ("سكوب واي بروتين جولد ستاندرد", BarProductCategory.SUPPLEMENTS, Decimal("65.00"), Decimal("38.00"), 30, 8),
            ("سكوب كرياتين مونوهيدرات ميكرونيزد", BarProductCategory.SUPPLEMENTS, Decimal("35.00"), Decimal("18.00"), 6, 10),  # Alert low stock
            ("بروتين بار شوكولاتة كيتو 60 جم", BarProductCategory.SNACKS, Decimal("45.00"), Decimal("26.00"), 18, 5),
            ("شيكر هالك الرياضي بريميوم 700 مل", BarProductCategory.OTHER, Decimal("120.00"), Decimal("70.00"), 12, 4),
        ]
        prod_objs = []
        for name, cat, price, cost, stock, min_alert in products_data:
            prod, _ = BarProduct.objects.get_or_create(
                name=name,
                defaults={
                    "category": cat,
                    "price": price,
                    "cost_price": cost,
                    "stock_quantity": stock,
                    "min_stock_alert": min_alert,
                    "is_active": True,
                },
            )
            prod.stock_quantity = stock
            prod.save()
            prod_objs.append(prod)

        # Seed Bar Sales
        bar_sales_specs = [
            (prod_objs[0], 2, Decimal("20.00"), True, "كاش نقدي (Cash)", "أحمد حسام الدين"),
            (prod_objs[1], 1, Decimal("45.00"), True, "كاش نقدي (Cash)", "طارق السعيد"),
            (prod_objs[2], 1, Decimal("65.00"), True, "إنستاباي / فودافون كاش (InstaPay)", "محمود عبد العزيز"),
            (prod_objs[3], 1, Decimal("35.00"), True, "كاش نقدي (Cash)", "لاعب كمال أجسام"),
            (prod_objs[4], 2, Decimal("90.00"), True, "فيزا / ماستركارد (POS Card)", "محمد سامي"),
            (prod_objs[0], 3, Decimal("30.00"), False, "نقدي (آجل)", "عمر فاروق الشريف"),  # Unpaid debt
            (prod_objs[5], 1, Decimal("120.00"), True, "كاش نقدي (Cash)", "ياسر كمال"),
        ]
        for idx, (p, qty, tot, is_p, meth, buyer) in enumerate(bar_sales_specs, start=1):
            sale_id = f"BAR-{today.strftime('%y%m%d')}-{idx:03d}"
            BarSale.objects.get_or_create(
                sale_id=sale_id,
                defaults={
                    "product": p,
                    "quantity": qty,
                    "unit_price": p.price,
                    "total_price": tot,
                    "is_paid": is_p,
                    "payment_method": meth,
                    "buyer_name": buyer,
                    "created_by": demo_user,
                    "paid_at": now if is_p else None,
                },
            )
        self.stdout.write(self.style.SUCCESS("  [OK] Bar Products & POS Sales seeded."))

        # -------------------------------------------------------------
        # 9. Key Test Member Personas & Member Distribution
        # -------------------------------------------------------------
        self.stdout.write("[9/10] Seeding Dedicated Test Personas & Member Realism...")

        test_personas = [
            # ID, Name, Mobile, Plan Name, Status, End Delta Days, Paid, Debt, Has Private, Coach, Alternate Days, Branch
            {
                "id": "MEM-1001",
                "name": "أحمد حسام الدين",
                "mobile": "01001234567",
                "gender": "male",
                "plan": "سنوي VIP الذهبي",
                "status": MemberStatus.ACTIVE,
                "end_delta": 90,
                "paid": Decimal("4000.00"),
                "debt": Decimal("0.00"),
                "has_private": False,
                "coach": None,
                "branch": b_maadi,
                "notes": "عضو VIP سنوي ملتزم جداً",
            },
            {
                "id": "MEM-1002",
                "name": "محمود عبد العزيز الشناوي",
                "mobile": "01012345678",
                "gender": "male",
                "plan": "شهر شامل حديد ولياقة",
                "status": MemberStatus.ACTIVE,
                "end_delta": 2,  # Expiring in 2 days (Warning test)
                "paid": Decimal("450.00"),
                "debt": Decimal("0.00"),
                "has_private": False,
                "coach": None,
                "branch": b_maadi,
                "notes": "متبقي يومان على الاشتراك - مرشح للتنبيه الآلي بالواتساب",
            },
            {
                "id": "MEM-1003",
                "name": "طارق السعيد مصطفى",
                "mobile": "01023456789",
                "gender": "male",
                "plan": "شهر شامل حديد ولياقة",
                "status": MemberStatus.ACTIVE,
                "end_delta": 1,  # Expiring tomorrow (Critical test)
                "paid": Decimal("450.00"),
                "debt": Decimal("0.00"),
                "has_private": False,
                "coach": None,
                "branch": b_nasr,
                "notes": "متبقي يوم واحد على الاشتراك - تنبيه حرج",
            },
            {
                "id": "MEM-1004",
                "name": "خالد إبراهيم النجار",
                "mobile": "01034567890",
                "gender": "male",
                "plan": "شهر شامل حديد ولياقة",
                "status": MemberStatus.EXPIRED,
                "end_delta": -5,  # Expired 5 days ago (Access denied test)
                "paid": Decimal("450.00"),
                "debt": Decimal("0.00"),
                "has_private": False,
                "coach": None,
                "branch": b_maadi,
                "notes": "الاشتراك منتهي - يختبر منع الدخول بالبصمة وإرسال رسالة العودة",
            },
            {
                "id": "MEM-1005",
                "name": "عمر فاروق الشريف",
                "mobile": "01045678901",
                "gender": "male",
                "plan": "3 شهور شامل سبا ومسبح",
                "status": MemberStatus.ACTIVE,
                "end_delta": 65,
                "paid": Decimal("700.00"),
                "debt": Decimal("500.00"),  # Has Remaining Debt
                "has_private": False,
                "coach": None,
                "branch": b_maadi,
                "notes": "عليه مديونية متبقية 500 ج.م - لاختبار تنبيه الديون وشاشة التحصيل",
            },
            {
                "id": "MEM-1006",
                "name": "ياسر كمال المنشاوي",
                "mobile": "01056789012",
                "gender": "male",
                "plan": "شهر يوم ويوم (تمرين 4 ساعات)",
                "status": MemberStatus.ACTIVE,
                "end_delta": 22,
                "paid": Decimal("350.00"),
                "debt": Decimal("0.00"),
                "has_private": False,
                "coach": None,
                "branch": b_nasr,
                "notes": "باقة يوم ويوم مع نافذة 4 ساعات - لاختبار قيود الدخول الذكية",
            },
            {
                "id": "MEM-1007",
                "name": "محمد سامي رضوان",
                "mobile": "01067890123",
                "gender": "male",
                "plan": "شهر شامل حديد ولياقة",
                "status": MemberStatus.ACTIVE,
                "end_delta": 28,
                "paid": Decimal("1950.00"),
                "debt": Decimal("0.00"),
                "has_private": True,
                "coach": c_islam,
                "branch": b_maadi,
                "notes": "مشترك في تدريب خاص Private مع كابتن إسلام عادل (1500 ج.م عمولة)",
            },
            {
                "id": "MEM-1008",
                "name": "ياسمين عادل زهران",
                "mobile": "01078901234",
                "gender": "female",
                "plan": "3 شهور شامل سبا ومسبح",
                "status": MemberStatus.ACTIVE,
                "end_delta": 45,
                "paid": Decimal("1200.00"),
                "debt": Decimal("0.00"),
                "has_private": False,
                "coach": None,
                "branch": b_zayed,
                "notes": "لاعبة في فرع الشيخ زايد",
            },
            {
                "id": "MEM-1009",
                "name": "كريم مجدي الصاوي",
                "mobile": "01089012345",
                "gender": "male",
                "plan": "باقة الملاكمة والكروس فيت",
                "status": MemberStatus.ACTIVE,
                "end_delta": 18,
                "paid": Decimal("600.00"),
                "debt": Decimal("0.00"),
                "has_private": True,
                "coach": c_ahmed,
                "branch": b_nasr,
                "notes": "تدريب كيك بوكسينغ وبوكسينغ",
            },
        ]

        created_personas = []
        for p in test_personas:
            mem, _ = Member.objects.get_or_create(member_id=p["id"])
            mem.name = p["name"]
            mem.mobile = p["mobile"]
            mem.gender = p["gender"]
            mem.current_status = p["status"]
            mem.branch = p["branch"]
            mem.notes = p["notes"]
            mem.has_face_enrolled = True
            mem.face_enrolled_at = now - timedelta(days=15)

            # Dates
            end_d = today + timedelta(days=p["end_delta"])
            start_d = end_d - timedelta(days=30 if "شهر" in p["plan"] else (90 if "3" in p["plan"] else 365))
            mem.last_subscription_start = start_d
            mem.last_subscription_end = end_d
            mem.last_subscription_type = p["plan"]
            mem.current_paid = p["paid"]
            mem.current_remaining = p["debt"]
            mem.total_paid = p["paid"]
            mem.last_payment_date = now - timedelta(days=5)

            if p["has_private"]:
                mem.has_private = True
                mem.assigned_coach = p["coach"]
                mem.private_price = Decimal("1500.00")
            else:
                mem.has_private = False
                mem.assigned_coach = None
                mem.private_price = Decimal("0.00")

            mem.save()
            created_personas.append(mem)

            # Create corresponding Subscription record
            plan_obj = plan_objs.get(p["plan"], plan_objs["شهر شامل حديد ولياقة"])
            sub, _ = Subscription.objects.get_or_create(
                member=mem,
                start_date=start_d,
                defaults={
                    "plan": plan_obj,
                    "plan_name": plan_obj.name,
                    "end_date": end_d,
                    "plan_price": plan_obj.price,
                    "has_private": p["has_private"],
                    "private_price": Decimal("1500.00") if p["has_private"] else Decimal("0.00"),
                    "coach": p["coach"],
                    "coach_commission_rate": Decimal("0.5000"),
                    "coach_commission_amount": Decimal("750.00") if p["has_private"] else Decimal("0.00"),
                    "discount": Decimal("0.00"),
                    "net_amount": p["paid"] + p["debt"],
                    "paid_amount": p["paid"],
                    "remaining_amount": p["debt"],
                    "operation_type": "new_subscription",
                    "payment_method": "كاش نقدي (Cash)",
                    "created_by": demo_user,
                },
            )

            # Create Payment record for paid amount
            if p["paid"] > Decimal("0.00"):
                p_id = f"PAY-{mem.member_id}"
                inv_no = f"INV-{mem.member_id}"
                Payment.objects.get_or_create(
                    payment_id=p_id,
                    defaults={
                        "invoice_no": inv_no,
                        "operation_type": PaymentOperationType.NEW_SUBSCRIPTION,
                        "member": mem,
                        "subscription": sub,
                        "amount": p["paid"],
                        "payment_method": "كاش نقدي (Cash)",
                        "branch": mem.branch,
                        "created_by": demo_user,
                    },
                )

        # Distribute and revitalize existing members database
        all_members = list(Member.objects.exclude(member_id__startswith="MEM-100"))
        random.seed(42)  # Deterministic seed for consistency
        for idx, mem in enumerate(all_members):
            # Distribute branch
            if not mem.branch:
                chosen_branch = b_maadi if (idx % 3 == 0) else (b_nasr if (idx % 3 == 1) else b_zayed)
                mem.branch = chosen_branch

            # Revitalize ~70 members to be Active with healthy future dates
            if idx < 75:
                mem.current_status = MemberStatus.ACTIVE
                days_ahead = random.randint(10, 150)
                mem.last_subscription_end = today + timedelta(days=days_ahead)
                mem.last_subscription_start = mem.last_subscription_end - timedelta(days=random.choice([30, 90, 180]))
                mem.has_face_enrolled = True
                mem.last_subscription_type = random.choice([
                    "شهر شامل حديد ولياقة",
                    "3 شهور شامل سبا ومسبح",
                    "6 شهور بلاتينيوم VIP",
                    "سنوي VIP الذهبي",
                ])

                # Give some members debt
                if idx % 5 == 0:
                    mem.current_remaining = Decimal(str(random.choice([150, 250, 400, 600])))
                else:
                    mem.current_remaining = Decimal("0.00")

                mem.current_paid = Decimal("450.00")
            elif idx < 95:
                # Expiring soon (1 to 3 days)
                mem.current_status = MemberStatus.ACTIVE
                mem.last_subscription_end = today + timedelta(days=random.choice([1, 2, 3]))
                mem.last_subscription_start = mem.last_subscription_end - timedelta(days=30)
                mem.last_subscription_type = "شهر شامل حديد ولياقة"
                mem.current_remaining = Decimal("0.00")
                mem.has_face_enrolled = True
            else:
                # Expired
                mem.current_status = MemberStatus.EXPIRED
                days_ago = random.randint(3, 90)
                mem.last_subscription_end = today - timedelta(days=days_ago)
                mem.last_subscription_start = mem.last_subscription_end - timedelta(days=30)
                mem.last_subscription_type = "شهر شامل حديد ولياقة"

            mem.save()

        self.stdout.write(self.style.SUCCESS(f"  [OK] Persona test accounts seeded and {len(all_members)} members distributed across branches."))

        # -------------------------------------------------------------
        # 10. Check-Ins & Attendance History (Today + Past 14 Days)
        # -------------------------------------------------------------
        self.stdout.write("[10/10] Seeding Realistic Attendance History & Today's Check-ins...")

        # A) Today's Check-ins
        today_checkins_count = 0
        active_pool = list(Member.objects.filter(current_status=MemberStatus.ACTIVE)[:30])
        for idx, mem in enumerate(active_pool):
            checkin_hour = 8 + (idx % 14)  # Spread from 8 AM to 10 PM
            checkin_min = (idx * 7) % 60
            c_time = timezone.make_aware(datetime.combine(today, datetime.min.time())).replace(hour=checkin_hour, minute=checkin_min)

            CheckInEvent.objects.create(
                member=mem,
                checked_in_at=c_time,
                method="face" if mem.has_face_enrolled else "manual",
                confidence=round(random.uniform(0.85, 0.98), 2) if mem.has_face_enrolled else None,
                status_snapshot="active",
                days_left_snapshot=mem.days_left,
                debt_snapshot=mem.current_remaining,
                branch=mem.branch or b_maadi,
            )
            today_checkins_count += 1

        # Also add a specific denied check-in for the expired persona
        expired_mem = Member.objects.get(member_id="MEM-1004")
        CheckInEvent.objects.create(
            member=expired_mem,
            checked_in_at=now - timedelta(minutes=45),
            method="face",
            confidence=0.94,
            status_snapshot="denied_expired",
            days_left_snapshot=0,
            debt_snapshot=Decimal("0.00"),
            branch=b_maadi,
        )

        # B) Historical check-ins for the past 14 days
        hist_count = 0
        for day_offset in range(1, 15):
            past_date = today - timedelta(days=day_offset)
            daily_members = random.sample(active_pool, min(len(active_pool), random.randint(12, 22)))
            for m in daily_members:
                h = random.randint(9, 21)
                minute = random.randint(0, 59)
                t = timezone.make_aware(datetime.combine(past_date, datetime.min.time())).replace(hour=h, minute=minute)
                CheckInEvent.objects.create(
                    member=m,
                    checked_in_at=t,
                    method="face",
                    confidence=round(random.uniform(0.88, 0.97), 2),
                    status_snapshot="active",
                    days_left_snapshot=m.days_left + day_offset,
                    debt_snapshot=Decimal("0.00"),
                    branch=m.branch or b_maadi,
                )
                hist_count += 1

        self.stdout.write(self.style.SUCCESS(f"  [OK] {today_checkins_count} check-ins for today + {hist_count} historical check-ins recorded."))

        # -------------------------------------------------------------
        # 11. WhatsApp Messages Queue
        # -------------------------------------------------------------
        wa_messages = [
            ("01001234567", "مرحباً يا بطل! تم تجديد اشتراكك بنجاح في هالك فيتنس كلوب. فورمتك تهمنا!", MessageType.RECEIPT, MessageStatus.SENT, "أحمد حسام الدين"),
            ("01012345678", "تنبيه ودي: متبقي يومان فقط على اشتراكك في هالك فيتنس. مستنيينك تجدد علشان تستمر في الفورمة!", MessageType.REMINDER_3, MessageStatus.PENDING, "محمود عبد العزيز"),
            ("01023456789", "تنبيه هام: غداً آخر يوم في اشتراكك الرياضي. مكتب الاستقبال في انتظارك بأفضل عروض التجديد!", MessageType.REMINDER_1, MessageStatus.PENDING, "طارق السعيد"),
            ("01034567890", "اشتقنالك في هالك جيم! اشتراكك انتهى، وبنقدملك خصم تجديد خاص علشان ترجع بقوة. مستنيينك!", MessageType.EXPIRED, MessageStatus.PENDING, "خالد إبراهيم"),
            ("01045678901", "إشعار حسابات: متبقي على حسابك مبلغ 500 ج.م برجاء السداد مع أقرب زيارة. شكراً لتعاونك", MessageType.CUSTOM, MessageStatus.SENT, "عمر فاروق"),
        ]
        for mob, msg, m_type, m_status, rec_name in wa_messages:
            WhatsAppMessage.objects.get_or_create(
                dedup_key=f"DEMO-WA-{mob}-{m_type}",
                defaults={
                    "mobile": mob,
                    "message": msg,
                    "msg_type": m_type,
                    "status": m_status,
                    "recipient_name": rec_name,
                    "recipient_type": "member",
                    "sent_at": now if m_status == MessageStatus.SENT else None,
                },
            )
        self.stdout.write(self.style.SUCCESS("  [OK] WhatsApp Messaging Queue ready with sample notifications."))

        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.SUCCESS("   [SUCCESS] FULL DEMO DATA SEEDED SUCCESSFULLY! SYSTEM IS 100% READY"))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.NOTICE("Main Demo Owner Account:   demo / 1234  (All Branches & Full Permissions)"))
        self.stdout.write(self.style.NOTICE("Maadi Branch Manager:      manager_maadi / 1234"))
        self.stdout.write(self.style.NOTICE("Maadi Reception:           reception_maadi / 1234"))
        self.stdout.write(self.style.NOTICE("Nasr City Manager:         manager_nasr / 1234"))
        self.stdout.write(self.style.NOTICE("Nasr City Reception:       reception_nasr / 1234"))
        self.stdout.write(self.style.NOTICE("URL:                       http://127.0.0.1:8000/accounts/login/\n"))
