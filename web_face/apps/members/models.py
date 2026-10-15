from datetime import date, timedelta
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone


class Plan(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم الباقة")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="السعر الأساسي")
    duration_days = models.PositiveIntegerField(default=30, verbose_name="المدة بالأيام")
    months = models.PositiveIntegerField(default=1, verbose_name="عدد الشهور")
    frequency = models.CharField(max_length=50, default="كل يوم", verbose_name="نظام الحضور")
    is_active = models.BooleanField(default=True, verbose_name="مفعلة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "باقة اشتراك"
        verbose_name_plural = "باقات الاشتراكات"
        ordering = ["price"]

    def __str__(self) -> str:
        return f"{self.name} ({self.price} ج.م)"


class MemberStatus(models.TextChoices):
    ACTIVE = "active", "نشط"
    EXPIRED = "expired", "منتهي"


class Member(models.Model):
    member_id = models.CharField(max_length=30, unique=True, db_index=True, verbose_name="كود العضو")
    name = models.CharField(max_length=150, db_index=True, verbose_name="الاسم بالكامل")
    mobile = models.CharField(max_length=20, db_index=True, verbose_name="رقم الهاتف")
    gender = models.CharField(
        max_length=10,
        choices=[("male", "ذكر"), ("female", "أنثى")],
        default="male",
        verbose_name="النوع",
    )
    current_status = models.CharField(
        max_length=15,
        choices=MemberStatus.choices,
        default=MemberStatus.EXPIRED,
        db_index=True,
        verbose_name="الحالة الحالية",
    )

    # Face Recognition Biometrics (Replaces Old Fingerprint)
    has_face_enrolled = models.BooleanField(default=False, db_index=True, verbose_name="مسجل ببصمة الوجه")
    face_enrolled_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ تسجيل بصمة الوجه")
    face_photo = models.ImageField(upload_to="faces/", null=True, blank=True, verbose_name="صورة الوجه المعتمدة")
    face_embeddings = models.JSONField(default=list, blank=True, verbose_name="بصمات الوجه الرقمية (Vectors)")

    last_subscription_start = models.DateField(null=True, blank=True, verbose_name="تاريخ بداية الاشتراك")
    last_subscription_end = models.DateField(null=True, blank=True, db_index=True, verbose_name="تاريخ نهاية الاشتراك")
    last_subscription_type = models.CharField(max_length=100, blank=True, verbose_name="نوع آخر باقة")
    last_payment_date = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ آخر دفعة")
    
    current_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="المدفوع حالياً")
    current_remaining = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        db_index=True,
        verbose_name="المتبقي (الديون)",
    )
    total_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="إجمالي المدفوعات التاريخية")
    
    follow_up_date = models.DateField(null=True, blank=True, verbose_name="تاريخ المتابعة")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    google_contact_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ مزامنة جهات اتصال جوجل")

    # Private Training Add-on (التدريب الخاص كإضافة للباقة)
    has_private = models.BooleanField(default=False, db_index=True, verbose_name="تدريب خاص (Private)")
    private_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="سعر إضافة التدريب الخاص")
    assigned_coach = models.ForeignKey(
        "payroll.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_members",
        limit_choices_to={"role": "TRAINER"},
        verbose_name="المدرب الخاص (الكابتن)",
    )
    # Manager Agreed Discount for Renewals
    renewal_discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="خصم التجديد المعتمد")
    discount_enabled = models.BooleanField(default=False, verbose_name="تفعيل خصم التجديد تلقائياً")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التسجيل")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "عضو"
        verbose_name_plural = "الأعضاء"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.member_id})"

    @property
    def phone(self) -> str:
        return self.mobile

    @property
    def days_left(self) -> int:
        if not self.last_subscription_end:
            return 0
        delta = (self.last_subscription_end - date.today()).days
        return max(0, delta)

    @property
    def is_active(self) -> bool:
        if not self.last_subscription_end:
            return False
        return self.last_subscription_end >= date.today()

    @property
    def has_debt(self) -> bool:
        return self.current_remaining > Decimal("0.00")

    @property
    def check_in_events(self):
        return self.check_ins

    def refresh_status(self, save: bool = True) -> str:
        """Dynamically reconciles active/expired state against today's date."""
        new_status = MemberStatus.ACTIVE if self.is_active else MemberStatus.EXPIRED
        if self.current_status != new_status:
            self.current_status = new_status
            if save:
                self.save(update_fields=["current_status", "updated_at"])
        return self.current_status

    def is_alternate_days_subscription(self) -> bool:
        """
        Checks whether the member's current subscription follows 'day on day off' (يوم ويوم).
        Handles all common variations:
        'يوم ويوم', 'يوم و يوم', 'يوم بعد يوم', 'day on day off', 'alternate'
        """
        target_normalized = ["يومويوم", "يومبعديوم", "dayondayoff", "alternate"]

        def matches(text: str) -> bool:
            if not text:
                return False
            clean = text.lower().replace(" ", "").replace("-", "").replace("/", "").replace("_", "")
            return any(kw in clean for kw in target_normalized)

        if matches(self.last_subscription_type):
            return True

        active_sub = self.subscriptions.filter(end_date__gte=timezone.localdate()).order_by("-created_at").first()
        latest_sub = active_sub or self.subscriptions.order_by("-created_at").first()
        if latest_sub:
            if matches(latest_sub.plan_name):
                return True
            if latest_sub.plan:
                if matches(latest_sub.plan.frequency) or matches(latest_sub.plan.name):
                    return True
        return False

    def check_access_eligibility(self, current_time=None) -> dict:
        """
        Evaluates whether the member is allowed to enter right now.
        Enforces:
        1. Active subscription check (not expired).
        2. For 'day on day off' (يوم ويوم) plans:
           - Rule A: Cannot attend 2 days in a row. Blocked if member attended yesterday.
           - Rule B: Daily workout window is 4 hours from their first entry today.
                     If 4 hours have elapsed since the first check-in today, entry is denied for the rest of today.
        """
        import datetime

        if current_time is None:
            current_time = timezone.now()

        # 1. Base active check
        if not self.is_active:
            return {
                "allowed": False,
                "reason_code": "expired",
                "reason": "الاشتراك منتهي. يرجى التجديد بمكتب الاستقبال.",
                "window_hours_left": None,
                "first_entry_time": None,
                "first_entry_time_str": None,
            }

        # If not day-on-day-off subscription, normal entry allowed
        if not self.is_alternate_days_subscription():
            return {
                "allowed": True,
                "reason_code": "active",
                "reason": "مسموح بالدخول",
                "window_hours_left": None,
                "first_entry_time": None,
                "first_entry_time_str": None,
            }

        # 2. Alternate days rules ('يوم ويوم')
        current_local = timezone.localtime(current_time)
        today = current_local.date()
        yesterday = today - timedelta(days=1)

        start_yesterday = timezone.make_aware(datetime.datetime.combine(yesterday, datetime.time.min))
        end_yesterday = timezone.make_aware(datetime.datetime.combine(yesterday, datetime.time.max))

        start_today = timezone.make_aware(datetime.datetime.combine(today, datetime.time.min))
        end_today = timezone.make_aware(datetime.datetime.combine(today, datetime.time.max))

        # Rule A: Cannot attend 2 days in a row (check if member attended yesterday, excluding denied events)
        yesterday_attended = self.check_ins.filter(
            checked_in_at__range=(start_yesterday, end_yesterday)
        ).exclude(status_snapshot__startswith="denied").exists()

        if yesterday_attended:
            return {
                "allowed": False,
                "reason_code": "consecutive_day_blocked",
                "reason": "عفواً، باقتك بنظام (يوم ويوم) وغير مسموح بالدخول يومين متتاليين (سجلت حضوراً بالأمس).",
                "window_hours_left": None,
                "first_entry_time": None,
                "first_entry_time_str": None,
            }

        # Rule B: 4-hour window from first entry today
        today_checkins = self.check_ins.filter(
            checked_in_at__range=(start_today, end_today)
        ).exclude(status_snapshot__startswith="denied").order_by("checked_in_at")

        if today_checkins.exists():
            first_entry = today_checkins.first()
            first_entry_local = timezone.localtime(first_entry.checked_in_at)
            first_entry_time_str = first_entry_local.strftime("%I:%M %p")
            elapsed = current_time - first_entry.checked_in_at
            max_window = timedelta(hours=4)

            if elapsed > max_window:
                return {
                    "allowed": False,
                    "reason_code": "daily_window_expired",
                    "reason": f"عفواً، انتهت نافذة التمرين اليومية المسموحة (4 ساعات من أول دخول الساعة {first_entry_time_str}). غير مسموح بالدخول مرة أخرى اليوم.",
                    "window_hours_left": 0.0,
                    "first_entry_time": first_entry.checked_in_at,
                    "first_entry_time_str": first_entry_time_str,
                }
            else:
                remaining_seconds = (max_window - elapsed).total_seconds()
                remaining_hours = round(max(0.0, remaining_seconds / 3600.0), 1)
                return {
                    "allowed": True,
                    "reason_code": "active_within_window",
                    "reason": f"مسموح بالدخول (متبقي من نافذة تمرينك اليوم {remaining_hours} ساعة — أول دخول الساعة {first_entry_time_str})",
                    "window_hours_left": remaining_hours,
                    "first_entry_time": first_entry.checked_in_at,
                    "first_entry_time_str": first_entry_time_str,
                }

        # First entry of the day
        return {
            "allowed": True,
            "reason_code": "first_entry_today",
            "reason": "مسموح بالدخول (أول دخول اليوم — نافذة التمرين 4 ساعات)",
            "window_hours_left": 4.0,
            "first_entry_time": None,
            "first_entry_time_str": None,
        }


