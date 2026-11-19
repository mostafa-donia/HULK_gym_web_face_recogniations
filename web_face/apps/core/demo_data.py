"""
Temporal Big Data Generator for Systemize Gym OS.
Populates realistic, comprehensive datasets cleanly distributed across:
- Today (This Day)
- This Week
- This Month
- Previous Month (for comparative analytics)
"""
import random
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone


def seed_temporal_big_data():
    from apps.accounts.models import User, UserRole
    from apps.core.models import Branch, GymProfile, SystemLicense, AuditLog
    from apps.members.models import Member, MemberStatus, Plan, Subscription, CheckInEvent
    from apps.payments.models import (
        Payment,
        PaymentMethod,
        PaymentOperationType,
        BarProduct,
        BarProductCategory,
        BarSale,
    )
    from apps.expenses.models import Expense, ExpenseCategory
    from apps.payroll.models import (
        Employee,
        EmployeeRole,
        EmployeeStatus,
        SalaryAdjustment,
        AdjustmentType,
        AdjustmentStatus,
        TrainerClientAssignment,
    )
    from apps.messaging.models import WhatsAppMessage, MessageStatus, MessageType

    today = timezone.localdate()
    now = timezone.now()
    month_start = today.replace(day=1)

    # 1. Gym Profile & Branding
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
    profile.face_camera_enabled = True
    profile.face_match_threshold = 65.0
    profile.gate_relay_enabled = True
    profile.whatsapp_enabled = True
    profile.trainers_page_password = "1234"
    profile.save()

    # 2. System License
    lic = SystemLicense.objects.first()
    if not lic:
        lic = SystemLicense.objects.create(
            machine_id="SYSTEMIZE-MACHINE-PRO-001",
            client_name="Systemize Fitness Club",
        )
    lic.status = "active"
    lic.license_type = "lifetime"
    lic.valid_until = None
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
    lic.save()

    # 3. Branches
    b_main, _ = Branch.objects.get_or_create(
        code="BR-MAIN",
        defaults={
            "name": "الفرع الرئيسي",
            "address": "شارع النصر، المعادي، القاهرة",
            "phone": "01080922432",
            "is_main": True,
            "is_active": True,
        },
    )
    b_main.is_main = True
    b_main.save()

    b_nasr, _ = Branch.objects.get_or_create(
        code="BR-NASR",
        defaults={
            "name": "فرع مدينة نصر",
            "address": "شارع عباس العقاد، مدينة نصر",
            "phone": "01011223344",
            "is_main": False,
            "is_active": True,
        },
    )

    branches = [b_main, b_nasr]

    # 4. Standard User Accounts
    u_manager, _ = User.objects.get_or_create(username="manager")
    u_manager.role = UserRole.OWNER
    u_manager.branch = b_main
    u_manager.is_staff = True
    u_manager.is_superuser = True
    u_manager.first_name = "مدير"
    u_manager.last_name = "الصالة"
    u_manager.set_password("1234")
    u_manager.save()

    u_reception, _ = User.objects.get_or_create(username="reception")
    u_reception.role = UserRole.RECEPTION
    u_reception.branch = b_main
    u_reception.is_staff = False
    u_reception.is_superuser = False
    u_reception.first_name = "موظف"
    u_reception.last_name = "الاستقبال"
    u_reception.set_password("1234")
    u_reception.save()

    u_admin, _ = User.objects.get_or_create(username="admin")
    u_admin.role = UserRole.OWNER
    u_admin.is_staff = True
    u_admin.is_superuser = True
    u_admin.set_password("1234")
    u_admin.save()

    # 5. Payment Methods
    pm_cash, _ = PaymentMethod.objects.get_or_create(name="كاش نقدي (Cash)", defaults={"is_active": True})
    pm_insta, _ = PaymentMethod.objects.get_or_create(name="إنستاباي / فودافون كاش (InstaPay)", defaults={"is_active": True})
    pm_card, _ = PaymentMethod.objects.get_or_create(name="فيزا / ماستركارد (POS Card)", defaults={"is_active": True})
    payment_methods = [pm_cash, pm_insta, pm_card]

    # 6. Subscription Plans
    plans_data = [
        {"name": "شهر شامل حديد ولياقة", "price": Decimal("450.00"), "duration_days": 30, "months": 1, "frequency": "كل يوم"},
        {"name": "شهر يوم ويوم (تمرين 4 ساعات)", "price": Decimal("350.00"), "duration_days": 30, "months": 1, "frequency": "يوم ويوم"},
        {"name": "3 شهور شامل سبا ومسبح", "price": Decimal("1200.00"), "duration_days": 90, "months": 3, "frequency": "كل يوم"},
        {"name": "6 شهور بلاتينيوم VIP", "price": Decimal("2200.00"), "duration_days": 180, "months": 6, "frequency": "كل يوم"},
        {"name": "سنوي VIP الذهبي", "price": Decimal("4000.00"), "duration_days": 365, "months": 12, "frequency": "كل يوم"},
        {"name": "باقة الملاكمة والكروس فيت", "price": Decimal("600.00"), "duration_days": 30, "months": 1, "frequency": "3 أيام بالأسبوع"},
        {"name": "حصة تدريبية (Day Use)", "price": Decimal("80.00"), "duration_days": 1, "months": 0, "frequency": "يوم واحد"},
    ]
    plans = {}
    for pd in plans_data:
        p_obj, _ = Plan.objects.get_or_create(name=pd["name"], defaults=pd)
        p_obj.price = pd["price"]
        p_obj.duration_days = pd["duration_days"]
        p_obj.months = pd["months"]
        p_obj.frequency = pd["frequency"]
        p_obj.is_active = True
        p_obj.save()
        plans[pd["name"]] = p_obj

    # 7. Staff & Coaches
    staff_data = [
        ("كابتن إسلام عادل", "01011112222", EmployeeRole.TRAINER, Decimal("6500.00"), Decimal("50.00")),
        ("كابتن أحمد شريف", "01033334444", EmployeeRole.TRAINER, Decimal("5800.00"), Decimal("50.00")),
        ("كابتن سارة محمود", "01055556666", EmployeeRole.TRAINER, Decimal("5200.00"), Decimal("45.00")),
        ("كريم سامي", "01077778888", EmployeeRole.ASSISTANT, Decimal("4500.00"), Decimal("0.00")),
    ]
    coaches = []
    for name, phone, role, salary, comm in staff_data:
        emp, _ = Employee.objects.get_or_create(name=name, defaults={"phone": phone, "role": role})
        emp.phone = phone
        emp.role = role
        emp.status = EmployeeStatus.ACTIVE
        emp.fixed_salary = salary
        emp.commission_percentage = comm
        emp.hire_date = date(2025, 1, 1)
        emp.save()
        if role == EmployeeRole.TRAINER:
            coaches.append(emp)

    # 8. Expense Categories & Expenses
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

    Expense.objects.all().delete()

    # Expenses across time buckets:
    # A) Today
    Expense.objects.create(
        category=cat_objs["نظافة ومستلزمات تعقيم"],
        amount=Decimal("280.00"),
        expense_date=today,
        branch=b_main,
        description="شراء مطهرات ومعقمات أرضيات كاونتر الاستقبال اليومية",
        created_by=u_reception,
    )
    Expense.objects.create(
        category=cat_objs["بوفيه واستقبال وضيافة"],
        amount=Decimal("220.00"),
        expense_date=today,
        branch=b_main,
        description="مشروبات وضيافة كبار الزوار والأعضاء",
        created_by=u_reception,
    )

    # B) This Week (days 1 to 6 ago)
    Expense.objects.create(
        category=cat_objs["صيانة الأجهزة والمعدات"],
        amount=Decimal("1450.00"),
        expense_date=today - timedelta(days=2),
        branch=b_main,
        description="تغيير سيور مشايات وتزييت وايرات الكابل كروس",
        created_by=u_manager,
    )
    Expense.objects.create(
        category=cat_objs["نظافة ومستلزمات تعقيم"],
        amount=Decimal("850.00"),
        expense_date=today - timedelta(days=4),
        branch=b_main,
        description="شراء كراتين مناديل ومستلزمات نظافة دورات المياه والساونا",
        created_by=u_reception,
    )

    # C) Earlier This Month (days 7 to 18 ago)
    Expense.objects.create(
        category=cat_objs["إيجار المقر والفرع"],
        amount=Decimal("22000.00"),
        expense_date=month_start,
        branch=b_main,
        description="إيجار مقر الفرع الرئيسي لشهر نوفمبر الجاري",
        created_by=u_manager,
    )
    Expense.objects.create(
        category=cat_objs["فواتير الكهرباء والمياه"],
        amount=Decimal("3850.00"),
        expense_date=today - timedelta(days=8),
        branch=b_main,
        description="فاتورة استهلاك كهرباء التكييف المركزي والإنارة",
        created_by=u_manager,
    )
    Expense.objects.create(
        category=cat_objs["تسويق وإعلانات سبونسر"],
        amount=Decimal("3200.00"),
        expense_date=today - timedelta(days=11),
        branch=b_main,
        description="حملة إعلانات ممولة فيسبوك وإنستجرام لعروض الشتاء",
        created_by=u_manager,
    )
    Expense.objects.create(
        category=cat_objs["فواتير الكهرباء والمياه"],
        amount=Decimal("950.00"),
        expense_date=today - timedelta(days=14),
        branch=b_main,
        description="فاتورة مياه الفرع الرئيسي",
        created_by=u_manager,
    )

    # 9. Bar Products & Bar Sales
    prods_data = [
        ("مياه معدنية 600 مل", BarProductCategory.DRINKS, Decimal("10.00"), Decimal("5.00"), 60),
        ("ريد بول كلاسيك 250 مل", BarProductCategory.DRINKS, Decimal("55.00"), Decimal("38.00"), 24),
        ("سكوب واي بروتين جولد", BarProductCategory.SUPPLEMENTS, Decimal("65.00"), Decimal("38.00"), 35),
        ("سكوب كرياتين مونوهيدرات", BarProductCategory.SUPPLEMENTS, Decimal("35.00"), Decimal("18.00"), 20),
        ("بروتين بار كيتو شوكولاتة", BarProductCategory.SNACKS, Decimal("45.00"), Decimal("25.00"), 30),
        ("إسبريسو دبل شوت", BarProductCategory.DRINKS, Decimal("30.00"), Decimal("12.00"), 100),
    ]
    bar_products = []
    for name, cat, price, cost, stock in prods_data:
        bp, _ = BarProduct.objects.get_or_create(
            name=name,
            defaults={"category": cat, "price": price, "cost_price": cost, "stock_quantity": stock, "is_active": True}
        )
        bp.price = price
        bp.stock_quantity = stock
        bp.is_active = True
        bp.save()
        bar_products.append(bp)

    BarSale.objects.all().delete()

    # Bar Sales across time:
    # A) Today: 3 paid + 3 unpaid tabs
    today_bar_sales = [
        (bar_products[0], 2, Decimal("20.00"), True, "كاش نقدي (Cash)", "أحمد حسام الدين", "01001234567"),
        (bar_products[1], 1, Decimal("55.00"), True, "إنستاباي / فودافون كاش (InstaPay)", "كريم عادل مصطفى", "01011112223"),
        (bar_products[5], 2, Decimal("60.00"), True, "كاش نقدي (Cash)", "يوسف مصطفى كمال", "01233334441"),
        (bar_products[2], 1, Decimal("65.00"), False, "آجل - معلق", "محمود عبد العزيز الشناوي", "01012345678"),
        (bar_products[1], 1, Decimal("55.00"), False, "آجل - معلق", "طارق يحيى العطار", "01122223332"),
        (bar_products[4], 1, Decimal("45.00"), False, "آجل - معلق", "خالد وليد الجوهري", "01544445552"),
    ]
    for idx, (p, qty, tot, is_p, meth, buyer, b_phone) in enumerate(today_bar_sales, start=1):
        bs = BarSale.objects.create(
            sale_id=f"BAR-{today.strftime('%y%m%d')}-{idx:03d}",
            product=p,
            quantity=qty,
            unit_price=p.price,
            total_price=tot,
            buyer_name=buyer,
            buyer_phone=b_phone,
            is_paid=is_p,
            payment_method=meth if is_p else "",
            branch=b_main,
            notes="طلب بار اليوم" if is_p else "حساب معلق لم يسدد",
            created_by=u_reception,
            paid_at=now if is_p else None,
        )
        BarSale.objects.filter(id=bs.id).update(created_at=now - timedelta(hours=idx))

    # B) This Week (days 1 to 6 ago)
    for w_i in range(1, 7):
        past_dt = now - timedelta(days=w_i, hours=w_i * 2)
        bs = BarSale.objects.create(
            sale_id=f"BAR-{past_dt.strftime('%y%m%d')}-01{w_i}",
            product=bar_products[w_i % len(bar_products)],
            quantity=random.choice([1, 2]),
            unit_price=bar_products[w_i % len(bar_products)].price,
            total_price=bar_products[w_i % len(bar_products)].price * random.choice([1, 2]),
            buyer_name=f"مشترك فرع المعادي #{w_i}",
            buyer_phone="0100000000" + str(w_i),
            is_paid=True,
            payment_method="كاش نقدي (Cash)",
            branch=b_main,
            created_by=u_reception,
            paid_at=past_dt,
        )
        BarSale.objects.filter(id=bs.id).update(created_at=past_dt)

    # 10. Members, Subscriptions, Payments & Check-Ins
    CheckInEvent.objects.all().delete()
    Payment.objects.all().delete()
    Subscription.objects.all().delete()
    Member.objects.all().delete()

    # Raw member directory roster
    member_roster = [
        # (ID, Name, Mobile, Gender, Status, EndDeltaDays, PlanKey, Debt, HasPrivate, CoachIdx, Notes)
        # Active Members (Healthy dates in future)
        ("MEM-1001", "أحمد حسام الدين الشناوي", "01001234567", "male", MemberStatus.ACTIVE, 75, "سنوي VIP الذهبي", 0, False, None, "مشترك VIP سنوي ملتزم"),
        ("MEM-1002", "محمود عبد العزيز قنديل", "01012345678", "male", MemberStatus.ACTIVE, 2, "شهر شامل حديد ولياقة", 150, False, None, "ينتهي بعد يومين وعليه متبقي 150 ج"),
        ("MEM-1003", "طارق السعيد مصطفى", "01023456789", "male", MemberStatus.ACTIVE, 1, "شهر شامل حديد ولياقة", 0, False, None, "ينتهي غداً (حرج)"),
        ("MEM-1004", "خالد إبراهيم النجار", "01034567890", "male", MemberStatus.EXPIRED, -6, "شهر شامل حديد ولياقة", 0, False, None, "منتهي منذ 6 أيام"),
        ("MEM-1005", "عمر فاروق الشريف", "01045678901", "male", MemberStatus.ACTIVE, 45, "3 شهور شامل سبا ومسبح", 500, False, None, "عليه متبقي 500 ج"),
        ("MEM-1006", "ياسر كمال المنشاوي", "01056789012", "male", MemberStatus.ACTIVE, 18, "شهر يوم ويوم (تمرين 4 ساعات)", 0, False, None, "باقة يوم ويوم"),
        ("MEM-1007", "محمد سامي رضوان", "01067890123", "male", MemberStatus.ACTIVE, 25, "شهر شامل حديد ولياقة", 0, True, 0, "تدريب خاص مع كابتن إسلام"),
        ("MEM-1008", "ياسمين عادل زهران", "01078901234", "female", MemberStatus.ACTIVE, 60, "3 شهور شامل سبا ومسبح", 0, False, None, "سيدات - سبا"),
        ("MEM-1009", "كريم مجدي الصاوي", "01089012345", "male", MemberStatus.ACTIVE, 20, "باقة الملاكمة والكروس فيت", 200, True, 1, "كروس فيت مع كابتن أحمد"),
        ("MEM-1010", "سارة إبراهيم فتحي", "01122223331", "female", MemberStatus.ACTIVE, 40, "شهر شامل حديد ولياقة", 0, False, None, "لياقة وبناء أجسام"),
        ("MEM-1011", "طارق يحيى العطار", "01122223332", "male", MemberStatus.ACTIVE, 3, "شهر شامل حديد ولياقة", 250, False, None, "ينتهي خلال 3 أيام وعليه 250 ج"),
        ("MEM-1012", "يوسف مصطفى كمال", "01233334441", "male", MemberStatus.ACTIVE, 85, "3 شهور شامل سبا ومسبح", 0, False, None, "ملتزم بحضور منتظم"),
        ("MEM-1013", "نور الدين عمر حامد", "01233334442", "male", MemberStatus.ACTIVE, 15, "شهر شامل حديد ولياقة", 0, False, None, "مشترك نشط"),
        ("MEM-1014", "عمر الفاروق إبراهيم", "01544445551", "male", MemberStatus.ACTIVE, 2, "شهر شامل حديد ولياقة", 0, False, None, "ينتهي بعد 48 ساعة"),
        ("MEM-1015", "خالد وليد الجوهري", "01544445552", "male", MemberStatus.ACTIVE, 1, "شهر شامل حديد ولياقة", 200, False, None, "ينتهي غداً وعليه 200 ج"),
        ("MEM-1016", "مروان عطية السيد", "01055556661", "male", MemberStatus.ACTIVE, 3, "شهر شامل حديد ولياقة", 0, False, None, "ينتهي بعد 3 أيام"),
        ("MEM-1017", "محمد صلاح رجب", "01055556662", "male", MemberStatus.EXPIRED, -12, "شهر شامل حديد ولياقة", 350, False, None, "منتهي وعليه متبقي 350 ج"),
        ("MEM-1018", "عمرو السولية فوزي", "01166667771", "male", MemberStatus.EXPIRED, -8, "شهر شامل حديد ولياقة", 0, False, None, "منتهي هذا الأسبوع"),
        ("MEM-1019", "علي معلول شكري", "01166667772", "male", MemberStatus.EXPIRED, -15, "شهر شامل حديد ولياقة", 500, False, None, "منتهي وعليه دين 500 ج"),
        ("MEM-1020", "حسين الشحات علي", "01277778881", "male", MemberStatus.EXPIRED, -25, "شهر شامل حديد ولياقة", 0, False, None, "منتهي الشهر الماضي"),
        ("MEM-1021", "إمام عاشور متولي", "01277778882", "male", MemberStatus.EXPIRED, -35, "3 شهور شامل سبا ومسبح", 0, False, None, "منتهي غير مجدد"),
        ("MEM-1022", "مصطفى محمد زكي", "01099991111", "male", MemberStatus.ACTIVE, 110, "6 شهور بلاتينيوم VIP", 0, False, None, "VIP ستة أشهر"),
        ("MEM-1023", "رامي ربيعة سمير", "01099992222", "male", MemberStatus.ACTIVE, 50, "3 شهور شامل سبا ومسبح", 300, False, None, "عليه 300 ج متبقي"),
        ("MEM-1024", "أكرم توفيق نصر", "01099993333", "male", MemberStatus.ACTIVE, 12, "شهر شامل حديد ولياقة", 0, True, 0, "تدريب خاص كابتن إسلام"),
        ("MEM-1025", "وسام أبو علي حسن", "01099994444", "male", MemberStatus.ACTIVE, 90, "3 شهور شامل سبا ومسبح", 0, False, None, "عضو متميز"),
        ("MEM-1026", "محمد عبد المنعم السيد", "01099995555", "male", MemberStatus.ACTIVE, 35, "شهر شامل حديد ولياقة", 0, False, None, "لياقة عامة"),
        ("MEM-1027", "أحمد نبيل كوكا", "01099996666", "male", MemberStatus.ACTIVE, 22, "شهر يوم ويوم (تمرين 4 ساعات)", 0, False, None, "يوم ويوم"),
        ("MEM-1028", "حمزة علاء فاروق", "01099997777", "male", MemberStatus.ACTIVE, 14, "شهر شامل حديد ولياقة", 100, False, None, "عليه 100 ج متبقي"),
        ("MEM-1029", "كريم فؤاد يحيى", "01099998888", "male", MemberStatus.ACTIVE, 65, "3 شهور شامل سبا ومسبح", 0, False, None, "سبا ومسبح"),
        ("MEM-1030", "محمد الشناوي طارق", "01099999999", "male", MemberStatus.ACTIVE, 240, "سنوي VIP الذهبي", 0, False, None, "سنوي VIP"),
    ]

    # Expand roster to ~60 realistic members
    first_names = ["أدهم", "مازن", "سيف الدين", "زياد", "عبد الرحمن", "بلال", "عصام", "أنس", "معتز", "شريف", "حازم", "هشام", "هيثم", "وائل", "رامز", "أمير", "إيهاب", "فادي", "شادي", "باسل", "تامر", "وليد", "سامر", "يحيى", "جمال", "مختار", "مؤمن", "صابر", "شاكر", "وجدي"]
    last_names = ["المهدي", "الشريف", "حسني", "غنيم", "الباز", "زهران", "عزت", "عطية", "الجمال", "غنيمي", "أبو النجا", "البدري", "الجوخدار", "الفيومي", "الدالي", "المنياوي", "عثمان", "النجار", "الخولاني", "مرعي", "الصعيدي", "علام", "رمضان", "شوقي", "السروجي", "الصباغ", "الخطيب", "أبو تريكة", "بركات", "متعب"]

    for i in range(31, 61):
        f = first_names[(i - 31) % len(first_names)]
        l = last_names[(i - 31) % len(last_names)]
        m_id = f"MEM-{1000 + i}"
        m_mob = f"010{i:02d}987654"
        delta = random.randint(-40, 120)
        st = MemberStatus.ACTIVE if delta >= 0 else MemberStatus.EXPIRED
        p_key = random.choice(["شهر شامل حديد ولياقة", "شهر يوم ويوم (تمرين 4 ساعات)", "3 شهور شامل سبا ومسبح"])
        debt = Decimal(str(random.choice([0, 0, 0, 150, 200, 350]))) if st == MemberStatus.ACTIVE else Decimal("0.00")
        member_roster.append((m_id, f"{f} {l}", m_mob, "male", st, delta, p_key, debt, False, None, "عضو مسجل"))

    created_members = []
    payments_to_create = []

    for idx, (m_id, name, mob, gender, st, end_delta, p_key, debt, has_pt, c_idx, notes) in enumerate(member_roster):
        p_obj = plans.get(p_key, plans["شهر شامل حديد ولياقة"])
        end_d = today + timedelta(days=end_delta)
        dur = p_obj.duration_days or 30
        start_d = end_d - timedelta(days=dur)

        total_plan_price = p_obj.price
        pt_price = Decimal("1500.00") if has_pt else Decimal("0.00")
        net_amount = total_plan_price + pt_price
        paid_amount = max(Decimal("0.00"), net_amount - Decimal(str(debt)))

        mem = Member.objects.create(
            member_id=m_id,
            name=name,
            mobile=mob,
            gender=gender,
            current_status=st,
            branch=b_main if idx % 4 != 0 else b_nasr,
            notes=notes,
            has_face_enrolled=True,
            face_enrolled_at=now - timedelta(days=random.randint(10, 60)),
            last_subscription_start=start_d,
            last_subscription_end=end_d,
            last_subscription_type=p_key,
            current_paid=paid_amount,
            current_remaining=Decimal(str(debt)),
            total_paid=paid_amount,
            last_payment_date=now - timedelta(days=random.randint(1, 25)),
            has_private=has_pt,
            assigned_coach=coaches[c_idx] if (has_pt and c_idx is not None and c_idx < len(coaches)) else None,
            private_price=pt_price,
        )
        created_members.append(mem)

        sub = Subscription.objects.create(
            member=mem,
            plan=p_obj,
            plan_name=p_obj.name,
            start_date=start_d,
            end_date=end_d,
            plan_price=p_obj.price,
            has_private=has_pt,
            private_price=pt_price,
            coach=mem.assigned_coach,
            coach_commission_rate=Decimal("0.5000") if has_pt else Decimal("0.0000"),
            coach_commission_amount=Decimal("750.00") if has_pt else Decimal("0.00"),
            discount=Decimal("0.00"),
            net_amount=net_amount,
            paid_amount=paid_amount,
            remaining_amount=Decimal(str(debt)),
            operation_type="new_subscription",
            payment_method="كاش نقدي (Cash)",
            created_by=u_reception if idx % 2 == 0 else u_manager,
        )

        # Distribute payments across temporal windows
        if paid_amount > Decimal("0.00"):
            payments_to_create.append((mem, sub, paid_amount, idx))

    # 11. Create & Backdate Payments into Temporal Buckets
    # Bucket A: Today (8 payments ~ 3,450 ج.م)
    # Bucket B: This Week (18 payments ~ 14,800 ج.م)
    # Bucket C: Earlier This Month (25 payments ~ 35,850 ج.م)
    # Total Month Revenue = ~ 54,100 ج.م
    # Bucket D: Last Month (Oct) (30 payments ~ 46,200 ج.م) for comparative +17% growth
    created_payments = []

    for i, (m, s, amt, roster_idx) in enumerate(payments_to_create):
        p_obj = Payment.objects.create(
            payment_id=f"PAY-{10000 + i}",
            invoice_no=f"INV-{10000 + i}",
            operation_type=PaymentOperationType.NEW_SUBSCRIPTION,
            member=m,
            subscription=s,
            amount=amt,
            payment_method=payment_methods[i % len(payment_methods)].name,
            branch=m.branch,
            created_by=u_reception if i % 2 == 0 else u_manager,
        )
        created_payments.append((p_obj, i))

    # Now backdate payments using .update(created_at=...)
    for p_obj, i in created_payments:
        if i < 8:
            # TODAY (spread across today's morning to evening)
            hour = 8 + (i * 2) % 13
            minute = (i * 17) % 60
            p_time = timezone.make_aware(datetime.combine(today, datetime.min.time())).replace(hour=hour, minute=minute)
        elif i < 26:
            # THIS WEEK (days 1 to 6 ago)
            day_offset = 1 + (i % 6)
            h = 9 + (i * 3) % 12
            p_time = timezone.make_aware(datetime.combine(today - timedelta(days=day_offset), datetime.min.time())).replace(hour=h, minute=15)
        elif i < 50:
            # EARLIER THIS MONTH (days 7 to 18 ago)
            day_offset = 7 + (i % 11)
            p_time = timezone.make_aware(datetime.combine(today - timedelta(days=day_offset), datetime.min.time())).replace(hour=14, minute=30)
        else:
            # LAST MONTH (October 2026 - comparative baseline)
            day_offset = 25 + (i % 25)
            p_time = timezone.make_aware(datetime.combine(today - timedelta(days=day_offset), datetime.min.time())).replace(hour=16, minute=0)

        Payment.objects.filter(id=p_obj.id).update(created_at=p_time)

    # 12. Check-In Events (Today, This Week, This Month)
    # A) Today's Check-ins (25 members checked in today!)
    today_active_pool = [m for m in created_members if m.current_status == MemberStatus.ACTIVE][:25]
    for idx, m in enumerate(today_active_pool):
        h = 8 + (idx % 14)  # 8:00 AM to 10:00 PM
        m_min = (idx * 9) % 60
        c_time = timezone.make_aware(datetime.combine(today, datetime.min.time())).replace(hour=h, minute=m_min)
        CheckInEvent.objects.create(
            member=m,
            checked_in_at=c_time,
            method="face" if idx % 3 != 0 else "manual",
            confidence=round(random.uniform(0.88, 0.98), 2) if idx % 3 != 0 else None,
            status_snapshot="active",
            days_left_snapshot=m.days_left,
            debt_snapshot=m.current_remaining,
            branch=m.branch,
        )

    # Add 1 Denied check-in today for expired member
    exp_mem = Member.objects.filter(current_status=MemberStatus.EXPIRED).first()
    if exp_mem:
        CheckInEvent.objects.create(
            member=exp_mem,
            checked_in_at=now - timedelta(minutes=35),
            method="face",
            confidence=0.95,
            status_snapshot="denied_expired",
            days_left_snapshot=0,
            debt_snapshot=Decimal("0.00"),
            branch=b_main,
        )

    # B) Historical Check-ins for the past 14 days (This week & this month)
    for day_offset in range(1, 15):
        past_d = today - timedelta(days=day_offset)
        daily_sample = random.sample(created_members[:35], min(len(created_members[:35]), random.randint(14, 24)))
        for sm in daily_sample:
            h = random.randint(9, 21)
            minute = random.randint(0, 59)
            t = timezone.make_aware(datetime.combine(past_d, datetime.min.time())).replace(hour=h, minute=minute)
            CheckInEvent.objects.create(
                member=sm,
                checked_in_at=t,
                method="face",
                confidence=round(random.uniform(0.86, 0.97), 2),
                status_snapshot="active" if sm.current_status == MemberStatus.ACTIVE else "denied_expired",
                days_left_snapshot=max(0, sm.days_left + day_offset),
                debt_snapshot=sm.current_remaining,
                branch=sm.branch,
            )

    # 13. Audit Log Entries (Recorded by reception and manager)
    AuditLog.objects.all().delete()
    audit_samples = [
        (u_reception, "new_subscription", "Member", "MEM-1001", Decimal("4000.00"), "تسجيل اشتراك سنوي VIP الذهبي للعضو أحمد حسام الدين"),
        (u_reception, "debt_payment", "Member", "MEM-1002", Decimal("150.00"), "تحصيل متبقي اشتراك 150 ج كاش"),
        (u_manager, "discount_applied", "Subscription", "SUB-1005", Decimal("100.00"), "تطبيق خصم استثنائي 100 ج بموافقة إدارة الفرع"),
        (u_reception, "private_assigned", "Member", "MEM-1007", Decimal("1500.00"), "حجز تدريب خاص Private مع كابتن إسلام عادل"),
        (u_reception, "cash_handover", "ShiftHandover", "HND-01", Decimal("3200.00"), "تسليم نقدية شفت صباحي إلى الإدارة مطابقة تماماً بدون عجز"),
        (u_manager, "expense_voucher", "Expense", "EXP-01", Decimal("1450.00"), "صرف فاتورة صيانة سيور المشايات الرياضية"),
        (u_reception, "bar_sale", "BarSale", "BAR-01", Decimal("120.00"), "مبيعات بار ومشروبات طاقة بالكاونتر"),
    ]
    for usr, act, t_mod, t_id, amt, det in audit_samples:
        AuditLog.objects.create(
            user=usr,
            action=act,
            target_model=t_mod,
            target_id=t_id,
            amount=amt,
            details=det,
        )

    # 14. WhatsApp Messaging Samples
    WhatsAppMessage.objects.all().delete()
    wa_data = [
        ("01001234567", "مرحباً يا بطل! تم تجديد اشتراكك السنوي VIP بنجاح في سيستمايز فيتنس كلوب. فورمتك تهمنا!", MessageType.RECEIPT, MessageStatus.SENT, "أحمد حسام الدين"),
        ("01012345678", "تنبيه ودي: متبقي يومان فقط على اشتراكك في سيستمايز فيتنس. مستنيينك تجدد علشان تستمر في الفورمة!", MessageType.REMINDER_3, MessageStatus.PENDING, "محمود عبد العزيز"),
        ("01023456789", "تنبيه هام: غداً آخر يوم في اشتراكك الرياضي. مكتب الاستقبال في انتظارك بأفضل عروض التجديد!", MessageType.REMINDER_1, MessageStatus.PENDING, "طارق السعيد"),
        ("01034567890", "اشتقنالك في سيستمايز جيم! اشتراكك انتهى، وبنقدملك خصم تجديد خاص علشان ترجع بقوة.", MessageType.EXPIRED, MessageStatus.PENDING, "خالد إبراهيم"),
        ("01045678901", "إشعار حسابات: متبقي على حسابك مبلغ 500 ج.م برجاء السداد مع أقرب زيارة. شكراً لتعاونك", MessageType.CUSTOM, MessageStatus.SENT, "عمر فاروق"),
    ]
    for mob, msg, m_type, m_status, rec_name in wa_data:
        WhatsAppMessage.objects.create(
            mobile=mob,
            message=msg,
            msg_type=m_type,
            status=m_status,
            recipient_name=rec_name,
            recipient_type="member",
            dedup_key=f"WA-{mob}-{m_type}",
            sent_at=now if m_status == MessageStatus.SENT else None,
        )

    return {
        "members": Member.objects.count(),
        "active_members": Member.objects.filter(current_status=MemberStatus.ACTIVE).count(),
        "payments": Payment.objects.count(),
        "expenses": Expense.objects.count(),
        "checkins": CheckInEvent.objects.count(),
        "bar_sales": BarSale.objects.count(),
    }
