from decimal import Decimal
from django.db import models
from django.conf import settings


class Branch(models.Model):
    name = models.CharField(max_length=150, verbose_name="اسم الفرع")
    code = models.CharField(max_length=50, unique=True, verbose_name="كود الفرع")
    address = models.CharField(max_length=255, blank=True, default="", verbose_name="عنوان الفرع")
    phone = models.CharField(max_length=30, blank=True, default="", verbose_name="هاتف الفرع")
    manager_name = models.CharField(max_length=100, blank=True, default="", verbose_name="اسم مدير الفرع")
    is_main = models.BooleanField(default=False, verbose_name="الفرع الرئيسي")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "فرع"
        verbose_name_plural = "الفروع"
        ordering = ["-is_main", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class GymProfile(models.Model):
    # Branding & Customization for ANY Gym
    gym_name = models.CharField(max_length=100, default="اسم الصالة الرياضية", verbose_name="اسم الصالة الرياضية")
    gym_tagline = models.CharField(max_length=150, default="مركز اللياقة البدنية والكمال الجسماني", verbose_name="الشعار اللفظي (Slogan)")
    logo = models.ImageField(upload_to="branding/", null=True, blank=True, verbose_name="شعار الصالة (Logo)")
    primary_color = models.CharField(max_length=20, default="#84CC16", verbose_name="لون الهوية الأساسي (Primary Accent)")
    secondary_color = models.CharField(max_length=20, default="#121723", verbose_name="لون البطاقات والأسطح (Secondary / Surface)")
    tertiary_color = models.CharField(max_length=20, default="#0B0E14", verbose_name="اللون الثالث / خلفية النظام (Tertiary / Background)")
    accent_theme = models.CharField(
        max_length=30,
        choices=[
            ("lime", "أخضر رياضي (Neon Lime)"),
            ("blue", "أزرق تيتانيوم (Titanium Blue)"),
            ("red", "أحمر طاقة (Power Red)"),
            ("orange", "برتقالي حماسي (Blaze Orange)"),
            ("gold", "ذهبي ملكي (Royal Gold)"),
            ("purple", "أرجواني مميز (Cyber Purple)"),
            ("emerald", "زمردي داكن (Dark Emerald)"),
            ("monochrome", "أسود أحادي (Obsidian Monochrome)"),
            ("custom", "ألوان مخصصة (Custom Hex)"),
        ],
        default="lime",
        verbose_name="طابع الألوان المعتمد",
    )

    manager_mobile = models.CharField(max_length=20, blank=True, default="", verbose_name="رقم هاتف المدير")
    currency = models.CharField(max_length=10, default="ج.م", verbose_name="العملة")
    timezone = models.CharField(max_length=50, default="Africa/Cairo", verbose_name="المنطقة الزمنية")
    daily_report_time = models.CharField(max_length=10, default="22:00", verbose_name="موعد إرسال التقرير اليومي")
    
    # Face Recognition & Electronic Gate Control
    face_camera_enabled = models.BooleanField(
        default=True,
        verbose_name="تشغيل كاميرا التعرف على الوجه التلقائية في النظام",
        help_text="عند التفعيل، تعمل الكاميرا تلقائياً في خلفية الموقع لإظهار إشعار الدخول أو انتهاء الاشتراك فوراً فور اقتراب المشترك.",
    )
    face_match_threshold = models.FloatField(
        default=65.0,
        verbose_name="دقة مطابقة الوجه المطلوبة (0 - 100%)",
        help_text="المعيار الموحد لدقة التعرف بالوجه: 65% هي النسبة الموصى بها لمنع الخلط بين الأشخاص نهائياً.",
    )
    face_min_confidence = models.FloatField(default=0.55, verbose_name="حساسية كشف الوجه (Detection Threshold)")
    face_debounce_seconds = models.PositiveIntegerField(default=60, verbose_name="مهلة منع تكرار التسجيل (ثوانٍ)")

    # Manager Face ID Unlock
    manager_face_unlock_enabled = models.BooleanField(
        default=True,
        verbose_name="تفعيل فتح مناطق الإدارة والإعدادات ببصمة وجه المدير",
        help_text="عند التفعيل، يمكن للمدير فتح لوحة المدير وصفحة الإعدادات والمدربين فوراً عبر التعرف على الوجه دون الحاجة لإدخال كلمة السر.",
    )
    manager_face_enrolled = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="تم تسجيل بصمة وجه المدير",
    )
    manager_face_photo = models.ImageField(
        upload_to="manager_face/",
        null=True,
        blank=True,
        verbose_name="صورة وجه المدير المعتمدة",
    )
    manager_face_embeddings = models.JSONField(
        default=list,
        blank=True,
        verbose_name="بصمات وجه المدير الرقمية (Vectors)",
    )
    manager_face_enrolled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ تسجيل بصمة وجه المدير",
    )
    manager_face_camera_source = models.CharField(
        max_length=20,
        choices=[
            ("same", "نفس كاميرا النظام المفتوحة (Shared System Camera)"),
            ("separate", "كاميرا منفصلة / كاميرا ويب المتصفح (Separate Webcam)"),
        ],
        default="same",
        verbose_name="مصدر كاميرا فتح وجه المدير",
        help_text="اختر 'نفس كاميرا النظام' لتجنب تعارض الكاميرا والفتح التلقائي بدون أخطاء، أو 'كاميرا منفصلة' عند تخصيص كاميرا ثانية لمكتب المدير.",
    )

    # Electronic Gate & Turnstile Network / Relay Settings
    gate_relay_enabled = models.BooleanField(default=False, verbose_name="تفعيل فتح البوابة تلقائياً عند التعرف بالوجه")
    gate_relay_type = models.CharField(
        max_length=20,
        choices=[
            ("lan_http", "شبكة محلية - رابط IP (HTTP GET/POST)"),
            ("lan_tcp", "شبكة محلية - مقبس مباشر (TCP Socket)"),
            ("serial_com", "منفذ تسلسلي USB (COM Port)"),
        ],
        default="lan_http",
        verbose_name="نوع اتصال البوابة",
    )
    gate_ip_address = models.CharField(max_length=100, default="192.168.1.50", blank=True, verbose_name="عنوان IP الثابت للبوابة (Fixed Local IP)")
    gate_ip_port = models.PositiveIntegerField(default=80, verbose_name="منفذ الاتصال (Port)")
    gate_http_path = models.CharField(max_length=200, default="/open", blank=True, verbose_name="مسار فتح البوابة (HTTP Endpoint)")
    gate_http_method = models.CharField(max_length=10, choices=[("GET", "GET"), ("POST", "POST")], default="GET", verbose_name="طريقة الإرسال (Method)")
    gate_tcp_payload = models.CharField(max_length=100, default="OPEN", blank=True, verbose_name="أمر الفتح (TCP Payload)")
    gate_pulse_seconds = models.FloatField(default=2.5, verbose_name="مدة فتح البوابة بالثواني")
    gate_relay_port = models.CharField(max_length=50, default="COM3", blank=True, verbose_name="منفذ تحكم البوابة (COM Port / Legacy)")

    # WhatsApp Configuration
    whatsapp_enabled = models.BooleanField(default=True, verbose_name="تفعيل إرسال الواتساب")
    whatsapp_send_mode = models.CharField(
        max_length=20,
        choices=[("paste", "لصق سريع (Clipboard)"), ("typing", "كتابة تدريجية إنسانية")],
        default="paste",
        verbose_name="نمط إرسال الرسائل",
    )
    whatsapp_letter_delay = models.FloatField(default=0.001, verbose_name="سرعة كتابة الحروف")
    whatsapp_search_x = models.IntegerField(default=280, verbose_name="إحداثي X لشريط بحث واتساب (WhatsApp Search X)")
    whatsapp_search_y = models.IntegerField(default=120, verbose_name="إحداثي Y لشريط بحث واتساب (WhatsApp Search Y)")
    expired_message_template = models.TextField(
        default="تنبيه من {gym_name}\nأهلاً {name}\nاشتراكك انتهى بتاريخ: {end_date}\nنورتنا في أي وقت للتجديد والرجوع للتمرين 💪",
        verbose_name="قالب رسالة انتهاء الاشتراك",
    )
    whatsapp_randomize_templates = models.BooleanField(
        default=True,
        verbose_name="تنويع واختيار صياغات عشوائية تلقائياً من بنك الرسائل لمنع الحظر",
    )
    whatsapp_kill_switch = models.CharField(
        max_length=50,
        default="ctrl+k",
        verbose_name="زر الطوارئ لإيقاف إرسال الواتساب (Kill Switch)",
        help_text="زر الاختصار لإيقاف إرسال الواتساب فوراً عند الطوارئ (الافتراضي ctrl+k)",
    )
    
    # Trainers Page Security
    trainers_page_password = models.CharField(
        max_length=50,
        default="1234",
        verbose_name="كلمة مرور صفحة المدربين",
        help_text="كلمة المرور المطلوبة لفتح صفحة إدارة المدربين وحساباتهم",
    )

    # GitHub System Updates & Versioning
    github_repo_url = models.CharField(
        max_length=255,
        default="https://github.com/mostafa-donia/HULK_gym_web_face_recogniations.git",
        blank=True,
        verbose_name="رابط مستودع التحديثات (GitHub Repo URL)",
    )
    github_branch = models.CharField(
        max_length=50,
        default="main",
        blank=True,
        verbose_name="فرع التحديثات (Branch)",
    )
    last_update_check = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ آخر فحص للتحديثات")
    current_version_tag = models.CharField(max_length=50, default="v2.1.0-face", blank=True, verbose_name="رقم الإصدار")

    # Telegram Bot Integration
    telegram_bot_enabled = models.BooleanField(
        default=True,
        verbose_name="تفعيل بوت تليجرام",
        help_text="تفعيل الرد التلقائي وإرسال إشعارات الاشتراكات والتقارير عبر تليجرام",
    )
    telegram_bot_token = models.CharField(
        max_length=150,
        default="7123456789:AAFlvExampleTokenPlaceholderForGym",
        blank=True,
        verbose_name="توكن بوت تليجرام (Bot Token)",
    )
    telegram_manager_chat_id = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="معرف شات تليجرام للمدير (Manager Chat ID)",
    )
    
    # Updated timestamp
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ آخر تحديث")

    class Meta:
        verbose_name = "إعدادات الصالة العامة"
        verbose_name_plural = "إعدادات الصالة العامة"

    @classmethod
    def get_solo(cls) -> "GymProfile":
        profile, _ = cls.objects.get_or_create(id=1)
        return profile

    @property
    def face_match_threshold_ratio(self) -> float:
        """Returns normalized 0.0 - 1.0 cosine threshold for internal facial vector matching."""
        try:
            val = float(self.face_match_threshold if self.face_match_threshold is not None else 65.0)
        except (ValueError, TypeError):
            val = 65.0
        if val > 1.0:
            return max(0.0, min(1.0, val / 100.0))
        return max(0.0, min(1.0, val))

    @property
    def face_match_threshold_percent(self) -> int:
        """Returns 0 - 100 integer percentage for UI display and slider control."""
        try:
            val = float(self.face_match_threshold if self.face_match_threshold is not None else 65.0)
        except (ValueError, TypeError):
            val = 65.0
        if val <= 1.0:
            return int(round(val * 100))
        return int(round(val))

    @property
    def primary_contrast_color(self) -> str:
        """Calculate high-contrast foreground color (#081104 or #FFFFFF) for primary accent."""
        try:
            hex_str = (self.primary_color or "#84CC16").lstrip("#")
            if len(hex_str) == 3:
                hex_str = "".join([c * 2 for c in hex_str])
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            return "#081104" if luminance > 0.55 else "#FFFFFF"
        except Exception:
            return "#081104"

    def get_primary_color_rgb(self, default=(225, 29, 72)) -> tuple:
        """Returns (R, G, B) integer tuple for primary_color."""
        try:
            hex_str = (self.primary_color or "#E11D48").lstrip("#")
            if len(hex_str) == 3:
                hex_str = "".join([c * 2 for c in hex_str])
            if len(hex_str) == 6:
                return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))
        except Exception:
            pass
        return default

    def get_logo_image_path(self):
        """Returns absolute path to a PNG/JPEG logo file, converting .ico if needed."""
        if not self.logo:
            return None
        try:
            import os
            p = getattr(self.logo, "path", None)
            if not p or not os.path.exists(p):
                return None
            if p.lower().endswith(".ico"):
                png_p = os.path.splitext(p)[0] + ".png"
                if os.path.exists(png_p):
                    return png_p
                try:
                    from PIL import Image
                    im = Image.open(p)
                    im.save(png_p)
                    return png_p
                except Exception:
                    return p
            return p
        except Exception:
            return None

    def __str__(self) -> str:
        return self.gym_name


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="المستخدم",
    )
    action = models.CharField(max_length=100, verbose_name="العملية")
    target_model = models.CharField(max_length=100, verbose_name="الجدول المستهدف")
    target_id = models.CharField(max_length=100, blank=True, verbose_name="معرف السجل")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="المبلغ المرتبط بالعملية")
    details = models.TextField(blank=True, verbose_name="التفاصيل")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ ووقت العملية")

    @classmethod
    def log(cls, action_type="", description="", user=None, member=None, amount=Decimal("0.00")):
        try:
            return cls.objects.create(
                user=user if getattr(user, "is_authenticated", False) else None,
                action=action_type,
                target_model="Member" if member else "System",
                target_id=str(member.id if member else ""),
                details=description,
                amount=Decimal(str(amount or "0.00")),
            )
        except Exception as e:
            print(f"[AuditLog.log] Error: {e}")
            return None

    class Meta:
        verbose_name = "سجل العمليات (Audit Log)"
        verbose_name_plural = "سجلات العمليات"
        ordering = ["-created_at"]


