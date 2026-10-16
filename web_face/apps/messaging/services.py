import os
import logging
from datetime import timedelta, date
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Q

from apps.core.models import GymProfile
from apps.members.models import Member, Subscription
from apps.payments.models import Payment
from apps.expenses.models import Expense
from apps.messaging.models import WhatsAppMessage, MessageStatus, MessageType

logger = logging.getLogger(__name__)


def enqueue_message(
    mobile: str,
    message: str,
    msg_type: str = MessageType.CUSTOM,
    recipient_name: str = "",
    recipient_type: str = "member",
    dedup_key: str = None,
    link: str = "",
    attachment = None,
) -> WhatsAppMessage:
    """
    Enqueues a message for WhatsApp delivery with deduplication, optional link and file attachment.
    """
    if not mobile or not message:
        return None

    # Clean phone number (strip whitespace, dashes, plus, arabic digits)
    table = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    cleaned_mobile = "".join(filter(str.isdigit, str(mobile).translate(table)))
    if not cleaned_mobile:
        return None

    if not dedup_key:
        dedup_key = f"{cleaned_mobile}_{msg_type}_{timezone.localdate().isoformat()}_{int(timezone.now().timestamp())}"

    existing = WhatsAppMessage.objects.filter(dedup_key=dedup_key).first()
    if existing:
        return existing

    msg_obj = WhatsAppMessage(
        mobile=cleaned_mobile,
        message=message.strip(),
        msg_type=msg_type,
        recipient_name=recipient_name.strip(),
        recipient_type=recipient_type,
        status=MessageStatus.PENDING,
        dedup_key=dedup_key,
        link=link.strip() if link else "",
    )
    if attachment:
        msg_obj.attachment = attachment
    msg_obj.save()
    return msg_obj


def dispatch_message_record(msg_obj: WhatsAppMessage, return_to_system: bool = False) -> bool:
    """
    Attempts delivery of a single WhatsApp message using whatsapp_sender on WhatsApp Desktop.
    Includes attached file/image and optional link formatting.
    """
    try:
        from apps.messaging import whatsapp_sender
        
        # Verify WhatsApp Desktop installation
        installed, inst_msg, _ = whatsapp_sender.is_whatsapp_desktop_installed()
        if not installed:
            msg_obj.status = MessageStatus.FAILED
            msg_obj.error_detail = inst_msg
            msg_obj.save()
            return False

        final_message = msg_obj.message
        if msg_obj.link and msg_obj.link not in final_message:
            final_message = f"{final_message}\n\n🔗 {msg_obj.link}"

        image_path = None
        if msg_obj.attachment:
            try:
                p = getattr(msg_obj.attachment, "path", None)
                if p and os.path.exists(p):
                    image_path = str(p)
            except Exception:
                pass

            if not image_path:
                try:
                    name = str(msg_obj.attachment)
                    cand = os.path.join(settings.MEDIA_ROOT, name)
                    if os.path.exists(cand):
                        image_path = os.path.abspath(cand)
                except Exception:
                    pass

            if not image_path:
                try:
                    name = str(msg_obj.attachment)
                    if os.path.exists(name):
                        image_path = os.path.abspath(name)
                except Exception:
                    pass

        # If attachment is an HTML invoice, resolve to companion PNG or generate it on the fly
        if image_path and image_path.lower().endswith(".html"):
            png_cand = image_path[:-5] + ".png"
            if os.path.exists(png_cand):
                image_path = png_cand
            else:
                try:
                    from apps.payments.models import Payment
                    from apps.payments.services import generate_invoice_image_file
                    base = os.path.splitext(os.path.basename(image_path))[0]
                    inv_no = base.replace("invoice_", "").replace("_", "/")
                    inv_no_alt = base.replace("invoice_", "")
                    p_match = Payment.objects.filter(Q(invoice_no__iexact=inv_no) | Q(invoice_no__iexact=inv_no_alt)).first()
                    if p_match:
                        rel_png = generate_invoice_image_file(p_match)
                        abs_png = os.path.join(settings.MEDIA_ROOT, rel_png)
                        if os.path.exists(abs_png):
                            image_path = abs_png
                except Exception as e:
                    logger.warning("Could not auto-generate PNG for invoice: %s", e)

        print(f"[dispatch_message_record] Sending msg id={msg_obj.id} to {msg_obj.mobile}, image_path={image_path}")

        profile = GymProfile.get_solo()
        success = whatsapp_sender.send_message(
            phone=msg_obj.mobile,
            message=final_message,
            image=image_path,
            x_search=profile.whatsapp_search_x,
            y_search=profile.whatsapp_search_y,
            return_to_system=return_to_system,
        )

        if success:
            msg_obj.status = MessageStatus.SENT
            msg_obj.sent_at = timezone.now()
            msg_obj.error_detail = ""
            msg_obj.save()
            return True
        else:
            msg_obj.status = MessageStatus.FAILED
            msg_obj.error_detail = "WhatsApp Desktop sender returned unsuccessful (window not active or chat not found)."
            msg_obj.save()
            return False
    except Exception as exc:
        logger.exception("Failed to dispatch WhatsApp message %s", msg_obj.id)
        msg_obj.status = MessageStatus.FAILED
        msg_obj.error_detail = str(exc)
        msg_obj.save()
        return False


