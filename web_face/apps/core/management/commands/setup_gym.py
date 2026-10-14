from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.accounts.models import User, UserRole
from apps.core.models import GymProfile
from apps.members.models import Plan
from apps.payments.models import PaymentMethod
from apps.expenses.models import ExpenseCategory


class Command(BaseCommand):
    help = "Initializes a clean, ready-to-use database for any gym client with white-label branding, admin user, and standard options (0 members)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            type=str,
            default="GYM SYSTEM",
            help="Default name for the gym",
        )
        parser.add_argument(
            "--tagline",
            type=str,
            default="The Ultimate Fitness Experience",
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
            help="Password for the initial admin manager account",
        )

    def handle(self, *args, **options):
        gym_name = options["name"]
        gym_tagline = options["tagline"]
        primary_color = options["color"]
        admin_pass = options["admin_pass"]

        self.stdout.write("[*] Initializing clean gym management system...")

        # 1. Admin Superuser
        admin_user, created = User.objects.get_or_create(username="admin")
        if created or not admin_user.is_superuser:
            admin_user.set_password(admin_pass)
            admin_user.is_superuser = True
            admin_user.is_staff = True
            admin_user.role = UserRole.MANAGER
            admin_user.first_name = "Manager"
            admin_user.last_name = "Admin"
            admin_user.save()
            self.stdout.write(self.style.SUCCESS(f"[OK] Admin created: username=admin, password={admin_pass}"))
        else:
            self.stdout.write(self.style.WARNING("[!] Admin account already exists."))

        # 2. Gym Profile & White-Label Branding
        profile = GymProfile.get_solo()
        profile.gym_name = gym_name
        profile.gym_tagline = gym_tagline
        profile.primary_color = primary_color
        profile.currency = "EGP"
        profile.trainers_page_password = "1234"
        profile.face_match_threshold = 0.363
        profile.face_min_confidence = 0.55
        profile.face_debounce_seconds = 60
        profile.gate_relay_enabled = False
        profile.gate_relay_port = "COM3"
        profile.save()
        self.stdout.write(self.style.SUCCESS(f"[OK] Gym Profile initialized: '{gym_name}', Color={primary_color}"))

        # 3. Standard Subscription Plans
        standard_plans = [
            {"name": "Full Month (شهر شامل)", "price": Decimal("450.00"), "duration_days": 30, "months": 1, "frequency": "كل يوم"},
            {"name": "3 Months (3 شهور شامل)", "price": Decimal("1200.00"), "duration_days": 90, "months": 3, "frequency": "كل يوم"},
            {"name": "6 Months (6 شهور شامل)", "price": Decimal("2200.00"), "duration_days": 180, "months": 6, "frequency": "كل يوم"},
            {"name": "Annual VIP (سنة كاملة)", "price": Decimal("4000.00"), "duration_days": 365, "months": 12, "frequency": "كل يوم"},
            {"name": "Day Use (حصة تدريبية)", "price": Decimal("50.00"), "duration_days": 1, "months": 0, "frequency": "يوم واحد"},
        ]
        plans_created = 0
        for p in standard_plans:
            obj, c = Plan.objects.get_or_create(
                name=p["name"],
                defaults={
                    "price": p["price"],
                    "duration_days": p["duration_days"],
                    "months": p["months"],
                    "frequency": p["frequency"],
                    "is_active": True,
                },
            )
            if c:
                plans_created += 1
        self.stdout.write(self.style.SUCCESS(f"[OK] Seeded {plans_created} standard subscription plans."))

        # 4. Payment Methods
        methods = ["Cash (كاش نقدي)", "Vodafone Cash / InstaPay", "Visa / MasterCard"]
        for m in methods:
            PaymentMethod.objects.get_or_create(name=m, defaults={"is_active": True})
        self.stdout.write(self.style.SUCCESS("[OK] Seeded payment methods."))

        # 5. Expense Categories
        categories = [
            "Gym Rent (إيجار)",
            "Electricity & Water (فواتير)",
            "Equipment Maintenance (صيانة أجهزة)",
            "Cleaning & Supplies (نظافة ومستهلكات)",
            "Staff Advances (سلف)",
            "Marketing & Ads (تسويق)",
        ]
        for cat in categories:
            ExpenseCategory.objects.get_or_create(name=cat, defaults={"is_active": True})
        self.stdout.write(self.style.SUCCESS("[OK] Seeded expense categories."))

        self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Gym System initialized cleanly with 0 members!"))
        self.stdout.write(self.style.NOTICE("Login URL: http://127.0.0.1:8000/accounts/login/"))
        self.stdout.write(self.style.NOTICE(f"Credentials: admin / {admin_pass}\n"))
