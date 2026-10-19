import sys
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User, UserRole
from apps.core.models import Branch, GymProfile, SystemLicense
from apps.members.models import Member, Subscription, CheckInEvent, Plan
from apps.payments.models import Payment, BarSale, BarProduct, BarProductCategory, PaymentMethod
from apps.expenses.models import Expense, ExpenseCategory
from apps.payroll.models import (
    Employee, PayrollRun, PayrollItem,
    SalaryAdjustment, TrainerClientAssignment, PrivateTrainingRecord
)
from apps.messaging.models import WhatsAppMessage


class Command(BaseCommand):
    help = "Resets the database into a clean, empty, ready-for-real-gym production state with 0 members and 0 transactions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            type=str,
            default="Systemize Gym & Fitness",
            help="Gym Name for the clean installation",
        )
        parser.add_argument(
            "--keep-trainers",
            action="store_true",
            help="Keep employee/trainer records",
        )

    def handle(self, *args, **options):
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.MIGRATE_HEADING("      RESETTING DATABASE TO CLEAN ZERO-DATA BLANK VERSION         "))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))

        gym_name = options.get("name") or "Systemize Gym & Fitness"
        now = timezone.now()

        # -----------------------------------------------------------------
        # 1. Clear All Transactional & Member Data
        # -----------------------------------------------------------------
        self.stdout.write("[1/6] Purging transactional tables (Members, Payments, Check-ins, Bar Sales)...")
        CheckInEvent.objects.all().delete()
        Subscription.objects.all().delete()
        Member.objects.all().delete()
        BarSale.objects.all().delete()
        Payment.objects.all().delete()
        Expense.objects.all().delete()
        PayrollItem.objects.all().delete()
        PayrollRun.objects.all().delete()
        SalaryAdjustment.objects.all().delete()
        TrainerClientAssignment.objects.all().delete()
        PrivateTrainingRecord.objects.all().delete()
        WhatsAppMessage.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("  [OK] All transactions, members, check-ins, and finances cleared."))

        # -----------------------------------------------------------------
        # 2. Ensure Main Branch Exists
        # -----------------------------------------------------------------
        self.stdout.write("[2/6] Configuring clean default branches...")
        main_branch = Branch.objects.filter(is_main=True).first()
        if not main_branch:
            main_branch = Branch.objects.create(
                code="BR-MAIN",
                name="الفرع الرئيسي",
                address="المقر الرئيسي للصالة الرياضية",
                phone="01000000000",
                manager_name="إدارة الفرع",
                is_main=True,
                is_active=True,
            )
        self.stdout.write(self.style.SUCCESS(f"  [OK] Default branch: '{main_branch.name}'"))

        # -----------------------------------------------------------------
        # 3. Ensure Default Users with standard passwords (1234)
        # -----------------------------------------------------------------
        self.stdout.write("[3/6] Verifying administrative user accounts (admin, demo, manager, assistant)...")
        # Admin Superuser
        admin_user, _ = User.objects.get_or_create(username="admin")
        admin_user.set_password("1234")
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_user.role = UserRole.OWNER
        admin_user.first_name = "Admin"
        admin_user.branch = main_branch
        admin_user.save()

        # Demo Account
        demo_user, _ = User.objects.get_or_create(username="demo")
        demo_user.set_password("1234")
        demo_user.is_superuser = True
        demo_user.is_staff = True
        demo_user.role = UserRole.OWNER
        demo_user.first_name = "المدير العام"
        demo_user.branch = main_branch
        demo_user.save()

        # Manager Account
        manager_user, _ = User.objects.get_or_create(username="manager")
        manager_user.set_password("1234")
        manager_user.is_staff = True
        manager_user.role = UserRole.MANAGER
        manager_user.first_name = "مدير الفرع"
        manager_user.branch = main_branch
        manager_user.save()

        # Reception Account
        reception_user, _ = User.objects.get_or_create(username="assistant")
        reception_user.set_password("1234")
        reception_user.role = UserRole.RECEPTION
        reception_user.first_name = "الاستقبال"
        reception_user.branch = main_branch
        reception_user.save()

        self.stdout.write(self.style.SUCCESS("  [OK] Users ready: admin, demo, manager, assistant (All Passwords: 1234)."))

        # -----------------------------------------------------------------
        # 4. Clean System License (Lifetime, No Countdown Lag)
        # -----------------------------------------------------------------
        self.stdout.write("[4/6] Activating clean perpetual license with all 10 features...")
        from apps.core.licensing.hwid import get_hardware_fingerprint
        from apps.core.licensing.crypto import compute_tamper_token

        current_hwid = get_hardware_fingerprint()
        lic = SystemLicense.objects.first()
        if not lic:
            lic = SystemLicense(machine_id=current_hwid)
        else:
            lic.machine_id = current_hwid

        lic.client_name = f"{gym_name} (نسخة جديدة)"
        lic.status = "active"
        lic.license_type = "lifetime"
        lic.valid_until = None
        lic.tamper_hash = compute_tamper_token(current_hwid, "active", "lifetime", "NONE")
        lic.last_clock_check = now
        lic.feature_multi_branch = True
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
        lic.save()
        self.stdout.write(self.style.SUCCESS("  [OK] License: Active Perpetual Lifetime (0 days countdown, ready for production)."))

        # -----------------------------------------------------------------
        # 5. Gym Profile
        # -----------------------------------------------------------------
        self.stdout.write("[5/6] Initializing Gym Profile...")
        profile = GymProfile.get_solo()
        profile.gym_name = gym_name
        profile.gym_tagline = "المنظومة الذكية المتكاملة لإدارة الصالات الرياضية"
        profile.primary_color = "#84CC16"      # Clean Emerald / Hulk Lime
        profile.secondary_color = "#121723"
        profile.tertiary_color = "#0B0E14"
        profile.accent_theme = "lime"
        profile.currency = "ج.م"
        profile.timezone = "Africa/Cairo"
        profile.trainers_page_password = "1234"
        profile.face_camera_enabled = True
        profile.whatsapp_enabled = True
        profile.save()
        self.stdout.write(self.style.SUCCESS(f"  [OK] Profile set: '{gym_name}' (Members: 0)."))

        # -----------------------------------------------------------------
        # 6. Standard Subscription Plans & Expense Categories
        # -----------------------------------------------------------------
        self.stdout.write("[6/6] Ensuring standard subscription plans and expense categories exist...")
        standard_plans = [
            ("اشتراك شهر كامل (Gym)", 30, Decimal("350.00"), False),
            ("اشتراك 3 أشهر (Quarterly)", 90, Decimal("900.00"), False),
            ("اشتراك 6 أشهر (Semi-Annual)", 180, Decimal("1600.00"), False),
            ("اشتراك سنة كاملة (VIP Annual)", 365, Decimal("2800.00"), False),
            ("باقة تدريب شخصي PT (12 جلسة)", 45, Decimal("1200.00"), True),
        ]
        for p_name, days, price, is_pt in standard_plans:
            Plan.objects.get_or_create(
                name=p_name,
                defaults={
                    "duration_days": days,
                    "price": price,
                    "is_pt": is_pt,
                    "is_active": True,
                },
            )

        standard_exp_cats = [
            ("إيجار الصالة الرياضية", True),
            ("فواتير الكهرباء والمياه والإنترنت", True),
            ("صيانة الأجهزة والمعدات الرياضية", False),
            ("أدوات نظافة ومستهلكات", False),
            ("بوفيه واستقبال وضيافة", False),
            ("سلف رواتب موظفين ومدربين", False),
            ("دعاية وإعلانات وتسويق", False),
        ]
        for c_name, is_fixed in standard_exp_cats:
            ExpenseCategory.objects.get_or_create(
                name=c_name,
                defaults={"is_fixed": is_fixed},
            )

        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.SUCCESS("  [SUCCESS] DATABASE HAS BEEN SUCCESSFULLY RESET TO A CLEAN SLATE!"))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