def get_pending_summary() -> dict:
    """
    Returns total pending count and categorized breakdown for routine messages:
    - Invoices / Receipts (receipt)
    - 1 Last day reminder (reminder_1)
    - 3 Days reminder (reminder_3)
    - Finished / Expired subscription (expired)
    - Others / Custom (bulk, custom, etc.)
    """
    from apps.messaging import whatsapp_sender
    is_installed, inst_msg, _ = whatsapp_sender.is_whatsapp_desktop_installed()

    qs = WhatsAppMessage.objects.filter(status=MessageStatus.PENDING)
    total = qs.count()
    receipt_count = qs.filter(msg_type=MessageType.RECEIPT).count()
    reminder_1_count = qs.filter(msg_type=MessageType.REMINDER_1).count()
    reminder_3_count = qs.filter(msg_type=MessageType.REMINDER_3).count()
    expired_count = qs.filter(msg_type=MessageType.EXPIRED).count()
    other_count = max(0, total - (receipt_count + reminder_1_count + reminder_3_count + expired_count))

    return {
        "pending_count": total,
        "has_pending": total > 0,
        "desktop_installed": is_installed,
        "desktop_status": inst_msg,
        "breakdown": {
            "receipt": receipt_count,
            "reminder_1": reminder_1_count,
            "reminder_3": reminder_3_count,
            "expired": expired_count,
            "other": other_count,
        },
    }


def dispatch_all_pending(limit: int = 25, selected_ids: list = None, msg_type: str = None) -> dict:
    """
    Dispatches a batch of pending messages, optionally filtered by selected IDs or message type.
    Focuses WhatsApp once at batch start and returns to the system once when batch finishes.
    """
    import time
    from apps.messaging import whatsapp_sender

    # Pre-check WhatsApp Desktop installation
    is_installed, inst_msg, _ = whatsapp_sender.is_whatsapp_desktop_installed()
    if not is_installed:
        return {
            "processed": 0,
            "sent": 0,
            "failed": 0,
            "error": inst_msg,
            "desktop_installed": False,
        }

    qs = WhatsAppMessage.objects.filter(status=MessageStatus.PENDING)
    if selected_ids:
        qs = qs.filter(id__in=selected_ids)
    if msg_type and msg_type != "all":
        qs = qs.filter(msg_type=msg_type)

    pending = list(qs.order_by("created_at")[:limit])
    sent_count = 0
    failed_count = 0

    if pending:
        try:
            whatsapp_sender.whatsupp_ready()
        except Exception as e:
            logger.warning("whatsupp_ready batch init error: %s", e)

    for msg in pending:
        if dispatch_message_record(msg, return_to_system=False):
            sent_count += 1
        else:
            failed_count += 1
        time.sleep(0.5)

    if pending:
        try:
            whatsapp_sender.return_to_system_window()
        except Exception:
            pass

    return {
        "processed": len(pending),
        "sent": sent_count,
        "failed": failed_count,
        "desktop_installed": True,
    }


