import os
import shutil
import sys
from decimal import Decimal
from django.core.management.base import BaseCommand
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


class Command(BaseCommand):
    help = "Interactively sets up a custom branded gym with custom name, logo, theme colors, and branches."

    def add_arguments(self, parser):
        parser.add_argument("--name", type=str, required=True, help="Gym name")
        parser.add_argument("--tagline", type=str, default="", help="Gym slogan/tagline")
        parser.add_argument("--logo", type=str, default="", help="Path to logo file on disk (png/jpg)")
        parser.add_argument("--color", type=str, default="#84CC16", help="Primary brand color hex")
        parser.add_argument("--accent", type=str, default="", help="Secondary accent color hex")
        parser.add_argument("--branches", type=str, default="الفرع الرئيسي", help="Comma-separated list of branches")
        parser.add_argument("--currency", type=str, default="ج.م", help="Currency symbol")
        parser.add_argument("--phone", type=str, default="", help="Main phone / WhatsApp")
        parser.add_argument("--clear-data", action="store_true", help="Wipe all existing members and transactions")

    def handle(self, *args, **options):
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        gym_name = options["name"].strip()
        tagline = options.get("tagline", "").strip() or f"المنظومة الذكية لإدارة صالات {gym_name}"
        logo_path = options.get("logo", "").strip().strip('"').strip("'")
        primary_color = options.get("color", "").strip() or "#84CC16"
        accent_color = options.get("accent", "").strip() or primary_color
        raw_branches = options.get("branches", "الفرع الرئيسي")
        currency = options.get("currency", "ج.م").strip()
        phone = options.get("phone", "").strip()
        clear_data = options.get("clear_data", False)

        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.MIGRATE_HEADING(f"      SETTING UP CUSTOM GYM: {gym_name.upper()}         "))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))

        # 1. Clear data if requested
        if clear_data:
            self.stdout.write("[1/6] Purging old members and financial transactions...")
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
        profile, _ = GymProfile.objects.get_or_create(id=1)
        profile.gym_name = gym_name
        profile.tagline = tagline
        profile.primary_color = primary_color
        profile.accent_color = accent_color
        profile.currency = currency
        if phone:
            profile.phone = phone

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
        self.stdout.write(self.style.SUCCESS(f"  [OK] Profile saved: Name='{profile.gym_name}', Colors=({primary_color}, {accent_color})"))

        # 4. Unlimited Multi-Branch Lifetime License
        self.stdout.write("[4/6] Registering full enterprise license...")
        license_obj, _ = SystemLicense.objects.get_or_create(id=1)
        license_obj.client_name = gym_name
        license_obj.status = "ACTIVE"
        license_obj.license_type = "LIFETIME"
        license_obj.max_branches = max(10, len(branch_names) + 2)
        license_obj.max_members = 999999
        license_obj.valid_until = timezone.now().date() + timedelta(days=365 * 50)
        license_obj.support_until = timezone.now().date() + timedelta(days=365 * 10)
        license_obj.feature_face_recognition = True
        license_obj.feature_whatsapp = True
        license_obj.feature_multi_branch = True
        license_obj.feature_bar = True
        license_obj.feature_payroll = True
        license_obj.feature_financial_reports = True
        license_obj.feature_cloud_backup = True
        license_obj.feature_manager_face_bypass = True
        license_obj.save()
        self.stdout.write(self.style.SUCCESS("  [OK] Enterprise Lifetime multi-branch license activated."))

        # 5. Core Users with standard 1234 passwords
        self.stdout.write("[5/6] Verifying user accounts...")
        accounts = [
            ("admin", UserRole.OWNER, "Admin", True),
            ("demo", UserRole.OWNER, "المالك العام", True),
            ("manager", UserRole.MANAGER, "مدير الصالة", False),
            ("reception", UserRole.RECEPTIONIST, "موظف الاستقبال", False),
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
        PaymentMethod.objects.get_or_create(code="CASH", defaults={"name": "نقدي (كاش)", "is_active": True})
        PaymentMethod.objects.get_or_create(code="VODAFONE_CASH", defaults={"name": "محفظة إلكترونية / فودافون كاش", "is_active": True})
        PaymentMethod.objects.get_or_create(code="VISA", defaults={"name": "فيزا / بطاقة بنكية", "is_active": True})
        PaymentMethod.objects.get_or_create(code="DEFERRED", defaults={"name": "آجل / على الحساب", "is_active": True})

        BarProductCategory.objects.get_or_create(name="مشروبات وبروتينات", defaults={"is_active": True})
        BarProductCategory.objects.get_or_create(name="سناكس ومكملات", defaults={"is_active": True})

        ExpenseCategory.objects.get_or_create(name="إيجار المقر", defaults={"is_fixed": True})
        ExpenseCategory.objects.get_or_create(name="فواتير كهرباء ومياه وانترنت", defaults={"is_fixed": True})
        ExpenseCategory.objects.get_or_create(name="صيانة ونظافة", defaults={"is_fixed": False})
        ExpenseCategory.objects.get_or_create(name="نثريات وضيافة", defaults={"is_fixed": False})

        self.stdout.write(self.style.SUCCESS("=================================================================="))
        self.stdout.write(self.style.SUCCESS(f"  🎉 SETUP COMPLETE FOR '{gym_name}'!"))
        self.stdout.write(self.style.SUCCESS("=================================================================="))
        self.stdout.write(f"  🏢 Branches ({len(branch_names)}): {', '.join(b.name for b in created_branches)}")
        self.stdout.write(f"  🎨 Theme: Primary={primary_color}, Accent={accent_color}")
        self.stdout.write(f"  👤 Login Accounts: admin / demo / manager / reception (All password: 1234)")
        self.stdout.write(self.style.SUCCESS("=================================================================="))
