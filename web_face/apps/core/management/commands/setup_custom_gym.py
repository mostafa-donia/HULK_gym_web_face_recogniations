import os
import shutil
import sys
from decimal import Decimal
from django.core.management import BaseCommand, call_command
from django.core.files import File
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

THEME_COLOR_MAP = {
    "lime": "#84CC16",
    "emerald": "#10B981",
    "blue": "#3B82F6",
    "orange": "#F97316",
    "red": "#EF4444",
    "purple": "#8B5CF6",
    "gold": "#EAB308",
    "monochrome": "#71717A",
}


class Command(BaseCommand):
    help = "Customizes gym branding (name, logo, theme) and initializes either clean or demo database."

    def add_arguments(self, parser):
        parser.add_argument("--name", type=str, default="", help="Gym name (optional)")
        parser.add_argument("--tagline", type=str, default="", help="Gym slogan/tagline")
        parser.add_argument("--logo", type=str, default="", help="Path to logo file on disk (png/jpg)")
        parser.add_argument("--theme", type=str, default="lime", help="Accent theme name (lime, emerald, blue, orange, red, purple, gold, monochrome)")
        parser.add_argument("--color", type=str, default="", help="Primary brand color hex")
        parser.add_argument("--branches", type=str, default="الفرع الرئيسي", help="Comma-separated list of branches")
        parser.add_argument("--currency", type=str, default="ج.م", help="Currency symbol")
        parser.add_argument("--phone", type=str, default="", help="Main phone / WhatsApp")
        parser.add_argument("--clear-data", action="store_true", help="Wipe all existing members and transactions")
        parser.add_argument("--seed-demo", action="store_true", help="Seed full demo dataset")

    def handle(self, *args, **options):
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        gym_name = options.get("name", "").strip() or "Systemize Gym"
        tagline = options.get("tagline", "").strip() or f"المنظومة الذكية لإدارة صالات {gym_name}"
        logo_path = options.get("logo", "").strip().strip('"').strip("'")
        raw_theme = options.get("theme", "lime").strip().lower()
        theme = raw_theme if raw_theme in THEME_COLOR_MAP else "lime"
        primary_color = options.get("color", "").strip() or THEME_COLOR_MAP.get(theme, "#84CC16")
        raw_branches = options.get("branches", "الفرع الرئيسي")
        currency = options.get("currency", "ج.م").strip()
        phone = options.get("phone", "").strip()
        clear_data = options.get("clear_data", False)
        seed_demo = options.get("seed_demo", False)

        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.MIGRATE_HEADING(f"      CONFIGURING GYM: {gym_name.upper()}         "))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))

        # 1. Database mode: Demo Seed vs. Clean Wipe
        if seed_demo:
            self.stdout.write("[1/6] Seeding comprehensive demo dataset...")
            try:
                call_command("seed_demo_data")
                self.stdout.write(self.style.SUCCESS("  [OK] Demo dataset seeded successfully."))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  [!] Note during demo seeding: {e}"))
        elif clear_data:
            self.stdout.write("[1/6] Purging dummy data for clean live start...")
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
            self.stdout.write(self.style.SUCCESS("  [OK] Clean wipe completed."))
        else:
            self.stdout.write("[1/6] Preserving existing records...")

        # 2. Branches configuration
        self.stdout.write("[2/6] Configuring gym branches...")
        branch_names = [b.strip() for b in raw_branches.split(",") if b.strip()]
        if not branch_names:
            branch_names = ["الفرع الرئيسي"]

        created_branches = []
        for idx, b_name in enumerate(branch_names, 1):
            code = f"BR-{idx:02d}"
            is_main = (idx == 1)
            branch, _ = Branch.objects.get_or_create(
                name=b_name,
                defaults={
                    "code": code,
                    "address": f"فرع {b_name} - مقر الصالة",
                    "phone": phone or "01000000000",
                    "manager_name": f"مدير {b_name}",
                    "is_main": is_main,
                    "is_active": True,
                }
            )
            if is_main and not branch.is_main:
                branch.is_main = True
                branch.save()
            created_branches.append(branch)
            self.stdout.write(self.style.SUCCESS(f"  [OK] Branch #{idx}: {branch.name} ({branch.code})"))

        main_branch = created_branches[0]

        # 3. GymProfile setup
        self.stdout.write("[3/6] Applying branding, colors and profile...")
        profile = GymProfile.get_solo()
        if gym_name:
            profile.gym_name = gym_name
        if tagline:
            profile.gym_tagline = tagline
        profile.accent_theme = theme
        profile.primary_color = primary_color
        profile.currency = currency
        if phone:
            profile.manager_mobile = phone

        # Copy logo if provided
        if logo_path and os.path.isfile(logo_path):
            try:
                ext = os.path.splitext(logo_path)[1].lower()
                clean_filename = f"gym_logo_{int(timezone.now().timestamp())}{ext}"
                with open(logo_path, "rb") as lf:
                    profile.logo.save(clean_filename, File(lf), save=False)
                self.stdout.write(self.style.SUCCESS(f"  [OK] Logo successfully attached from: {logo_path}"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  [!] Failed to copy logo: {e}"))
        elif logo_path:
            self.stdout.write(self.style.WARNING(f"  [!] Logo file not found at: {logo_path}"))

        profile.save()
        self.stdout.write(self.style.SUCCESS(f"  [OK] Profile saved: Name='{profile.gym_name}', Theme={theme}, Color={primary_color}"))

        # 4. Unlimited Multi-Branch Lifetime License
        self.stdout.write("[4/6] Registering full enterprise license...")
        license_obj, _ = SystemLicense.objects.get_or_create(id=1)
        license_obj.client_name = gym_name
        license_obj.status = "active"
        license_obj.license_type = "lifetime"
        license_obj.valid_until = timezone.now() + timedelta(days=365 * 50)
        license_obj.feature_face_recognition = True
        license_obj.feature_gate_relay = True
        license_obj.feature_whatsapp = True
        license_obj.feature_telegram = True
        license_obj.feature_bar = True
        license_obj.feature_payroll = True
        license_obj.feature_retention = True
        license_obj.feature_reports = True
        license_obj.feature_barcode = True
        license_obj.feature_expenses = True
        license_obj.feature_multi_branch = True
        license_obj.save()
        self.stdout.write(self.style.SUCCESS("  [OK] Enterprise Lifetime multi-branch license activated."))

        # 5. Core Users with standard 1234 passwords
        self.stdout.write("[5/6] Verifying user accounts...")
        accounts = [
            ("admin", UserRole.OWNER, "Admin", True),
            ("demo", UserRole.OWNER, "المالك العام", True),
            ("manager", UserRole.MANAGER, "مدير الصالة", False),
            ("reception", UserRole.RECEPTION, "موظف الاستقبال", False),
        ]
        for uname, role, fname, is_super in accounts:
            usr, created = User.objects.get_or_create(username=uname)
            usr.set_password("1234")
            usr.role = role
            usr.first_name = fname
            usr.branch = main_branch
            usr.is_staff = True
            usr.is_superuser = is_super
            usr.save()

        # 6. Core Categories & Payment Methods
        self.stdout.write("[6/6] Ensuring core payment methods and categories...")
        PaymentMethod.objects.get_or_create(name="نقدي (كاش)", defaults={"is_active": True})
        PaymentMethod.objects.get_or_create(name="محفظة إلكترونية / فودافون كاش", defaults={"is_active": True})
        PaymentMethod.objects.get_or_create(name="فيزا / بطاقة بنكية", defaults={"is_active": True})
        PaymentMethod.objects.get_or_create(name="إنستاباي / تحويل بنكي", defaults={"is_active": True})
        PaymentMethod.objects.get_or_create(name="آجل / على الحساب", defaults={"is_active": True})

        ExpenseCategory.objects.get_or_create(name="إيجار المقر", defaults={"is_active": True})
        ExpenseCategory.objects.get_or_create(name="فواتير كهرباء ومياه وانترنت", defaults={"is_active": True})
        ExpenseCategory.objects.get_or_create(name="صيانة ونظافة", defaults={"is_active": True})
        ExpenseCategory.objects.get_or_create(name="نثريات وضيافة", defaults={"is_active": True})

        self.stdout.write(self.style.SUCCESS("=================================================================="))
        self.stdout.write(self.style.SUCCESS(f"  🎉 SETUP COMPLETE FOR '{gym_name}'!"))
        self.stdout.write(self.style.SUCCESS("=================================================================="))
        self.stdout.write(f"  🏢 Branches ({len(branch_names)}): {', '.join(b.name for b in created_branches)}")
        self.stdout.write(f"  🎨 Theme: {theme} ({primary_color})")
        self.stdout.write(f"  👤 Login Accounts: admin / demo / manager / reception (All password: 1234)")
        self.stdout.write(self.style.SUCCESS("=================================================================="))