def prepare_due_reminders() -> dict:
    """
    Scans members and automatically queues reminders:
    - 3 days before expiration
    - 1 day before expiration
    - Already expired memberships
    """
    today = timezone.localdate()
    profile = GymProfile.get_solo()
    gym_name = profile.gym_name or "HULK GYM"

    members = Member.objects.filter(phone__isnull=False).exclude(phone="").select_related()
    queued_count = 0

    for m in members:
        m.refresh_status()
        end_date = m.last_subscription_end
        if not end_date:
            continue

        days_diff = (end_date - today).days

        # 1. Reminder 3 days before
        if days_diff == 3:
            dedup = f"{m.phone}_rem3_{end_date.isoformat()}"
            msg_text = (
                f"🏋️‍♂️ تذكير من {gym_name}\n"
                f"أهلاً كابتن {m.name} 👋\n"
                f"اشتراكك في الجيم هينتهي بعد 3 أيام (بتاريخ: {end_date.strftime('%Y-%m-%d')}).\n"
                f"جاهزين لتجديدك في أي وقت للاستمرار في فورمتك! 💪"
            )
            created = enqueue_message(
                mobile=m.phone,
                message=msg_text,
                msg_type=MessageType.REMINDER_3,
                recipient_name=m.name,
                dedup_key=dedup,
            )
            if created and created.status == MessageStatus.PENDING:
                queued_count += 1

        # 2. Reminder 1 day before
        elif days_diff == 1:
            dedup = f"{m.phone}_rem1_{end_date.isoformat()}"
            msg_text = (
                f"🏋️‍♂️ تذكير هام من {gym_name}\n"
                f"أهلاً كابتن {m.name} 👋\n"
                f"اشتراكك في الجيم هينتهي غداً (بتاريخ: {end_date.strftime('%Y-%m-%d')}).\n"
                f"تقدر تجدد مع كابتن الاستقبال اليوم عشان بوابتك تفضل شغالة بدون توقف! 🚀"
            )
            created = enqueue_message(
                mobile=m.phone,
                message=msg_text,
                msg_type=MessageType.REMINDER_1,
                recipient_name=m.name,
                dedup_key=dedup,
            )
            if created and created.status == MessageStatus.PENDING:
                queued_count += 1

        # 3. Already expired
        elif days_diff <= 0:
            dedup = f"{m.phone}_exp_{end_date.isoformat()}"
            template = profile.expired_message_template or (
                "تنبيه من {gym_name}\nأهلاً {name}\nاشتراكك انتهى بتاريخ: {end_date}\nنورتنا في أي وقت للتجديد والرجوع للتمرين 💪"
            )
            msg_text = template.format(
                gym_name=gym_name,
                name=m.name,
                end_date=end_date.strftime("%Y-%m-%d"),
                days_left=abs(days_diff),
            )
            created = enqueue_message(
                mobile=m.phone,
                message=msg_text,
                msg_type=MessageType.EXPIRED,
                recipient_name=m.name,
                dedup_key=dedup,
            )
            if created and created.status == MessageStatus.PENDING:
                queued_count += 1

    return {"queued": queued_count}


from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from apps.core.text_utils import reshape_arabic


