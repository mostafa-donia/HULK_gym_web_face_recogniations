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
    help = "Seeds Number One Gym demo data with Gold Yellow theme, logo, and 3 branches (شكري القوتلي، الزراعة، الشعبية)."

    def handle(self, *args, **options):
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.MIGRATE_HEADING("   CONFIGURING NUMBER ONE GYM DEMO (GOLD YELLOW + 3 BRANCHES)    "))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))

        today = timezone.localdate()
        now = timezone.now()

        # -----------------------------------------------------------------
        # 1. Gym Profile & Gold Yellow Branding
        # -----------------------------------------------------------------
        self.stdout.write("[1/6] Applying Number One Gym Branding & Theme...")
        profile = GymProfile.get_solo()
        profile.gym_name = "Number One Gym | صالات نمبر وان"
        profile.gym_tagline = "NUMBER ONE LIGHT - صالات نمبر وان الرياضية المتكاملة"
        profile.logo = "branding/number_one_logo.png"
        profile.primary_color = "#FFD700"      # Bright Iconic Gold Yellow matching logo
        profile.secondary_color = "#161B26"    # Dark Surface / Card
        profile.tertiary_color = "#0B0E14"     # Deep Background (Obsidian Black)
        profile.accent_theme = "gold"          # Royal Gold theme
        profile.currency = "ج.م"
        profile.timezone = "Africa/Cairo"
        profile.manager_mobile = "01080922432"
        profile.daily_report_time = "22:00"
        profile.trainers_page_password = "1234"
        profile.whatsapp_enabled = True
        profile.face_camera_enabled = True
        profile.save()
        self.stdout.write(self.style.SUCCESS(f"  [OK] Gym Profile set: {profile.gym_name} (Theme: Gold Yellow #FFD700)"))

        # -----------------------------------------------------------------
        # 2. System License (Valid Hardware Bound Demo)
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

        lic.client_name = "Number One Gym - صالات نمبر وان"
        lic.status = "demo"
        lic.license_type = "demo"
        lic.valid_until = now + timedelta(days=365)
        lic.tamper_hash = compute_tamper_token(current_hwid, "demo", "demo", lic.valid_until)
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
        self.stdout.write(self.style.SUCCESS(f"  [OK] License: Active Multi-Branch Demo (HWID: {current_hwid})"))

        # -----------------------------------------------------------------
        # 3. Setup the 3 Branches (شكري القوتلي، الزراعة، الشعبية)
        # -----------------------------------------------------------------
        self.stdout.write("[3/6] Setting up the 3 Branches (شكري القوتلي، الزراعة، الشعبية)...")
        existing_branches = list(Branch.objects.all().order_by("id"))

        # Branch 1: شكري القوتلي (Main)
        if len(existing_branches) >= 1:
            b1 = existing_branches[0]
            b1.code = "BR-QOWATLY"
            b1.name = "فرع شكري القوتلي"
            b1.address = "شارع شكري القوتلي الرئيسي"
            b1.phone = "01011223344"
            b1.manager_name = "كابتن أحمد العوضي"
            b1.is_main = True
            b1.is_active = True
            b1.save()
        else:
            b1 = Branch.objects.create(
                code="BR-QOWATLY",
                name="فرع شكري القوتلي",
                address="شارع شكري القوتلي الرئيسي",
                phone="01011223344",
                manager_name="كابتن أحمد العوضي",
                is_main=True,
                is_active=True,
            )

        # Branch 2: الزراعة
        if len(existing_branches) >= 2:
            b2 = existing_branches[1]
            b2.code = "BR-ZARAA"
            b2.name = "فرع الزراعة"
            b2.address = "ميدان الزراعة"
            b2.phone = "01022334455"
            b2.manager_name = "كابتن محمود نصر"
            b2.is_main = False
            b2.is_active = True
            b2.save()
        else:
            b2 = Branch.objects.create(
                code="BR-ZARAA",
                name="فرع الزراعة",
                address="ميدان الزراعة",
                phone="01022334455",
                manager_name="كابتن محمود نصر",
                is_main=False,
                is_active=True,
            )

        # Branch 3: الشعبية
        if len(existing_branches) >= 3:
            b3 = existing_branches[2]
            b3.code = "BR-SHAABIA"
            b3.name = "فرع الشعبية"
            b3.address = "حي الشعبية"
            b3.phone = "01033445566"
            b3.manager_name = "كابتن تامر حسني"
            b3.is_main = False
            b3.is_active = True
            b3.save()
        else:
            b3 = Branch.objects.create(
                code="BR-SHAABIA",
                name="فرع الشعبية",
                address="حي الشعبية",
                phone="01033445566",
                manager_name="كابتن تامر حسني",
                is_main=False,
                is_active=True,
            )

        branches = [b1, b2, b3]
        self.stdout.write(self.style.SUCCESS(f"  [OK] 3 Branches Ready: {b1.name}, {b2.name}, {b3.name}"))

        # -----------------------------------------------------------------
        # 4. Distribute Members & Subscriptions across the 3 branches
        # -----------------------------------------------------------------
        self.stdout.write("[4/6] Rebalancing and verifying members across branches...")
        members = list(Member.objects.all())
        m_count = len(members)
        if m_count > 0:
            for idx, m in enumerate(members):
                target_branch = branches[idx % 3]
                if m.branch != target_branch:
                    m.branch = target_branch
                    m.save(update_fields=["branch"])
            self.stdout.write(self.style.SUCCESS(f"  [OK] {m_count} Members distributed evenly across the 3 branches."))
        else:
            self.stdout.write("  [i] No existing members to distribute.")

        # -----------------------------------------------------------------
        # 5. Seed Branch-Specific Bar Products & Stock
        # -----------------------------------------------------------------
        self.stdout.write("[5/6] Seeding Bar Products and Stock for each branch...")
        catalog = [
            ("مياه معدنية طبيعية 600 مل", BarProductCategory.DRINKS, Decimal("10.00"), Decimal("5.00"), 48, 10),
            ("مشروب طاقة ريد بول أوريجينال", BarProductCategory.DRINKS, Decimal("45.00"), Decimal("30.00"), 24, 6),
            ("سكوب واي بروتين جولد ستاندرد", BarProductCategory.SUPPLEMENTS, Decimal("65.00"), Decimal("38.00"), 30, 8),
            ("سكوب كرياتين مونوهيدرات ميكرونيزد", BarProductCategory.SUPPLEMENTS, Decimal("35.00"), Decimal("18.00"), 8, 10),
            ("بروتين بار شوكولاتة كيتو 60 جم", BarProductCategory.SNACKS, Decimal("45.00"), Decimal("26.00"), 20, 5),
            ("شيكر نمبر وان بريميوم 700 مل", BarProductCategory.OTHER, Decimal("120.00"), Decimal("70.00"), 15, 4),
        ]

        total_prods = 0
        for br in branches:
            for name, cat, price, cost, stock, min_alert in catalog:
                prod, _ = BarProduct.objects.get_or_create(
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
                prod.price = price
                prod.cost_price = cost
                prod.stock_quantity = stock
                prod.min_stock_alert = min_alert
                prod.branch = br
                prod.save()
                total_prods += 1

            # Seed a sample paid sale and an unpaid deferred sale for each branch
            p_water = BarProduct.objects.filter(branch=br, name__contains="مياه").first()
            p_redbull = BarProduct.objects.filter(branch=br, name__contains="ريد بول").first()
            first_m = Member.objects.filter(branch=br).first()

            if p_water and first_m:
                sale_id_paid = f"BAR-{br.code}-P1"
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

            if p_redbull and first_m:
                sale_id_unpaid = f"BAR-{br.code}-U1"
                BarSale.objects.get_or_create(
                    sale_id=sale_id_unpaid,
                    defaults={
                        "product": p_redbull,
                        "branch": br,
                        "member": first_m,
                        "buyer_name": first_m.name,
                        "buyer_phone": first_m.mobile,
                        "quantity": 1,
                        "unit_price": p_redbull.price,
                        "total_price": p_redbull.price,
                        "is_paid": False,
                        "payment_method": "نقدي (آجل)",
                        "notes": "آجل - هيدفع بعد التمرين",
                    },
                )

        self.stdout.write(self.style.SUCCESS(f"  [OK] {total_prods} Bar Products configured with branch isolation."))

        # -----------------------------------------------------------------
        # 6. Summary Output
        # -----------------------------------------------------------------
        self.stdout.write(self.style.SUCCESS("\n=================================================================="))
        self.stdout.write(self.style.SUCCESS("   NUMBER ONE GYM SETUP COMPLETED SUCCESSFULLY!                   "))
        self.stdout.write(self.style.SUCCESS("=================================================================="))
        self.stdout.write(f"Gym Name     : {profile.gym_name}")
        self.stdout.write(f"Theme Colors : Primary={profile.primary_color} (Gold Yellow) | Accent=gold")
        self.stdout.write(f"Logo Path    : {profile.logo}")
        self.stdout.write("Branches:")
        for b in branches:
            m_cnt = Member.objects.filter(branch=b).count()
            self.stdout.write(f"  • [{b.code}] {b.name} ({b.address}) -> {m_cnt} أعضاء")
        self.stdout.write("==================================================================\n")
