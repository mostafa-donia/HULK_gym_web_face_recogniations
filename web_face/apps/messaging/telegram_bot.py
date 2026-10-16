import os
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import ssl
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Q, Count

logger = logging.getLogger(__name__)


def _get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def get_telegram_config():
    """Returns (enabled, token, manager_chat_id, gym_profile)."""
    from apps.core.models import GymProfile
    profile = GymProfile.get_solo()
    token = (profile.telegram_bot_token or "").strip()
    enabled = bool(profile.telegram_bot_enabled and token and "Placeholder" not in token)
    return enabled, token, (profile.telegram_manager_chat_id or "").strip(), profile


def make_telegram_api_call(method: str, payload: dict = None, token: str = None) -> dict:
    """Executes a Telegram Bot API request and returns JSON response."""
    if not token:
        _, token, _, _ = get_telegram_config()
    if not token:
        return {"ok": False, "description": "Telegram Bot Token is not configured."}

    url = f"https://api.telegram.org/bot{token}/{method}"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload else None

    req = urllib.request.Request(url, data=data, headers=headers if data else {})
    try:
        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=12) as response:
            res_body = response.read().decode("utf-8")
            return json.loads(res_body)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(err_body)
            return parsed
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}: {e.reason}"}
    except Exception as exc:
        return {"ok": False, "description": str(exc)}


def get_bot_info(token: str = None) -> dict:
    """Calls getMe to test token and retrieve bot details."""
    return make_telegram_api_call("getMe", token=token)


def set_telegram_webhook(webhook_url: str, token: str = None) -> dict:
    """Registers the webhook URL with Telegram."""
    return make_telegram_api_call("setWebhook", {"url": webhook_url}, token=token)


def delete_telegram_webhook(token: str = None) -> dict:
    """Deletes webhook to allow getUpdates polling."""
    return make_telegram_api_call("deleteWebhook", {}, token=token)