def generate_manager_report_image_file(report_data: dict) -> str:
    """
    Renders an official executive graphical summary card (PNG) for the manager daily report.
    Saved to media/reports/manager_report_{date}_{ts}.png and returns the relative path.
    """
    reports_dir = Path(settings.MEDIA_ROOT) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    date_str = report_data.get("date_str", "")
    ts = int(timezone.now().timestamp())
    png_filename = f"manager_report_{date_str}_{ts}.png"
    png_file_path = reports_dir / png_filename

    w, h = 820, 1060
    # Rich dark background
    img = Image.new("RGB", (w, h), color=(11, 15, 25))
    draw = ImageDraw.Draw(img)

    # Outer border / card
    draw.rounded_rectangle([20, 20, w - 20, h - 20], radius=18, fill=(15, 23, 42), outline=(30, 41, 59), width=2)

    try:
        font_badge = ImageFont.truetype("tahomabd.ttf", 14)
        font_title = ImageFont.truetype("tahomabd.ttf", 26)
        font_sub = ImageFont.truetype("tahoma.ttf", 15)
        font_card_val = ImageFont.truetype("tahomabd.ttf", 22)
        font_card_lbl = ImageFont.truetype("tahomabd.ttf", 14)
        font_card_sub = ImageFont.truetype("tahoma.ttf", 13)
        font_sec_title = ImageFont.truetype("tahomabd.ttf", 17)
        font_normal = ImageFont.truetype("tahoma.ttf", 15)
        font_sm = ImageFont.truetype("tahoma.ttf", 13)
    except Exception:
        try:
            font_badge = ImageFont.truetype("arialbd.ttf", 14)
            font_title = ImageFont.truetype("arialbd.ttf", 26)
            font_sub = ImageFont.truetype("arial.ttf", 15)
            font_card_val = ImageFont.truetype("arialbd.ttf", 22)
            font_card_lbl = ImageFont.truetype("arialbd.ttf", 14)
            font_card_sub = ImageFont.truetype("arial.ttf", 13)
            font_sec_title = ImageFont.truetype("arialbd.ttf", 17)
            font_normal = ImageFont.truetype("arial.ttf", 15)
            font_sm = ImageFont.truetype("arial.ttf", 13)
        except Exception:
            font_badge = font_title = font_sub = font_card_val = font_card_lbl = font_card_sub = font_sec_title = font_normal = font_sm = ImageFont.load_default()

    gym_name = report_data.get("gym_name", "HULK GYM")
    curr = report_data.get("currency", "ج.م")

    # Header Top Badge
    draw.rounded_rectangle([w // 2 - 130, 35, w // 2 + 130, 65], radius=8, fill=(30, 41, 59), outline=(71, 85, 105), width=1)
    draw.text((w // 2, 50), reshape_arabic("تقرير الإدارة اليومي الرسمي"), fill=(251, 191, 36), font=font_badge, anchor="mm")

    # Gym Name
    draw.text((w // 2, 95), reshape_arabic(gym_name), fill=(163, 230, 53), font=font_title, anchor="mm")

    # Date & Time
    time_str = report_data.get("time_str", "")
    meta_str = reshape_arabic(f"تاريخ التقرير: {date_str}   |   وقت الإعداد: {time_str}")
    draw.text((w // 2, 130), meta_str, fill=(148, 163, 184), font=font_sub, anchor="mm")

    draw.line([(40, 155), (w - 40, 155)], fill=(30, 41, 59), width=1)

    # 4 Key Financial Stats (2x2 grid)
    card_w = (w - 100) // 2  # 360 px each
    card_h = 100

    cards = [
        {
            "x": 50,
            "y": 175,
            "bg": (20, 83, 45),
            "border": (34, 197, 94),
            "lbl": "إجمالي الإيرادات اليوم",
            "val": f"{report_data.get('total_revenue', 0)} {curr}",
            "sub": f"عدد عمليات التحصيل: {report_data.get('total_payments_count', 0)}",
            "val_color": (74, 222, 128),
        },
        {
            "x": 50 + card_w + 20,
            "y": 175,
            "bg": (127, 29, 29),
            "border": (239, 68, 68),
            "lbl": "إجمالي المصروفات اليوم",
            "val": f"{report_data.get('total_expenses', 0)} {curr}",
            "sub": "مصروفات الصالة المسجلة",
            "val_color": (248, 113, 113),
        },
        {
            "x": 50,
            "y": 290,
            "bg": (6, 78, 59),
            "border": (16, 185, 129),
            "lbl": "صافي الخزينة النقدية",
            "val": f"{report_data.get('net_cash', 0)} {curr}",
            "sub": "الإيراد بعد خصم المصروفات",
            "val_color": (52, 211, 153),
        },
        {
            "x": 50 + card_w + 20,
            "y": 290,
            "bg": (120, 53, 15),
            "border": (245, 158, 11),
            "lbl": "الخصومات الممنوحة اليوم",
            "val": f"{report_data.get('total_discounts_today', 0)} {curr}",
            "sub": "إجمالي الخصم على الاشتراكات",
            "val_color": (251, 191, 36),
        },
    ]

    for c in cards:
        draw.rounded_rectangle([c["x"], c["y"], c["x"] + card_w, c["y"] + card_h], radius=12, fill=c["bg"], outline=c["border"], width=1)
        draw.text((c["x"] + card_w // 2, c["y"] + 24), reshape_arabic(c["lbl"]), fill=(226, 232, 240), font=font_card_lbl, anchor="mm")
        draw.text((c["x"] + card_w // 2, c["y"] + 54), reshape_arabic(c["val"]), fill=c["val_color"], font=font_card_val, anchor="mm")
        draw.text((c["x"] + card_w // 2, c["y"] + 82), reshape_arabic(c["sub"]), fill=(203, 213, 225), font=font_card_sub, anchor="mm")

    # Section: Subscriptions & Private Sessions
    sy = 415
    draw.rounded_rectangle([40, sy, w - 40, sy + 250], radius=14, fill=(17, 24, 39), outline=(51, 65, 85), width=1)
    draw.text((w - 60, sy + 22), reshape_arabic("🏋️‍♂️ إحصائيات الاشتراكات والتدريب الخاص:"), fill=(56, 189, 248), font=font_sec_title, anchor="ra")

    draw.line([(55, sy + 48), (w - 55, sy + 48)], fill=(30, 41, 59), width=1)

    items = [
        ("اشتراكات جديدة ومجددة اليوم:", f"{report_data.get('new_subs_count', 0)} اشتراك"),
        ("حالات الدخول ببصمة الوجه اليوم:", f"{report_data.get('checkins_today_count', 0)} دخول"),
        ("اشتراكات التدريب الخاص (Private):", f"{report_data.get('private_count', 0)} اشتراك"),
        ("إجمالي دخل اشتراكات البرايفت:", f"{report_data.get('private_rev', 0)} {curr}"),
        ("عمولة الكباتن المستحقة عن اليوم:", f"{report_data.get('coaches_comm', 0)} {curr}"),
        ("صافي دخل الصالة من البرايفت:", f"{report_data.get('gym_private_profit', 0)} {curr}"),
    ]

    iy = sy + 62
    for label, val in items:
        draw.text((w - 65, iy), reshape_arabic(label), fill=(203, 213, 225), font=font_normal, anchor="ra")
        draw.text((65, iy), reshape_arabic(val), fill=(255, 255, 255), font=font_card_lbl)
        iy += 30

    # Section: Sensitive Operations & Audit
    ay = 685
    draw.rounded_rectangle([40, ay, w - 40, ay + 260], radius=14, fill=(17, 24, 39), outline=(51, 65, 85), width=1)
    draw.text((w - 60, ay + 22), reshape_arabic("🚨 رقابة العمليات الحساسة والتعديلات اليوم:"), fill=(251, 146, 60), font=font_sec_title, anchor="ra")

    draw.line([(55, ay + 48), (w - 55, ay + 48)], fill=(30, 41, 59), width=1)

    audit_lines = report_data.get("audit_lines", [])
    if not audit_lines:
        draw.text((w // 2, ay + 140), reshape_arabic("لا توجد عمليات حساسة أو استثنائية مسجلة اليوم ✓"), fill=(148, 163, 184), font=font_normal, anchor="mm")
    else:
        line_y = ay + 65
        for line in audit_lines[:5]:
            draw.text((w - 65, line_y), reshape_arabic(f"• {line}"), fill=(226, 232, 240), font=font_sm, anchor="ra")
            line_y += 36

    # Footer
    footer_text = reshape_arabic(f"تم إعداد وتوثيق التقرير آلياً بواسطة نظام {gym_name} الذكي")
    draw.text((w // 2, h - 35), footer_text, fill=(100, 116, 139), font=font_sm, anchor="mm")

    img.save(str(png_file_path), "PNG")
    logger.info("Generated manager report PNG at: %s", png_file_path)
    return f"reports/{png_filename}"


def prepare_manager_daily_report():
    """
    Compiles today's complete managerial report, renders executive graphics summary image,
    and enqueues to the manager mobile number with the report image attached.
    """
    profile = GymProfile.get_solo()
    manager_phone = profile.manager_mobile
    if not manager_phone:
        return None

    today = timezone.localdate()
    gym_name = profile.gym_name or "HULK GYM"

    # Daily financials
    payments_today = Payment.objects.filter(created_at__date=today)
    total_revenue = payments_today.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    total_payments_count = payments_today.count()

    # Expenses
    expenses_today = Expense.objects.filter(expense_date=today)
    total_expenses = expenses_today.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    # Net Cash
    net_cash = total_revenue - total_expenses

    # Subscriptions today
    subs_today = Subscription.objects.filter(created_at__date=today)
    new_subs_count = subs_today.count()

    # Discounts given today
    total_discounts_today = subs_today.aggregate(total=Sum("discount"))["total"] or Decimal("0.00")

    # Private Add-on details today
    private_subs_today = subs_today.filter(has_private=True)
    private_count = private_subs_today.count()
    private_rev = private_subs_today.aggregate(total=Sum("private_price"))["total"] or Decimal("0.00")
    coaches_comm = private_subs_today.aggregate(total=Sum("coach_commission_amount"))["total"] or Decimal("0.00")
    gym_private_profit = private_rev - coaches_comm

    # Audit Events today (Discounts, private toggling, price changes)
    from apps.core.models import AuditLog
    audit_today = AuditLog.objects.filter(created_at__date=today).order_by("-created_at")[:10]
    audit_count = audit_today.count()
    audit_section = ""
    audit_lines = []
    if audit_count > 0:
        for a in audit_today:
            time_str = timezone.localtime(a.created_at).strftime("%H:%M")
            user_str = a.user.username if a.user else "النظام"
            audit_lines.append(f"• [{time_str}] {a.details} (بواسطة: {user_str})")
        audit_section = (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🚨 *رقابة العمليات والتعديلات الحساسة ({audit_count})*:\n"
            + "\n".join(audit_lines) + "\n"
        )

    # Checkins today
    from apps.members.models import CheckInEvent
    checkins_today_count = CheckInEvent.objects.filter(checked_in_at__date=today).count()

    report_text = (
        f"📊 *تقرير الإدارة اليومي - {gym_name}*\n"
        f"📅 التاريخ: {today.strftime('%Y-%m-%d')}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 إجمالي الإيرادات اليوم: {total_revenue} ج.م ({total_payments_count} عملية دفع)\n"
        f"📉 إجمالي المصروفات اليوم: {total_expenses} ج.م\n"
        f"💵 صافي الخزينة: {net_cash} ج.م\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎁 إجمالي الخصومات الممنوحة اليوم: {total_discounts_today} ج.م\n"
        f"🏋️‍♂️ اشتراكات التدريب الخاص (Private): {private_count}\n"
        f"   └ إيراد البرايفت: {private_rev} ج.م\n"
        f"   └ عمولة الكباتن المستحقة: {coaches_comm} ج.م\n"
        f"   └ صافي دخل الصالة من البرايفت: {gym_private_profit} ج.م\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📝 اشتراكات جديدة / مجددة اليوم: {new_subs_count}\n"
        f"👤 حالات الدخول ببصمة الوجه اليوم: {checkins_today_count}\n"
        f"{audit_section}"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"مرفق بطاقة التقرير والإحصائيات الرسمية 📊\n"
        f"تم إعداد التقرير تلقائياً بواسطة نظام {gym_name} الذكي."
    )

    report_data = {
        "gym_name": gym_name,
        "currency": profile.currency or "ج.م",
        "date_str": today.strftime("%Y-%m-%d"),
        "time_str": timezone.localtime().strftime("%I:%M %p"),
        "total_revenue": total_revenue,
        "total_payments_count": total_payments_count,
        "total_expenses": total_expenses,
        "net_cash": net_cash,
        "total_discounts_today": total_discounts_today,
        "new_subs_count": new_subs_count,
        "private_count": private_count,
        "private_rev": private_rev,
        "coaches_comm": coaches_comm,
        "gym_private_profit": gym_private_profit,
        "checkins_today_count": checkins_today_count,
        "audit_lines": [f"[{timezone.localtime(a.created_at).strftime('%H:%M')}] {a.details} ({a.user.username if a.user else 'النظام'})" for a in audit_today[:5]],
    }

    rel_report_image = ""
    try:
        rel_report_image = generate_manager_report_image_file(report_data)
    except Exception as exc:
        logger.exception("Failed to generate manager report image: %s", exc)

    dedup = f"mgr_report_{today.isoformat()}_{int(timezone.now().timestamp())}"
    msg = enqueue_message(
        mobile=manager_phone,
        message=report_text,
        msg_type=MessageType.MANAGER_REPORT,
        recipient_name="إدارة الصالة",
        recipient_type="manager",
        dedup_key=dedup,
        attachment=rel_report_image or None,
    )
    return msg


def filter_members_for_bulk(
    category: str = "non_sub",
    date_from: date = None,
    date_to: date = None,
    preset_range: str = "all",
):
    """
    Filters members based on category, date range, or preset for bulk WhatsApp campaigns.
    """
    today = timezone.localdate()
    qs = Member.objects.filter(phone__isnull=False).exclude(phone="")

    if category == "non_sub":
        # Expired or no active subscription
        qs = qs.filter(Q(last_subscription_end__isnull=True) | Q(last_subscription_end__lt=today))

        if date_from and date_to:
            qs = qs.filter(last_subscription_end__gte=date_from, last_subscription_end__lte=date_to)
        elif date_from:
            qs = qs.filter(last_subscription_end__gte=date_from)
        elif date_to:
            qs = qs.filter(last_subscription_end__lte=date_to)
        elif preset_range == "week":
            # Expired in the last 7 days
            qs = qs.filter(last_subscription_end__gte=today - timedelta(days=7), last_subscription_end__lt=today)
        elif preset_range == "month":
            # Expired in the last 30 days
            qs = qs.filter(last_subscription_end__gte=today - timedelta(days=30), last_subscription_end__lt=today)
        elif preset_range == "3months":
            # Expired more than 90 days ago
            qs = qs.filter(last_subscription_end__lte=today - timedelta(days=90))

    elif category == "active":
        qs = qs.filter(last_subscription_end__gte=today)

    elif category == "expiring_soon":
        # Expiring within next 7 days
        qs = qs.filter(last_subscription_end__gte=today, last_subscription_end__lte=today + timedelta(days=7))

    elif category == "with_debt":
        # Calculate members who owe debt
        # We can filter members whose remaining is positive
        qs = qs.filter(id__in=[m.id for m in qs if m.has_debt])

    elif category == "all_members":
        # All members with phone
        pass

    return qs


def prepare_bulk_campaign(
    category: str = "non_sub",
    message_template: str = "",
    link: str = "",
    attachment = None,
    date_from: date = None,
    date_to: date = None,
    preset_range: str = "all",
) -> dict:
    """
    Prepares and enqueues bulk WhatsApp messages for the selected target category.
    """
    if not message_template.strip():
        return {"queued": 0, "error": "نص الرسالة مطلوب."}

    members = filter_members_for_bulk(
        category=category,
        date_from=date_from,
        date_to=date_to,
        preset_range=preset_range,
    )

    profile = GymProfile.get_solo()
    gym_name = profile.gym_name or "HULK GYM"
    today = timezone.localdate()
    queued_count = 0
    batch_tag = f"bulk_{category}_{today.isoformat()}_{int(timezone.now().timestamp())}"

    for m in members:
        m.refresh_status()
        end_date_str = m.last_subscription_end.strftime("%Y-%m-%d") if m.last_subscription_end else "غير محدد"
        days_diff = (m.last_subscription_end - today).days if m.last_subscription_end else 0

        # Replace tags
        text = message_template.replace("{name}", m.name or "كابتن")
        text = text.replace("{gym_name}", gym_name)
        text = text.replace("{end_date}", end_date_str)
        text = text.replace("{days_left}", str(abs(days_diff)))
        text = text.replace("{remaining}", str(m.current_remaining))
        text = text.replace("{plan}", m.last_subscription_type or "الاشتراك")

        dedup = f"{m.phone}_{batch_tag}"
        msg = enqueue_message(
            mobile=m.phone,
            message=text,
            msg_type=MessageType.BULK,
            recipient_name=m.name,
            recipient_type="member",
            dedup_key=dedup,
            link=link,
            attachment=attachment,
        )
        if msg:
            queued_count += 1

    return {"queued": queued_count, "total_target": len(members)}