def log_audit_event(user=None, action="", target_model="Member", target_id="", details="", amount=Decimal("0.00")):
    """Helper to log sensitive managerial actions like discounts, private changes, and price overrides."""
    try:
        return AuditLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            action=action,
            target_model=target_model,
            target_id=str(target_id),
            details=details,
            amount=Decimal(str(amount or "0.00")),
        )
    except Exception as e:
        print(f"[log_audit_event] Error: {e}")
        return None


class SystemLicense(models.Model):
    STATUS_CHOICES = [
        ("demo", "فترة تجريبية (Demo)"),
        ("active", "مرخص ونشط (Active)"),
        ("suspended", "معلق يدوياً من المطور (Suspended)"),
        ("expired", "انتهت فترة الاشتراك (Expired)"),
        ("tampered", "محاولة تلاعب بالنظام (Tampered)"),
    ]

    LICENSE_TYPE_CHOICES = [
        ("demo", "تجريبي (7 أيام)"),
        ("monthly", "اشتراك شهري (SaaS Monthly)"),
        ("yearly", "اشتراك سنوي (SaaS Yearly)"),
        ("lifetime", "شراء مدى الحياة (Lifetime)"),
    ]

    machine_id = models.CharField(max_length=120, unique=True, verbose_name="بصمة الجهاز (Machine HWID)")
    client_name = models.CharField(max_length=150, default="عميل تجريبي", verbose_name="اسم العميل / الصالة")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="demo", verbose_name="حالة الترخيص")
    license_type = models.CharField(max_length=20, choices=LICENSE_TYPE_CHOICES, default="demo", verbose_name="نوع الترخيص")
    
    first_run_date = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ أول تشغيل")
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name="صالح حتى تاريخ")
    
    # Feature Flags (Every Little Option Access)
    feature_face_recognition = models.BooleanField(default=True, verbose_name="بصمة الوجه الذكية")
    feature_gate_relay = models.BooleanField(default=True, verbose_name="بوابات الدخول ومتحكم الريليه")
    feature_whatsapp = models.BooleanField(default=True, verbose_name="رسائل وتنبيهات الواتساب")
    feature_telegram = models.BooleanField(default=True, verbose_name="بوت تليجرام")
    feature_bar = models.BooleanField(default=True, verbose_name="مخزون ومبيعات البار")
    feature_payroll = models.BooleanField(default=True, verbose_name="المدربين ومسيرات الرواتب")
    feature_retention = models.BooleanField(default=True, verbose_name="تتبع حركة واستمرارية الأعضاء")
    feature_reports = models.BooleanField(default=True, verbose_name="التقارير المالية المتقدمة")
    feature_barcode = models.BooleanField(default=True, verbose_name="قارئ الباركود والـ QR")
    feature_expenses = models.BooleanField(default=True, verbose_name="المصروفات وسندات الصرف")
    feature_multi_branch = models.BooleanField(default=False, verbose_name="إدارة الفروع المتعددة (Multi-Branch Add-on)")

    # Anti-Tampering & Security
    tamper_hash = models.CharField(max_length=256, blank=True, default="", verbose_name="توقيع الأمان الرقمي")
    last_clock_check = models.DateTimeField(null=True, blank=True, verbose_name="آخر توقيت فحص للنظام")
    
    # Remote Control Center & Cloud Governance
    remote_control_url = models.CharField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="رابط مركز التحكم السحابي للمطور",
        help_text="رابط الـ API أو JSON للتحكم المركزي في صلاحيات العميل عن بعد",
    )
    last_remote_sync = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ آخر مزامنة مع السيرفر")
    updates_allowed = models.BooleanField(default=True, verbose_name="السماح بالتحديثات من GitHub")
    update_block_reason = models.CharField(max_length=255, blank=True, default="", verbose_name="سبب حظر التحديثات")
    developer_notes = models.TextField(blank=True, default="", verbose_name="رسالة المطور أو إشعار الإيقاف")
    developer_contact_phone = models.CharField(
        max_length=30,
        default="01080922432",
        verbose_name="رقم واتساب المطور للتفعيل",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ترخيص النظام وحماية الملكية"
        verbose_name_plural = "تراخيص النظام وحماية الملكية"

    def __str__(self):
        return f"{self.client_name} - {self.machine_id} ({self.get_status_display()})"