class Subscription(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="subscriptions", verbose_name="العضو")
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="الباقة")
    plan_name = models.CharField(max_length=100, verbose_name="اسم الباقة")
    start_date = models.DateField(db_index=True, verbose_name="تاريخ البداية")
    end_date = models.DateField(db_index=True, verbose_name="تاريخ النهاية")
    plan_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="سعر الباقة")
    
    # Private Training Add-on
    has_private = models.BooleanField(default=False, verbose_name="مشتمل على تدريب خاص")
    private_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="قيمة التدريب الخاص الإضافي")
    coach = models.ForeignKey(
        "payroll.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions_trained",
        verbose_name="المدرب المسند إليه",
    )
    coach_commission_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.5000"), verbose_name="نسبة عمولة المدرب")
    coach_commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="قيمة عمولة المدرب")

    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="الخصم")
    net_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المستحق الصافي")
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المدفوع")
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="المتبقي")
    allowance_days = models.PositiveIntegerField(default=0, verbose_name="أيام السماح")
    operation_type = models.CharField(
        max_length=30,
        choices=[("new_subscription", "اشتراك جديد"), ("renewal", "تجديد اشتراك")],
        default="new_subscription",
        verbose_name="نوع العملية",
    )
    payment_method = models.CharField(max_length=50, blank=True, verbose_name="طريقة الدفع")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="الموظف المسجل",
    )

    class Meta:
        verbose_name = "سجل اشتراك"
        verbose_name_plural = "سجلات الاشتراكات"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.member.name} - {self.plan_name} ({self.start_date} إلى {self.end_date})"


class CheckInEvent(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="check_ins", verbose_name="العضو")
    checked_in_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="وقت الحضور")
    method = models.CharField(
        max_length=20,
        choices=[("face", "بصمة الوجه"), ("manual", "تسجيل يدوي"), ("code", "كود العضو")],
        default="face",
        verbose_name="طريقة الحضور"
    )
    confidence = models.FloatField(null=True, blank=True, verbose_name="نسبة تطابق الوجه")
    status_snapshot = models.CharField(max_length=20, verbose_name="حالة الاشتراك وقت الدخول")
    days_left_snapshot = models.IntegerField(default=0, verbose_name="الأيام المتبقية")
    debt_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="الديون وقت الدخول")

    class Meta:
        verbose_name = "سجل حضور"
        verbose_name_plural = "سجلات الحضور"
        ordering = ["-checked_in_at"]
