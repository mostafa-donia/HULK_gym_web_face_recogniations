from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.core.models import Branch, GymProfile, SystemLicense
from apps.members.models import Plan
from apps.payments.models import PaymentMethod, BarProductCategory
from apps.expenses.models import ExpenseCategory


class Command(BaseCommand):
    help = "Initializes a clean, ready-to-deploy database for any gym client with 0 members, default plans, branches, and demo/admin accounts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            type=str,
            default="Systemize Fitness Club",
            help="Default name for the gym",
        )
        parser.add_argument(
            "--tagline",
            type=str,
            default="المنظومة الذكية المتكاملة لإدارة الصالات الرياضية بالذكاء الاصطناعي وبصمة الوجه",
            help="Slogan / Tagline for the gym",
        )
        parser.add_argument(
            "--color",
            type=str,
            default="#84CC16",
            help="Primary brand color hex (default #84CC16)",
        )
        parser.add_argument(
            "--admin-pass",
            type=str,
            default="admin123456",
            help="Password for admin account",
        )
        parser.add_argument(
            "--demo-pass",
            type=str,
            default="1234",
            help="Password for demo account",
        )

    def handle(self, *args, **options):
        import sys
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        gym_name = options["name"]
        gym_tagline = options["tagline"]
        primary_color = options["color"]
        admin_pass = options["admin_pass"]
        demo_pass = options["demo_pass"]

        self.stdout.write("[*] Initializing clean client database for Systemize Gym OS...")

        # 1. Main Branch
        main_branch, _ = Branch.objects.get_or_create(
            code="BR-MAIN",
            defaults={
                "name": "الفرع الرئيسي",
                "address": "المقر الرئيسي للصالة الرياضية",
                "phone": "01000000000",
                "manager_name": "إدارة الفرع",
                "is_main": True,
                "is_active": True,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"[OK] Main Branch: '{main_branch.name}'"))

        # 2. User Accounts
        # Admin Superuser
        admin_user, _ = User.objects.get_or_create(username="admin")
        admin_user.set_password(admin_pass)
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_user.role = UserRole.OWNER
        admin_user.first_name = "Admin"
        admin_user.last_name = "System"
        admin_user.branch = main_branch
        admin_user.save()
        self.stdout.write(self.style.SUCCESS(f"[OK] Admin created: username=admin, password={admin_pass}"))

        # Demo Account
        demo_user, _ = User.objects.get_or_create(username="demo")
        demo_user.set_password(demo_pass)
        demo_user.is_superuser = True
        demo_user.is_staff = True
        demo_user.role = UserRole.OWNER
        demo_user.first_name = "المدير العام"
        demo_user.last_name = "المالك"
        demo_user.branch = main_branch
        demo_user.save()
        self.stdout.write(self.style.SUCCESS(f"[OK] Demo user created: username=demo, password={demo_pass}"))

        # Manager Account
        manager_user, _ = User.objects.get_or_create(username="manager")
        manager_user.set_password(demo_pass)
        manager_user.is_superuser = False
        manager_user.is_staff = True
        manager_user.role = UserRole.MANAGER
        manager_user.first_name = "مدير"
        manager_user.last_name = "الفرع"
        manager_user.branch = main_branch
        manager_user.save()

        # Reception Account
        reception_user, _ = User.objects.get_or_create(username="reception")
        reception_user.set_password(demo_pass)
        reception_user.is_superuser = False
        reception_user.is_staff = False
        reception_user.role = UserRole.RECEPTION
        reception_user.first_name = "موظف"
        reception_user.last_name = "الاستقبال"
        reception_user.branch = main_branch
        reception_user.save()

        # 3. Gym Profile & White-Label Branding
        profile = GymProfile.get_solo()
        profile.gym_name = gym_name
        profile.gym_tagline = gym_tagline
        profile.primary_color = primary_color
        profile.secondary_color = "#121723"
        profile.tertiary_color = "#0B0E14"
        profile.accent_theme = "lime"
        profile.currency = "ج.م"
        profile.timezone = "Africa/Cairo"
        profile.trainers_page_password = "1234"
        profile.face_camera_enabled = True
        profile.face_match_threshold = 0.363
        profile.face_min_confidence = 0.55
        profile.face_debounce_seconds = 60
        profile.gate_relay_enabled = False
        profile.gate_relay_type = "lan_http"
        profile.gate_ip_address = "192.168.1.50"
        profile.gate_ip_port = 80
        profile.whatsapp_enabled = True
        profile.whatsapp_randomize_templates = True
        profile.whatsapp_send_mode = "paste"
        profile.save()
        self.stdout.write(self.style.SUCCESS(f"[OK] Gym Profile initialized: '{gym_name}'"))

        # 4. System License (Active Trial / Demo Mode)
        now = timezone.now()
        lic = SystemLicense.objects.first()
        if not lic:
            lic = SystemLicense.objects.create(
                machine_id="SYSTEMIZE-CLIENT-STANDALONE",
                client_name=f"{gym_name} (Client Installation)",
            )
        lic.status = "active"
        lic.license_type = "perpetual"
        lic.valid_until = now + timedelta(days=365)
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
        lic.feature_multi_branch = True
        lic.developer_contact_phone = "01080922432"
        lic.last_clock_check = now
        lic.save()
        self.stdout.write(self.style.SUCCESS(f"[OK] System License activated with all features."))

        # 5. Standard Subscription Plans
        standard_plans = [
            {"name": "شهر شامل حديد ولياقة", "price": Decimal("450.00"), "duration_days": 30, "months": 1, "frequency": "كل يوم"},
            {"name": "شهر يوم ويوم (تمرين 4 ساعات)", "price": Decimal("350.00"), "duration_days": 30, "months": 1, "frequency": "يوم ويوم"},
            {"name": "3 شهور شامل لياقة ومسبح", "price": Decimal("1200.00"), "duration_days": 90, "months": 3, "frequency": "كل يوم"},
            {"name": "6 شهور بلاتينيوم VIP", "price": Decimal("2200.00"), "duration_days": 180, "months": 6, "frequency": "كل يوم"},
            {"name": "سنوي VIP الذهبي", "price": Decimal("4000.00"), "duration_days": 365, "months": 12, "frequency": "كل يوم"},
            {"name": "حصة تجريبية Day-Use", "price": Decimal("50.00"), "duration_days": 1, "months": 0, "frequency": "يوم واحد"},
        ]
        for p in standard_plans:
            Plan.objects.get_or_create(
                name=p["name"],
                defaults={
                    "price": p["price"],
                    "duration_days": p["duration_days"],
                    "months": p["months"],
                    "frequency": p["frequency"],
                    "is_active": True,
                },
            )
        self.stdout.write(self.style.SUCCESS(f"[OK] Seeded {len(standard_plans)} standard subscription plans."))

        # 6. Payment Methods
        methods = ["كاش نقدي (Cash)", "فودافون كاش / إنستاباي (InstaPay)", "فيزا / بطاقة بنكية (Visa/MasterCard)"]
        for m in methods:
            PaymentMethod.objects.get_or_create(name=m, defaults={"is_active": True})
        self.stdout.write(self.style.SUCCESS("[OK] Seeded payment methods."))

        # 7. Expense Categories
        categories = [
            "إيجار الصالة (Gym Rent)",
            "فواتير كهرباء ومياه وإنترنت",
            "صيانة أجهزة ومعدات رياضية",
            "نظافة ومستهلكات ورقية",
            "سلف ومصروفات موظفين",
            "دعاية وتسويق وإعلانات",
            "مشتريات بوفيه وبار",
        ]
        for cat in categories:
            ExpenseCategory.objects.get_or_create(name=cat, defaults={"is_active": True})
        self.stdout.write(self.style.SUCCESS("[OK] Seeded expense categories."))

        self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Systemize initialized cleanly with 0 members! Ready for client delivery."))
        self.stdout.write(self.style.NOTICE("Login URL: http://127.0.0.1:8000/accounts/login/"))
        self.stdout.write(self.style.NOTICE(f"Owner Demo: demo / {demo_pass}"))
        self.stdout.write(self.style.NOTICE(f"Admin Superuser: admin / {admin_pass}"))
