import sys
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.core.models import Branch, GymProfile, SystemLicense
from apps.members.models import Member, Subscription, CheckInEvent
from apps.payments.models import BarProduct, BarProductCategory, BarSale, Payment
from apps.payroll.models import Employee


class Command(BaseCommand):
    help = "Seeds Cina Spa demo data with Ruby Red theme, circular logo, and 3 branches (الفرع الرئيسي، النادي الصحي والاستشفاء، فرع السيدات)."

    def handle(self, *args, **options):
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.MIGRATE_HEADING("      CONFIGURING CINA SPA DEMO (RUBY RED THEME + SPA BRANCHES)   "))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))

        today = timezone.localdate()
        now = timezone.now()

        # -----------------------------------------------------------------
        # 1. Gym Profile & Ruby Red Branding
        # -----------------------------------------------------------------
        self.stdout.write("[1/6] Applying Cina Spa Branding & Theme...")
        profile = GymProfile.get_solo()
        profile.gym_name = "Cina Spa | جيم وسبا سينا"
        profile.gym_tagline = "CINA SPA - Gym and more.. For a better you"
        profile.logo = "branding/cina_spa_logo.png"
        profile.primary_color = "#991B1B"      # Rich Crimson / Ruby Red matching logo
        profile.secondary_color = "#18181B"    # Dark Zinc Card Surface
        profile.tertiary_color = "#09090B"     # Deep Obsidian Dark
        profile.accent_theme = "red"           # Power Red theme
        profile.currency = "ج.م"
        profile.timezone = "Africa/Cairo"
        profile.manager_mobile = "01080922432"
        profile.daily_report_time = "22:00"
        profile.trainers_page_password = "1234"
        profile.whatsapp_enabled = True
        profile.face_camera_enabled = True
        profile.save()
        self.stdout.write(self.style.SUCCESS(f"  [OK] Gym Profile set: {profile.gym_name} (Theme: Ruby Red #991B1B)"))

        # -----------------------------------------------------------------
        # 2. System License (Active Multi-Branch Lifetime License)
        # -----------------------------------------------------------------
        self.stdout.write("[2/6] Configuring Multi-Branch License...")
        from apps.core.licensing.hwid import get_hardware_fingerprint
        from apps.core.licensing.crypto import compute_tamper_token

        current_hwid = get_hardware_fingerprint()
        lic = SystemLicense.objects.first()
        if not lic:
            lic = SystemLicense(machine_id=current_hwid)
        else:
            lic.machine_id = current_hwid

        lic.client_name = "Cina Spa - جيم وسبا سينا"
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
        self.stdout.write(self.style.SUCCESS(f"  [OK] License: Active Multi-Branch Lifetime (HWID: {current_hwid})"))

        # -----------------------------------------------------------------
        # 3. Setup the 3 Branches
        # -----------------------------------------------------------------
        self.stdout.write("[3/6] Setting up the 3 Cina Spa Branches...")
        existing_branches = list(Branch.objects.all().order_by("id"))

        # Branch 1: الفرع الرئيسي
        if len(existing_branches) >= 1:
            b1 = existing_branches[0]
            b1.code = "BR-CINA-MAIN"
            b1.name = "فرع سينا سبا الرئيسي"
            b1.address = "المجمع الرياضي والصحي الرئيسي"
            b1.phone = "01099887766"
            b1.manager_name = "إدارة سينا سبا"
            b1.is_main = True
            b1.is_active = True
            b1.save()
        else:
            b1 = Branch.objects.create(
                code="BR-CINA-MAIN",
                name="فرع سينا سبا الرئيسي",
                address="المجمع الرياضي والصحي الرئيسي",
                phone="01099887766",
                manager_name="إدارة سينا سبا",
                is_main=True,
                is_active=True,
            )

        # Branch 2: النادي الصحي والاستشفاء
        if len(existing_branches) >= 2:
            b2 = existing_branches[1]
            b2.code = "BR-WELLNESS"
            b2.name = "فرع النادي الصحي والاستشفاء"
            b2.address = "مجمع الساونا والجاكوزي والمساج"
            b2.phone = "01088776655"
            b2.manager_name = "دكتور أحمد كمال (أخصائي تأهيل)"
            b2.is_main = False
            b2.is_active = True
            b2.save()
        else:
            b2 = Branch.objects.create(
                code="BR-WELLNESS",
                name="فرع النادي الصحي والاستشفاء",
                address="مجمع الساونا والجاكوزي والمساج",
                phone="01088776655",
                manager_name="دكتور أحمد كمال (أخصائي تأهيل)",
                is_main=False,
                is_active=True,
            )

        # Branch 3: فرع السيدات الخاص
        if len(existing_branches) >= 3:
            b3 = existing_branches[2]
            b3.code = "BR-LADIES"
            b3.name = "فرع السيدات الخاص (Ladies Only)"
            b3.address = "جناح السيدات والرشاقة"
            b3.phone = "01077665544"
            b3.manager_name = "كابتن سارة علي"
            b3.is_main = False
            b3.is_active = True
            b3.save()
        else:
            b3 = Branch.objects.create(
                code="BR-LADIES",
                name="فرع السيدات الخاص (Ladies Only)",
                address="جناح السيدات والرشاقة",
                phone="01077665544",
                manager_name="كابتن سارة علي",
                is_main=False,
                is_active=True,
            )

        branches = [b1, b2, b3]
        self.stdout.write(self.style.SUCCESS(f"  [OK] 3 Branches Ready: {b1.name}, {b2.name}, {b3.name}"))

        # -----------------------------------------------------------------
        # 4. Distribute Members & Subscriptions across the 3 branches
        # -----------------------------------------------------------------
        self.stdout.write("[4/6] Rebalancing members across branches...")
        members = list(Member.objects.all())
        m_count = len(members)
        if m_count > 0:
            for idx, m in enumerate(members):
                target_branch = branches[idx % 3]
                if m.branch != target_branch:
                    m.branch = target_branch
                    m.save(update_fields=["branch"])
            self.stdout.write(self.style.SUCCESS(f"  [OK] {m_count} Members distributed across the 3 branches."))
        else:
            self.stdout.write("  [i] No existing members to distribute.")

        # -----------------------------------------------------------------
        # 5. Seed Branch-Specific Spa & Bar Products & Stock
        # -----------------------------------------------------------------
        self.stdout.write("[5/6] Seeding Spa & Bar Products and Stock for each branch...")
        catalog = [
            ("مياه معدنية نقية 600 مل", BarProductCategory.DRINKS, Decimal("10.00"), Decimal("5.00"), 50, 10),
            ("ديتوكس جرين جوس طبيعي (Green Detox)", BarProductCategory.DRINKS, Decimal("40.00"), Decimal("22.00"), 30, 8),
            ("سكوب واي بروتين معزول فانيليا/فراولة", BarProductCategory.SUPPLEMENTS, Decimal("70.00"), Decimal("40.00"), 35, 10),
            ("جلسة ساونا وجاكوزي VIP", BarProductCategory.OTHER, Decimal("150.00"), Decimal("50.00"), 100, 5),
            ("مساج استشفائي علاجي 45 دقيقة", BarProductCategory.OTHER, Decimal("250.00"), Decimal("100.00"), 50, 5),
            ("بروتين بار كيتو شوكولاتة وتوت 60 جم", BarProductCategory.SNACKS, Decimal("50.00"), Decimal("28.00"), 25, 6),
            ("منشفة سينا سبا الفاخرة القطنية", BarProductCategory.OTHER, Decimal("90.00"), Decimal("45.00"), 40, 8),
        ]

        total_prods = 0
        for br in branches:
            for name, cat, price, cost, stock, min_alert in catalog:
                prod, created = BarProduct.objects.get_or_create(
                    name=name,
                    branch=br,
                    defaults={
                        "category": cat,
                        "price": price,
                        "cost_price": cost,
                        "stock_quantity": stock,
                        "min_stock_alert": min_alert,
                        "is_active": True,
                    },
                )
                if not created:
                    prod.price = price
                    prod.cost_price = cost
                    prod.category = cat
                    prod.is_active = True
                    prod.save()
                total_prods += 1

        self.stdout.write(self.style.SUCCESS(f"  [OK] {total_prods} Spa & Bar products ready across all branches."))

        # -----------------------------------------------------------------
        # 6. Seed Sample Branch Bar Sales
        # -----------------------------------------------------------------
        self.stdout.write("[6/6] Seeding sample Spa Bar sales per branch...")
        for br in branches:
            p_water = BarProduct.objects.filter(branch=br, name__icontains="مياه").first()
            first_m = Member.objects.filter(branch=br).first()
            if p_water and first_m:
                sale_id_paid = f"SPA-{br.code}-P1"
                BarSale.objects.get_or_create(
                    sale_id=sale_id_paid,
                    defaults={
                        "product": p_water,
                        "branch": br,
                        "member": first_m,
                        "buyer_name": first_m.name,
                        "buyer_phone": first_m.mobile,
                        "quantity": 2,
                        "unit_price": p_water.price,
                        "total_price": p_water.price * 2,
                        "is_paid": True,
                        "paid_at": now,
                        "payment_method": "كاش نقدي (Cash)",
                    },
                )

        self.stdout.write(self.style.SUCCESS("  [OK] Spa Sales configured with branch isolation."))

        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.SUCCESS("  [SUCCESS] CINA SPA DEMO CONFIGURATION APPLIED PERFECTLY!"))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(f"Gym Name     : {profile.gym_name}")
        self.stdout.write(f"Theme Colors : Primary={profile.primary_color} (Ruby Red) | Accent=red")
        self.stdout.write(f"Logo Path    : {profile.logo}")
        self.stdout.write("Branches:")
        for b in branches:
            self.stdout.write(f"  - [{b.code}] {b.name}")
