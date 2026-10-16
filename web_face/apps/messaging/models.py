from django.db import models


class MessageStatus(models.TextChoices):
    PENDING = "pending", "معلق (جاهز للإرسال)"
    SCHEDULED = "scheduled", "مجدول (تأجيل مؤقت)"
    SENT = "sent", "تم الإرسال بنجاح"
    FAILED = "failed", "فشل الإرسال"


class MessageType(models.TextChoices):
    RECEIPT = "receipt", "إيصال سداد"
    REMINDER_3 = "reminder_3", "تنبيه قبل 3 أيام"
    REMINDER_1 = "reminder_1", "تنبيه قبل يوم واحد"
    EXPIRED = "expired", "تنبيه انتهاء الاشتراك"
    SALARY_STATEMENT = "salary_statement", "كشف راتب موظف"
    MANAGER_REPORT = "manager_report", "تقرير المدير اليومي"
    CUSTOM = "custom", "رسالة مخصصة"
    BULK = "bulk", "إرسال جماعي مخصص"


class WhatsAppMessage(models.Model):
    mobile = models.CharField(max_length=20, db_index=True, verbose_name="رقم الهاتف المستلم")
    message = models.TextField(verbose_name="نص الرسالة")
    attachment = models.FileField(upload_to="whatsapp_attachments/", blank=True, null=True, verbose_name="ملف أو صورة مرفقة")
    link = models.URLField(max_length=500, blank=True, default="", verbose_name="رابط مرفق")
    msg_type = models.CharField(
        max_length=30,
        choices=MessageType.choices,
        default=MessageType.CUSTOM,
        db_index=True,
        verbose_name="نوع الرسالة",
    )
    recipient_name = models.CharField(max_length=150, blank=True, verbose_name="اسم المستلم")
    recipient_type = models.CharField(
        max_length=20,
        choices=[("member", "لاعب / عضو"), ("employee", "موظف / مدرب"), ("manager", "إدارة الصالة")],
        default="member",
        verbose_name="فئة المستلم",
    )
    status = models.CharField(
        max_length=20,
        choices=MessageStatus.choices,
        default=MessageStatus.PENDING,
        db_index=True,
        verbose_name="حالة الرسالة",
    )
    send_after = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="موعد الإرسال المؤجل")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ ووقت الإرسال الفعلي")
    error_detail = models.TextField(blank=True, verbose_name="تفاصيل الخطأ إن وجد")
    sent_via_telegram = models.BooleanField(default=False, verbose_name="أُرسلت عبر تليجرام أيضاً")
    dedup_key = models.CharField(max_length=150, unique=True, db_index=True, verbose_name="مفتاح منع التكرار")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "رسالة واتساب"
        verbose_name_plural = "طابور رسائل الواتساب"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.mobile} ({self.get_msg_type_display()} - {self.get_status_display()})"


class WhatsAppMessageBank(models.Model):
    category = models.CharField(max_length=50, unique=True, verbose_name="تصنيف القالب")
    variations = models.JSONField(default=list, verbose_name="الصياغات المتعددة للرسالة (لمنع الحظر)")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")

    class Meta:
        verbose_name = "بنك قوالب الواتساب"
        verbose_name_plural = "بنك قوالب الواتساب"

    def __str__(self) -> str:
        return f"بنك رسائل: {self.category} ({len(self.variations)} صياغة)"