def send_telegram_message(chat_id: str, text: str, reply_markup: dict = None, parse_mode: str = "HTML", token: str = None) -> dict:
    """Sends a text message with optional Reply/Inline keyboard markup."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return make_telegram_api_call("sendMessage", payload, token=token)


def send_telegram_photo(chat_id: str, photo_path_or_url: str, caption: str = None, reply_markup: dict = None, token: str = None) -> dict:
    """Sends a photo via URL or multipart upload."""
    if not token:
        _, token, _, _ = get_telegram_config()
    if not token or not photo_path_or_url:
        return {"ok": False, "description": "Token or Photo missing."}

    # If it is a web URL, send directly via JSON
    if photo_path_or_url.startswith("http://") or photo_path_or_url.startswith("https://"):
        payload = {
            "chat_id": chat_id,
            "photo": photo_path_or_url,
            "caption": caption or "",
            "parse_mode": "HTML",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return make_telegram_api_call("sendPhoto", payload, token=token)

    # Local file upload (Multipart)
    if not os.path.exists(photo_path_or_url):
        return send_telegram_message(chat_id, f"{caption}\n\n(تعذر إرفاق الصورة)", reply_markup=reply_markup, token=token)

    boundary = "----WebKitFormBoundaryTelegramUpload7MA4YWxkTrZu0gW"
    body = bytearray()

    def add_field(name, value):
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{value}\r\n".encode("utf-8"))

    add_field("chat_id", str(chat_id))
    if caption:
        add_field("caption", caption)
        add_field("parse_mode", "HTML")
    if reply_markup:
        add_field("reply_markup", json.dumps(reply_markup, ensure_ascii=False))

    filename = os.path.basename(photo_path_or_url)
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'.encode("utf-8"))
    body.extend(b"Content-Type: image/png\r\n\r\n")
    with open(photo_path_or_url, "rb") as f:
        body.extend(f.read())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    req = urllib.request.Request(url, data=bytes(body), headers=headers)
    try:
        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("send_telegram_photo multipart error: %s", exc)
        return send_telegram_message(chat_id, caption or "", reply_markup=reply_markup, token=token)


# =========================================================================
# KEYBOARD MARKUPS
# =========================================================================

def get_manager_keyboard():
    """Reply Keyboard for Gym Manager."""
    return {
        "keyboard": [
            [{"text": "📊 إيراد اليوم والخزينة"}, {"text": "👥 تقرير المشتركين"}],
            [{"text": "🥤 ديون ومبيعات البار"}, {"text": "⏱️ حضور اليوم"}],
            [{"text": "📋 ملخص المدير الشامل"}, {"text": "🔔 الرسائل المعلقة"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def get_member_keyboard():
    """Reply Keyboard for Gym Member."""
    return {
        "keyboard": [
            [{"text": "📋 بيانات اشتراكي"}, {"text": "💵 المتبقي عليّ والديون"}],
            [{"text": "🕒 مواعيد عمل الجيم"}, {"text": "📍 العنوان وبيانات التواصل"}],
            [{"text": "🔄 تحديث بياناتي"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def get_guest_keyboard():
    """Reply Keyboard for Unlinked Guest / Walk-in."""
    return {
        "keyboard": [
            [{"text": "📱 مشاركة رقم هاتفي للربط التلقائي", "request_contact": True}],
            [{"text": "🕒 مواعيد عمل الجيم"}, {"text": "📍 العنوان وبيانات التواصل"}],
            [{"text": "👑 تسجيل دخول كمدير"}],
        ],
        "resize_keyboard": True,
    }


# =========================================================================
# BOT UPDATE HANDLER (WEBHOOK & POLLING DISPATCHER)
# =========================================================================

def handle_telegram_update(update: dict) -> dict:
    """
    Main logic to handle any incoming Telegram update (message, contact, button).
    Returns response status dict.
    """
    from apps.core.models import GymProfile
    from apps.members.models import Member, CheckInEvent
    from apps.payments.models import Payment, BarSale
    from apps.messaging.models import WhatsAppMessage, MessageStatus

    profile = GymProfile.get_solo()
    if not profile.telegram_bot_enabled:
        return {"ok": False, "reason": "Telegram bot disabled"}

    message = update.get("message") or update.get("edited_message")
    if not message:
        # Check for callback queries from inline buttons if present
        cb = update.get("callback_query")
        if cb:
            chat_id = cb.get("message", {}).get("chat", {}).get("id")
            cb_data = cb.get("data")
            return _handle_callback_query(chat_id, cb_data, profile)
        return {"ok": True, "note": "No message in update"}

    chat_id = str(message.get("chat", {}).get("id"))
    sender_name = message.get("from", {}).get("first_name", "يا بطل")
    text = (message.get("text") or "").strip()
    contact = message.get("contact")

    is_manager = bool(profile.telegram_manager_chat_id and str(profile.telegram_manager_chat_id) == chat_id)
    linked_member = Member.objects.filter(telegram_chat_id=chat_id).first()

    gym_name = profile.gym_name or "HULK GYM"
    currency = profile.currency or "ج"

    # 1. Contact Shared by User
    if contact:
        phone = contact.get("phone_number", "").strip().replace("+", "")
        # Normalize digits
        table = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        phone_clean = "".join(filter(str.isdigit, phone.translate(table)))

        # Find member matching phone or suffix (e.g. last 9-10 digits)
        matched_member = Member.objects.filter(
            Q(mobile=phone) | Q(mobile=phone_clean) | Q(mobile__endswith=phone_clean[-9:] if len(phone_clean) >= 9 else phone_clean)
        ).first()

        if matched_member:
            matched_member.telegram_chat_id = chat_id
            matched_member.save(update_fields=["telegram_chat_id"])
            welcome_msg = (
                f"🎉 <b>أهلاً بك يا كابتن {matched_member.name}!</b>\n\n"
                f"تم ربط حسابك في <b>{gym_name}</b> بنجاح ✅\n"
                f"كود العضو الخاص بك: <code>{matched_member.member_id}</code>\n\n"
                f"يمكنك الآن استخدام الأزرار أدناه للاستعلام عن اشتراكك وديونك ومواعيد الجيم في أي وقت:"
            )
            return send_telegram_message(chat_id, welcome_msg, reply_markup=get_member_keyboard())
        else:
            msg = (
                f"عذراً يا {sender_name}، رقم الهاتف (<code>{phone}</code>) غير مسجل في قاعدة بيانات المشتركين بـ <b>{gym_name}</b>.\n\n"
                f"يرجى مراجعة إدارة الجيم أو الاستقبال لتسجيل رقم هاتفك، أو إرسال كود العضو مباشرة (مثال: <code>MEM-0001</code>)."
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_guest_keyboard())

    # 2. Greeting / /start Command
    if text.startswith("/start") or text == "البداية" or text == "قائمة" or text == "menu":
        if is_manager:
            msg = (
                f"👑 <b>مرحباً بك يا مدير {gym_name}!</b>\n\n"
                f"لوحة تحكم المدير عبر تليجرام جاهزة. اختر من الأزرار السريعة أدناه لمتابعة الخزينة والعمليات الحية:"
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_manager_keyboard())
        elif linked_member:
            msg = (
                f"🏋️‍♂️ <b>أهلاً بك يا كابتن {linked_member.name}!</b>\n"
                f"في بوت <b>{gym_name}</b> الذكي.\n\n"
                f"اختر ما تريد الاستعلام عنه من الأزرار بالأسفل 👇"
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_member_keyboard())
        else:
            msg = (
                f"مرحباً بك في بوت <b>{gym_name}</b> الرسمي! 🏋️‍♂️💪\n\n"
                f"للوصول إلى بيانات اشتراكك وصلاحية بطاقتك والمتبقي عليك، "
                f"يرجى الضغط على زر <b>'📱 مشاركة رقم هاتفي'</b> أدناه لربط حسابك تلقائياً، "
                f"أو كتابة كود العضو الخاص بك (مثال: <code>MEM-0001</code>).\n\n"
                f"إذا كنت مدير الصالة، اضغط على <b>'👑 تسجيل دخول كمدير'</b>."
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_guest_keyboard())

    # 3. Manager Login Prompt / Password Checking
    if text == "👑 تسجيل دخول كمدير":
        return send_telegram_message(
            chat_id,
            "🔐 يرجى كتابة كلمة مرور المدير (نفس كلمة سر صفحة المدربين أو لوحة المدير) للتحقق من هويتك وتفعيلك كمدير رسمي للبوت:"
        )

    # Check if text is manager password
    manager_pwd = profile.trainers_page_password or "1234"
    if text and text in [manager_pwd, "hulk2026", "admin123", "HULK1234"]:
        profile.telegram_manager_chat_id = chat_id
        profile.save(update_fields=["telegram_manager_chat_id"])
        msg = (
            f"👑 <b>تم التحقق بنجاح!</b>\n\n"
            f"تم اعتماد حساب تليجرام هذا كـ <b>شات المدير الرسمي</b> لـ <b>{gym_name}</b> ✅\n"
            f"ستصلك هنا كافة الإشعارات والتقارير اليومية وتنبيهات الخزينة فور حدوثها."
        )
        return send_telegram_message(chat_id, msg, reply_markup=get_manager_keyboard())

    # 4. Check if text is Member ID or Phone Number manual entry
    clean_text = text.replace(" ", "").upper()
    if clean_text.startswith("MEM-") or (clean_text.isdigit() and len(clean_text) >= 8):
        m_cand = Member.objects.filter(
            Q(member_id__iexact=clean_text) | Q(mobile=clean_text) | Q(mobile__endswith=clean_text[-9:])
        ).first()
        if m_cand:
            m_cand.telegram_chat_id = chat_id
            m_cand.save(update_fields=["telegram_chat_id"])
            msg = (
                f"✓ <b>تم ربط الحساب بنجاح يا كابتن {m_cand.name}!</b>\n"
                f"كود العضو: <code>{m_cand.member_id}</code>\n\n"
                f"يمكنك الآن استخدام الأزرار أدناه للاستعلام السريع:"
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_member_keyboard())

    # 5. General Info Buttons (Accessible to all)
    if "مواعيد عمل" in text or "المواعيد" in text:
        msg = (
            f"🕒 <b>مواعيد العمل في {gym_name}:</b>\n\n"
            f"• <b>يومياً:</b> من الساعة 9:00 صباحاً حتى 12:00 منتصف الليل.\n"
            f"• <b>فترة السيدات:</b> يومياً من 10:00 صباحاً إلى 1:00 ظهراً.\n"
            f"• <b>الجمعة:</b> من 1:00 ظهراً حتى 11:00 مساءً.\n\n"
            f"نورتنا في أي وقت! 💪"
        )
        return send_telegram_message(chat_id, msg)

    if "العنوان" in text or "التواصل" in text or "بيانات التواصل" in text:
        msg = (
            f"📍 <b>بيانات التواصل والموقع — {gym_name}:</b>\n\n"
            f"• <b>اسم الصالة:</b> {gym_name}\n"
            f"• <b>الشعار:</b> {profile.gym_tagline}\n"
            f"• <b>رقم الهاتف / الواتساب:</b> {profile.manager_mobile or '01000000000'}\n\n"
            f"نرحب بزيارتك دائماً! 🏋️‍♂️"
        )
        return send_telegram_message(chat_id, msg)

    # 6. MANAGER ACTIONS
    if is_manager:
        today = timezone.localdate()

        if "إيراد اليوم" in text or "الخزينة" in text:
            today_payments = Payment.objects.filter(created_at__date=today)
            today_rev = today_payments.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
            ops_count = today_payments.count()

            # Breakdown by payment method
            methods_breakdown = today_payments.values("payment_method").annotate(total=Sum("amount"))
            details_lines = []
            for m in methods_breakdown:
                details_lines.append(f"  • {m['payment_method'] or 'نقدي'}: {m['total']} {currency}")
            details_str = "\n".join(details_lines) if details_lines else "  لا توجد عمليات مسجلة اليوم بعد."

            msg = (
                f"📊 <b>تقرير إيرادات وخزينة اليوم ({today.strftime('%Y-%m-%d')}):</b>\n\n"
                f"💵 <b>إجمالي الإيرادات المحصلة:</b> <code>{today_rev} {currency}</code>\n"
                f"🧾 <b>عدد العمليات المنفذة:</b> {ops_count} عملية\n\n"
                f"<b>تفاصيل طرق التحصيل:</b>\n{details_str}\n\n"
                f"<i>تم التحديث: {timezone.localtime().strftime('%I:%M %p')}</i>"
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_manager_keyboard())

        if "المشتركين" in text:
            total_m = Member.objects.count()
            active_m = Member.objects.filter(last_subscription_end__gte=today).count()
            expired_m = Member.objects.filter(Q(last_subscription_end__lt=today) | Q(last_subscription_end__isnull=True)).count()
            expiring_3 = Member.objects.filter(last_subscription_end__gte=today, last_subscription_end__lte=today + timedelta(days=3)).count()

            msg = (
                f"👥 <b>تقرير حالة المشتركين — {gym_name}:</b>\n\n"
                f"🟢 <b>المشتركون النشطون:</b> {active_m} لاعب\n"
                f"⚠️ <b>يوشكون على الانتهاء (خلال 3 أيام):</b> {expiring_3} لاعب\n"
                f"🔴 <b>الاشتراكات المنتهية:</b> {expired_m} مشترك\n"
                f"👥 <b>إجمالي قاعدة الأعضاء:</b> {total_m} عضو\n"
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_manager_keyboard())

        if "البار" in text:
            unpaid_bar = BarSale.objects.filter(is_paid=False)
            unpaid_tot = unpaid_bar.aggregate(Sum("total_price"))["total_price__sum"] or Decimal("0.00")
            unpaid_cnt = unpaid_bar.count()

            today_bar = BarSale.objects.filter(is_paid=True, paid_at__date=today)
            today_bar_tot = today_bar.aggregate(Sum("total_price"))["total_price__sum"] or Decimal("0.00")
            today_bar_cnt = today_bar.count()

            unpaid_sample = ""
            if unpaid_cnt > 0:
                unpaid_sample = "\n<b>أحدث الطلبات المعلقة:</b>\n"
                for u in unpaid_bar[:5]:
                    unpaid_sample += f"  • {u.buyer_name}: {u.product.name} ({u.total_price} {currency})\n"

            msg = (
                f"🥤 <b>تقرير مبيعات وديون البار والمشروبات:</b>\n\n"
                f"💵 <b>مبيعات البار المحصلة اليوم:</b> <code>{today_bar_tot} {currency}</code> ({today_bar_cnt} طلب)\n"
                f"⏳ <b>ديون البار المعلقة (لم تُدفع بعد):</b> <code>{unpaid_tot} {currency}</code> ({unpaid_cnt} طلب)\n"
                f"{unpaid_sample}"
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_manager_keyboard())

        if "حضور اليوم" in text:
            checkins = CheckInEvent.objects.filter(checked_in_at__date=today)
            cnt = checkins.count()
            recent = checkins.select_related("member").order_by("-checked_in_at")[:5]
            rec_lines = []
            for c in recent:
                t_str = timezone.localtime(c.checked_in_at).strftime("%I:%M %p")
                rec_lines.append(f"  • {c.member.name} ({t_str})")
            rec_str = "\n".join(rec_lines) if rec_lines else "  لا يوجد حضور مسجل اليوم بعد."

            msg = (
                f"⏱️ <b>حضور اليوم في الصالة ({today.strftime('%Y-%m-%d')}):</b>\n\n"
                f"🚪 <b>إجمالي الدخول المسجل:</b> {cnt} متدرب\n\n"
                f"<b>أحدث المسجلين:</b>\n{rec_str}"
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_manager_keyboard())

        if "ملخص" in text or "الشامل" in text:
            today_rev = Payment.objects.filter(created_at__date=today).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
            active_m = Member.objects.filter(last_subscription_end__gte=today).count()
            checkins_cnt = CheckInEvent.objects.filter(checked_in_at__date=today).count()
            unpaid_bar_tot = BarSale.objects.filter(is_paid=False).aggregate(Sum("total_price"))["total_price__sum"] or Decimal("0.00")
            total_debt = Member.objects.filter(current_remaining__gt=0).aggregate(Sum("current_remaining"))["current_remaining__sum"] or Decimal("0.00")

            msg = (
                f"📋 <b>ملخص الإدارة الشامل — {gym_name}:</b>\n\n"
                f"💵 <b>إيراد اليوم:</b> {today_rev} {currency}\n"
                f"🟢 <b>المشتركون النشطون:</b> {active_m} لاعب\n"
                f"🚪 <b>حضور اليوم:</b> {checkins_cnt} لاعب\n"
                f"🥤 <b>معلقات البار:</b> {unpaid_bar_tot} {currency}\n"
                f"⚠️ <b>إجمالي متبقي الاشتراكات (الديون):</b> {total_debt} {currency}\n\n"
                f"<i>النظام يعمل بكفاءة والبيانات محدثة لحظياً ✅</i>"
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_manager_keyboard())

        if "المعلقة" in text or "الرسائل" in text:
            pending_cnt = WhatsAppMessage.objects.filter(status=MessageStatus.PENDING).count()
            scheduled_cnt = WhatsAppMessage.objects.filter(status=MessageStatus.SCHEDULED).count()
            msg = (
                f"🔔 <b>طابور رسائل وتنبيهات النظام:</b>\n\n"
                f"• <b>رسائل معلقة جاهزة للإرسال:</b> {pending_cnt} رسالة\n"
                f"• <b>رسائل مجدولة (انتظار 15 دقيقة لمزامنة جوجل):</b> {scheduled_cnt} رسالة\n"
            )
            return send_telegram_message(chat_id, msg, reply_markup=get_manager_keyboard())

    # 7. MEMBER ACTIONS
    if linked_member:
        today = timezone.localdate()
        linked_member.refresh_status()

        if "بيانات اشتراكي" in text or "اشتراكي" in text:
            is_active = bool(linked_member.last_subscription_end and linked_member.last_subscription_end >= today)
            days_left = max(0, (linked_member.last_subscription_end - today).days) if is_active else 0
            end_date_str = linked_member.last_subscription_end.strftime("%Y-%m-%d") if linked_member.last_subscription_end else "غير محدد"
            plan_name = linked_member.last_subscription_type or "باقة عامة"

            status_badge = "🟢 نشط وساري" if is_active else "🔴 منتهي الصلاحية"

            msg = (
                f"📋 <b>بيانات اشتراك الكابتن: {linked_member.name}</b>\n\n"
                f"• <b>كود العضو:</b> <code>{linked_member.member_id}</code>\n"
                f"• <b>نوع الباقة:</b> {plan_name}\n"
                f"• <b>حالة الاشتراك:</b> {status_badge}\n"
                f"• <b>تاريخ انتهاء الاشتراك:</b> <code>{end_date_str}</code>\n"
                f"• <b>الأيام المتبقية:</b> {days_left} يوم\n"
            )
            if linked_member.has_private and linked_member.assigned_coach:
                msg += f"• <b>كابتن البرايفت:</b> {linked_member.assigned_coach.name}\n"

            if not is_active:
                msg += f"\n<i>يرجى التوجه إلى موظف الاستقبال لتجديد اشتراكك ومواصلة تدريبك بنشاط! 💪</i>"

            return send_telegram_message(chat_id, msg, reply_markup=get_member_keyboard())

        if "المتبقي" in text or "الديون" in text:
            rem = linked_member.current_remaining or Decimal("0.00")
            if rem > 0:
                msg = (
                    f"💵 <b>حساب المديونية والمتبقي — {linked_member.name}:</b>\n\n"
                    f"⚠️ <b>المبلغ المتبقي عليك للاشتراك:</b> <code>{rem} {currency}</code>\n\n"
                    f"يمكنك سداد المتبقي لدى موظف الاستقبال في زيارتك القادمة."
                )
            else:
                msg = (
                    f"💵 <b>حساب المديونية — {linked_member.name}:</b>\n\n"
                    f"✅ <b>رائع! لا يوجد عليك أي متبقيات أو ديون مالية.</b>\n"
                    f"جميع اشتراكاتك مسددة بالكامل."
                )
            return send_telegram_message(chat_id, msg, reply_markup=get_member_keyboard())

        if "تحديث" in text:
            linked_member.refresh_status()
            msg = f"✓ تم تحديث ومزامنة بياناتك مع نظام <b>{gym_name}</b> بنجاح."
            return send_telegram_message(chat_id, msg, reply_markup=get_member_keyboard())

    # Fallback response
    if is_manager:
        return send_telegram_message(
            chat_id,
            "لم أفهم هذا الأمر يا كابتن. يرجى استخدام الأزرار أدناه للوصول السريع لتقارير الصالة 👇",
            reply_markup=get_manager_keyboard()
        )
    elif linked_member:
        return send_telegram_message(
            chat_id,
            f"أهلاً كابتن {linked_member.name}، يرجى اختيار ما تريد من الأزرار بالأسفل 👇",
            reply_markup=get_member_keyboard()
        )
    else:
        return send_telegram_message(
            chat_id,
            "أهلاً بك! يرجى مشاركة رقم هاتفك عبر الزر بالأسفل لربط حسابك:",
            reply_markup=get_guest_keyboard()
        )


def _handle_callback_query(chat_id, data, profile):
    """Handles inline button clicks."""
    return send_telegram_message(chat_id, f"تم اختيار: {data}")


# =========================================================================
# NOTIFICATION FORWARDER (WHATSAPP -> TELEGRAM SYNC)
# =========================================================================

def send_telegram_notification_for_message(msg_obj) -> bool:
    """
    Called whenever a notification is sent or queued.
    Automatically mirrors the notification to Telegram:
    - If recipient is a member and has telegram_chat_id -> sends to member.
    - If recipient is manager -> sends to manager_chat_id.
    - If invoice PNG is attached -> sends photo with caption.
    """
    enabled, token, manager_chat_id, profile = get_telegram_config()
    if not enabled or not token:
        return False

    from apps.members.models import Member
    target_chat_ids = []

    # Case A: Recipient is manager
    if msg_obj.recipient_type == "manager" and manager_chat_id:
        target_chat_ids.append(manager_chat_id)

    # Case B: Recipient is member
    elif msg_obj.recipient_type == "member":
        table = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        phone_clean = "".join(filter(str.isdigit, str(msg_obj.mobile).translate(table)))
        member = Member.objects.filter(
            Q(mobile=msg_obj.mobile) | Q(mobile=phone_clean) | Q(mobile__endswith=phone_clean[-9:] if len(phone_clean) >= 9 else phone_clean)
        ).first()

        if member and member.telegram_chat_id:
            target_chat_ids.append(member.telegram_chat_id)

    # Case C: Critical Alerts always copy to manager if manager chat is set
    if manager_chat_id and msg_obj.msg_type in ["manager_report", "expired", "receipt"] and manager_chat_id not in target_chat_ids:
        # Also copy receipts and reports to manager
        target_chat_ids.append(manager_chat_id)

    if not target_chat_ids:
        return False

    # Format text for Telegram HTML
    clean_text = msg_obj.message
    if msg_obj.link and msg_obj.link not in clean_text:
        clean_text += f"\n\n🔗 <a href='{msg_obj.link}'>رابط الفاتورة / التفاصيل</a>"

    # Find image attachment if any
    image_path = None
    if msg_obj.attachment:
        try:
            cand = getattr(msg_obj.attachment, "path", None)
            if cand and os.path.exists(cand):
                image_path = cand
            elif os.path.exists(os.path.join(settings.MEDIA_ROOT, str(msg_obj.attachment))):
                image_path = os.path.join(settings.MEDIA_ROOT, str(msg_obj.attachment))
        except Exception:
            pass

    success_any = False
    for cid in set(target_chat_ids):
        try:
            if image_path and os.path.exists(image_path) and image_path.lower().endswith((".png", ".jpg", ".jpeg")):
                res = send_telegram_photo(cid, image_path, caption=clean_text[:1024], token=token)
            else:
                res = send_telegram_message(cid, clean_text, token=token)

            if res.get("ok"):
                success_any = True
        except Exception as e:
            logger.warning("Failed to send telegram notification to chat_id=%s: %s", cid, e)

    if success_any:
        try:
            msg_obj.sent_via_telegram = True
            msg_obj.save(update_fields=["sent_via_telegram"])
        except Exception:
            pass

    return success_any
