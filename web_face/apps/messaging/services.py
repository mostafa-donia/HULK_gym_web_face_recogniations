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


NEW_MEMBER_SYNC_DELAY_MINUTES = 15


def promote_due_scheduled_messages() -> int:
    """
    Promotes any SCHEDULED messages whose 15-minute Google Contacts sync delay
    has elapsed (send_after <= now) to PENDING so they are ready for dispatch.
    """
    now = timezone.now()
    return WhatsAppMessage.objects.filter(
        status=MessageStatus.SCHEDULED,
    ).filter(
        Q(send_after__lte=now) | Q(send_after__isnull=True)
    ).update(status=MessageStatus.PENDING)


def get_first_time_send_after(mobile: str, member: Member = None):
    """
    If a new member's phone number was recently added (or not yet synced to Google Contacts)
    and no WhatsApp message has ever been SENT to this number before, schedules the first
    message(s) for 15 minutes after the contact addition/sync so Google Contacts syncs to WhatsApp.
    """
    if not mobile:
        return None

    table = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    cleaned_mobile = "".join(filter(str.isdigit, str(mobile).translate(table)))
    if not cleaned_mobile:
        return None

    # If any message was already sent to this phone number before, no delay needed
    already_sent = WhatsAppMessage.objects.filter(
        Q(mobile=mobile) | Q(mobile=cleaned_mobile),
        status=MessageStatus.SENT,
    ).exists()
    if already_sent:
        return None

    if member is None:
        member = Member.objects.filter(
            Q(mobile=mobile) | Q(mobile=cleaned_mobile)
        ).order_by("-created_at").first()

    if not member:
        return None

    now = timezone.now()

    # If member is not yet synced to Google Contacts, trigger sync now and schedule 15 min later
    if member.google_contact_synced_at is None:
        try:
            from apps.core.google_contacts import trigger_async_member_google_sync
            trigger_async_member_google_sync(member)
        except Exception:
            pass
        return now + timedelta(minutes=NEW_MEMBER_SYNC_DELAY_MINUTES)

    # Otherwise check if member was created or synced within the last 15 minutes
    timestamps = [t for t in [member.google_contact_synced_at, member.created_at] if t is not None]
    ref_time = max(timestamps) if timestamps else now
    target_time = ref_time + timedelta(minutes=NEW_MEMBER_SYNC_DELAY_MINUTES)
    if target_time > now:
        return target_time

    return None


def enqueue_message(
    mobile: str,
    message: str,
    msg_type: str = MessageType.CUSTOM,
    recipient_name: str = "",
    recipient_type: str = "member",
    dedup_key: str = None,
    link: str = "",
    attachment = None,
    member: Member = None,
) -> WhatsAppMessage:
    """
    Enqueues a message for WhatsApp delivery with deduplication, optional link and file attachment.
    Automatically schedules first-time messages to newly added member phone numbers 15 minutes later.
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

    send_after = None
    initial_status = MessageStatus.PENDING
    if recipient_type == "member":
        send_after = get_first_time_send_after(cleaned_mobile, member=member)
        if send_after and send_after > timezone.now():
            initial_status = MessageStatus.SCHEDULED

    msg_obj = WhatsAppMessage(
        mobile=cleaned_mobile,
        message=message.strip(),
        msg_type=msg_type,
        recipient_name=recipient_name.strip(),
        recipient_type=recipient_type,
        status=initial_status,
        send_after=send_after,
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

        # Always regenerate the latest PNG on the fly for invoice attachments so Arabic shaping and details are fresh
        if image_path and ("invoice_" in os.path.basename(image_path).lower() or image_path.lower().endswith(".html")):
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
                        image_path = os.path.abspath(abs_png)
            except Exception as e:
                logger.warning("Could not auto-generate PNG for invoice: %s", e)
                if image_path.lower().endswith(".html") and os.path.exists(image_path[:-5] + ".png"):
                    image_path = image_path[:-5] + ".png"

        profile = GymProfile.get_solo()
        gym_name = profile.gym_name or "سينا سبا | CINA SPA"

        # Ensure gym name is clearly displayed in message text if not already included
        if gym_name not in final_message:
            final_message = f"{final_message}\n\n🏢 *{gym_name}*"

        # If no specific invoice or report attachment is present, attach the gym logo if available!
        if not image_path:
            logo_p = profile.get_logo_image_path() if hasattr(profile, "get_logo_image_path") else None
            if logo_p and os.path.exists(logo_p):
                image_path = logo_p

        print(f"[dispatch_message_record] Sending msg id={msg_obj.id} to {msg_obj.mobile}, image_path={image_path}")

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

            # Mirror notification to Telegram as requested
            try:
                from apps.messaging.telegram_bot import send_telegram_notification_for_message
                send_telegram_notification_for_message(msg_obj)
            except Exception as e:
                logger.warning("Telegram notification mirror error: %s", e)

            return True
        else:
            if getattr(whatsapp_sender, "KILL_SWITCH_REQUESTED", False):
                msg_obj.status = MessageStatus.PENDING
                msg_obj.error_detail = "تم إيقاف الإرسال بواسطة زر الطوارئ (Ctrl+K). الرسالة معلقة وجاهزة للاستئناف في أي وقت."
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
    promote_due_scheduled_messages()
    try:
        prepare_due_reminders()
    except Exception as e:
        logger.warning("Auto prepare_due_reminders in get_pending_summary error: %s", e)

    from apps.messaging import whatsapp_sender
    is_installed, inst_msg, _ = whatsapp_sender.is_whatsapp_desktop_installed()

    qs = WhatsAppMessage.objects.filter(status=MessageStatus.PENDING)
    total = qs.count()
    scheduled_count = WhatsAppMessage.objects.filter(status=MessageStatus.SCHEDULED).count()
    receipt_count = qs.filter(msg_type=MessageType.RECEIPT).count()
    reminder_1_count = qs.filter(msg_type=MessageType.REMINDER_1).count()
    reminder_3_count = qs.filter(msg_type=MessageType.REMINDER_3).count()
    expired_count = qs.filter(msg_type=MessageType.EXPIRED).count()
    other_count = max(0, total - (receipt_count + reminder_1_count + reminder_3_count + expired_count))

    return {
        "pending_count": total,
        "scheduled_count": scheduled_count,
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

    promote_due_scheduled_messages()

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

    if selected_ids:
        qs = WhatsAppMessage.objects.filter(
            id__in=selected_ids,
            status__in=[MessageStatus.PENDING, MessageStatus.SCHEDULED],
        )
    else:
        qs = WhatsAppMessage.objects.filter(status=MessageStatus.PENDING)
    if msg_type and msg_type != "all":
        qs = qs.filter(msg_type=msg_type)

    pending = list(qs.order_by("created_at")[:limit])
    sent_count = 0
    failed_count = 0

    whatsapp_sender.reset_kill_switch()

    if pending:
        try:
            whatsapp_sender.whatsupp_ready()
        except Exception as e:
            logger.warning("whatsupp_ready batch init error: %s", e)

    for msg in pending:
        if getattr(whatsapp_sender, "KILL_SWITCH_REQUESTED", False):
            logger.info("Batch dispatch aborted by emergency kill switch.")
            break
        if dispatch_message_record(msg, return_to_system=False):
            sent_count += 1
        else:
            if getattr(whatsapp_sender, "KILL_SWITCH_REQUESTED", False):
                logger.info("Message %s aborted by kill switch, halting queue.", msg.id)
                break
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
    gym_name = profile.gym_name or "سينا سبا | CINA SPA"

    members = Member.objects.filter(mobile__isnull=False).exclude(mobile="").select_related()
    queued_count = 0

    for m in members:
        # Skip frozen / paused subscriptions from receiving expiry reminders
        if getattr(m, "is_frozen", False):
            continue

        m.refresh_status()
        end_date = m.last_subscription_end
        if not end_date:
            continue

        days_diff = (end_date - today).days

        # Deduplication check: Ensure member never receives multiple reminder messages on the same day
        already_reminded_today = WhatsAppMessage.objects.filter(
            mobile=m.mobile,
            created_at__date=today,
            msg_type__in=[MessageType.REMINDER_3, MessageType.REMINDER_1, MessageType.EXPIRED],
        ).exists()
        if already_reminded_today:
            continue

        from apps.messaging.message_bank import get_random_message, format_template_safely

        # 1. Reminder exactly 3 days before
        if days_diff == 3:
            dedup = f"{m.mobile}_rem3_{end_date.isoformat()}"
            ctx = {
                "name": m.name,
                "gym_name": gym_name,
                "end_date": end_date.strftime("%Y-%m-%d"),
                "days_left": 3,
                "plan": m.last_subscription_type or "الاشتراك",
                "phone": m.mobile,
            }
            if getattr(profile, "whatsapp_randomize_templates", True):
                msg_text = get_random_message("reminder_3", ctx)
            else:
                msg_text = (
                    f"🏋️‍♂️ تذكير من {gym_name}\n"
                    f"أهلاً كابتن {m.name} 👋\n"
                    f"اشتراكك في الجيم هينتهي بعد 3 أيام (بتاريخ: {end_date.strftime('%Y-%m-%d')}).\n"
                    f"جاهزين لتجديدك في أي وقت للاستمرار في فورمتك! 💪"
                )
            created = enqueue_message(
                mobile=m.mobile,
                message=msg_text,
                msg_type=MessageType.REMINDER_3,
                recipient_name=m.name,
                dedup_key=dedup,
            )
            if created and created.status == MessageStatus.PENDING:
                queued_count += 1

        # 2. Reminder exactly 1 day before
        elif days_diff == 1:
            dedup = f"{m.mobile}_rem1_{end_date.isoformat()}"
            ctx = {
                "name": m.name,
                "gym_name": gym_name,
                "end_date": end_date.strftime("%Y-%m-%d"),
                "days_left": 1,
                "plan": m.last_subscription_type or "الاشتراك",
                "phone": m.mobile,
            }
            if getattr(profile, "whatsapp_randomize_templates", True):
                msg_text = get_random_message("reminder_1", ctx)
            else:
                msg_text = (
                    f"🏋️‍♂️ تذكير هام من {gym_name}\n"
                    f"أهلاً كابتن {m.name} 👋\n"
                    f"اشتراكك في الجيم هينتهي غداً (بتاريخ: {end_date.strftime('%Y-%m-%d')}).\n"
                    f"تقدر تجدد مع كابتن الاستقبال اليوم عشان بوابتك تفضل شغالة بدون توقف! 🚀"
                )
            created = enqueue_message(
                mobile=m.mobile,
                message=msg_text,
                msg_type=MessageType.REMINDER_1,
                recipient_name=m.name,
                dedup_key=dedup,
            )
            if created and created.status == MessageStatus.PENDING:
                queued_count += 1

        # 3. Subscription Expired (Today or Yesterday only - avoids spamming members expired long ago)
        elif days_diff in [0, -1]:
            dedup = f"{m.mobile}_exp_{end_date.isoformat()}"
            ctx = {
                "name": m.name,
                "gym_name": gym_name,
                "end_date": end_date.strftime("%Y-%m-%d"),
                "days_left": abs(days_diff),
                "plan": m.last_subscription_type or "الاشتراك",
                "phone": m.mobile,
            }
            custom_tmpl = (profile.expired_message_template or "").strip()
            if getattr(profile, "whatsapp_randomize_templates", True):
                msg_text = get_random_message("expired", ctx)
            elif custom_tmpl and "---" in custom_tmpl:
                choices = [c.strip() for c in custom_tmpl.split("---") if c.strip()]
                msg_text = format_template_safely(random.choice(choices), ctx)
            elif custom_tmpl:
                msg_text = format_template_safely(custom_tmpl, ctx)
            else:
                msg_text = get_random_message("expired", ctx)

            created = enqueue_message(
                mobile=m.mobile,
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
    Comprehensive high-DPI card with zero missing-glyph boxes (□), beautiful native vector badges,
    Financial KPIs, Subscriptions, Gym AI Tactical Actions & Audit Log.
    """
    reports_dir = Path(settings.MEDIA_ROOT) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    date_str = report_data.get("date_str", "")
    ts = int(timezone.now().timestamp())
    png_filename = f"manager_report_{date_str}_{ts}.png"
    png_file_path = reports_dir / png_filename

    w, h = 860, 1080
    img = Image.new("RGB", (w, h), color=(11, 15, 25))
    draw = ImageDraw.Draw(img)

    from apps.core.text_utils import get_arabic_font, reshape_arabic
    font_badge = get_arabic_font(size=14, bold=True)
    font_gym = get_arabic_font(size=28, bold=True)
    font_meta = get_arabic_font(size=14, bold=False)
    font_sec = get_arabic_font(size=16, bold=True)
    font_card_val = get_arabic_font(size=22, bold=True)
    font_card_lbl = get_arabic_font(size=14, bold=True)
    font_card_sub = get_arabic_font(size=12, bold=False)
    font_item_lbl = get_arabic_font(size=14, bold=False)
    font_item_val = get_arabic_font(size=14, bold=True)
    font_ai = get_arabic_font(size=13, bold=False)
    font_num_badge = get_arabic_font(size=12, bold=True)

    profile = GymProfile.get_solo()
    gym_name = profile.gym_name or report_data.get("gym_name", "Systemize Gym")
    curr = profile.currency or report_data.get("currency", "ج.م")
    theme_rgb = profile.get_primary_color_rgb() if hasattr(profile, "get_primary_color_rgb") else (132, 204, 22)

    # Outer decorative card border
    draw.rounded_rectangle([16, 16, w - 16, h - 16], radius=20, fill=(15, 23, 42), outline=(30, 41, 59), width=2)

    # Top Header Pill Badge
    draw.rounded_rectangle([w // 2 - 130, 28, w // 2 + 130, 56], radius=14, fill=(30, 41, 59), outline=(71, 85, 105), width=1)
    draw.text((w // 2, 42), reshape_arabic("تقرير الإدارة الشامل والذكاء الاصطناعي"), fill=(251, 191, 36), font=font_badge, anchor="mm")

    # Gym Name
    draw.text((w // 2, 80), reshape_arabic(gym_name), fill=theme_rgb, font=font_gym, anchor="mm")

    # Date & Time Meta
    time_str = report_data.get("time_str", "")
    draw.text((w // 2, 110), reshape_arabic(f"تاريخ التقرير: {date_str}   |   توقيت الإعداد: {time_str}"), fill=(148, 163, 184), font=font_meta, anchor="mm")

    draw.line([(35, 128), (w - 35, 128)], fill=(30, 41, 59), width=1)

    # 4 Key Financial Stats (2x2 grid)
    card_w = (w - 90) // 2
    card_h = 84

    cards = [
        {
            "x": 35,
            "y": 140,
            "bg": (20, 83, 45),
            "border": (34, 197, 94),
            "lbl": "إجمالي الإيرادات اليوم",
            "val": f"{report_data.get('total_revenue', 0)} {curr}",
            "sub": f"العمليات: {report_data.get('total_payments_count', 0)} (نقدي {report_data.get('cash_collected', 0)} ج)",
            "val_color": (74, 222, 128),
        },
        {
            "x": 35 + card_w + 20,
            "y": 140,
            "bg": (127, 29, 29),
            "border": (239, 68, 68),
            "lbl": "المصروفات اليومية",
            "val": f"{report_data.get('total_expenses', 0)} {curr}",
            "sub": "فواتير ومصاريف الصالة المسجلة",
            "val_color": (248, 113, 113),
        },
        {
            "x": 35,
            "y": 234,
            "bg": (6, 78, 59),
            "border": (16, 185, 129),
            "lbl": "صافي الخزينة النقدية",
            "val": f"{report_data.get('net_cash', 0)} {curr}",
            "sub": "المحصل بالخزينة مطروحاً منه المصاريف",
            "val_color": (52, 211, 153),
        },
        {
            "x": 35 + card_w + 20,
            "y": 234,
            "bg": (120, 53, 15),
            "border": (245, 158, 11),
            "lbl": "مبيعات وأرباح البار",
            "val": f"{report_data.get('bar_sales_today', 0)} {curr}",
            "sub": f"المكسب الفعلي للبار: +{report_data.get('bar_profit_today', 0)} {curr}",
            "val_color": (251, 191, 36),
        },
    ]

    for c in cards:
        draw.rounded_rectangle([c["x"], c["y"], c["x"] + card_w, c["y"] + card_h], radius=12, fill=c["bg"], outline=c["border"], width=1)
        draw.text((c["x"] + card_w // 2, c["y"] + 18), reshape_arabic(c["lbl"]), fill=(226, 232, 240), font=font_card_lbl, anchor="mm")
        draw.text((c["x"] + card_w // 2, c["y"] + 44), reshape_arabic(c["val"]), fill=c["val_color"], font=font_card_val, anchor="mm")
        draw.text((c["x"] + card_w // 2, c["y"] + 67), reshape_arabic(c["sub"]), fill=(203, 213, 225), font=font_card_sub, anchor="mm")

    # Section 1: Subscriptions, VIP Coaching & Attendance
    sy = 330
    draw.rounded_rectangle([35, sy, w - 35, sy + 215], radius=14, fill=(17, 24, 39), outline=(51, 65, 85), width=1)
    draw.rounded_rectangle([w - 240, sy + 12, w - 50, sy + 38], radius=6, fill=(14, 116, 144))
    draw.text((w - 145, sy + 25), reshape_arabic("نشاط العضويات والحضور"), fill=(255, 255, 255), font=font_sec, anchor="mm")

    items = [
        ("اشتراكات جديدة ومجددة مسجلة اليوم:", f"{report_data.get('new_subs_count', 0)} اشتراكات"),
        ("حالات الدخول ببصمة الوجه المعتمدة اليوم:", f"{report_data.get('checkins_today_count', 0)} حضور"),
        ("اشتراكات التدريب الخاص (Private VIP):", f"{report_data.get('private_count', 0)} مشترك | دخل: {report_data.get('private_rev', 0)} {curr}"),
        ("عمولة الكباتن المستحقة عن البرايفت:", f"{report_data.get('coaches_comm', 0)} {curr}"),
        ("صافي دخل الصالة من التدريب الخاص:", f"{report_data.get('gym_private_profit', 0)} {curr}"),
        ("إجمالي الخصومات الممنوحة اليوم:", f"{report_data.get('total_discounts_today', 0)} {curr}"),
    ]
    iy = sy + 50
    for label, val in items:
        draw.ellipse([w - 55, iy + 4, w - 49, iy + 10], fill=(56, 189, 248))
        draw.text((w - 65, iy), reshape_arabic(label), fill=(203, 213, 225), font=font_item_lbl, anchor="ra")
        draw.text((50, iy), reshape_arabic(val), fill=(255, 255, 255), font=font_item_val, anchor="la")
        iy += 26

    # Section 2: Gym AI Tactical Actions ("يعمل إيه دلوقتي")
    gy = 560
    draw.rounded_rectangle([35, gy, w - 35, gy + 260], radius=14, fill=(15, 23, 42), outline=(14, 165, 233), width=2)
    draw.rounded_rectangle([w - 300, gy + 12, w - 50, gy + 38], radius=6, fill=(3, 105, 161))
    draw.text((w - 175, gy + 25), reshape_arabic("توجيهات الذكاء الاصطناعي (أولويات اليوم)"), fill=(255, 255, 255), font=font_sec, anchor="mm")

    ai_actions = report_data.get("ai_lines", [])[:4]
    if not ai_actions:
        ai_actions = [
            f"توقعات إغلاق الشهر: {report_data.get('projected_month_rev', '0')} {curr} بمعدل نمو متوازن.",
            f"متابعة التجديد: {report_data.get('expiring_soon_count', 0)} لاعب تنتهي اشتراكاتهم خلال الأسبوع القادم.",
            "فرصة مبيعات البار: مراقبة النواقص الأكثر طلباً لطلب شحنة جديدة.",
            "إعادة جذب المتوقفين: فرصة إطلاق حملة واتساب مخصصة لأعضاء الشهر الماضي.",
        ]

    line_y = gy + 52
    for idx, act in enumerate(ai_actions, 1):
        draw.rounded_rectangle([w - 76, line_y, w - 50, line_y + 24], radius=6, fill=(14, 165, 233))
        draw.text((w - 63, line_y + 12), str(idx), fill=(255, 255, 255), font=font_num_badge, anchor="mm")
        draw.text((w - 86, line_y + 2), reshape_arabic(act), fill=(241, 245, 249), font=font_ai, anchor="ra")
        line_y += 50

    # Section 3: Audit & Management Controls
    ay = 835
    draw.rounded_rectangle([35, ay, w - 35, ay + 175], radius=14, fill=(17, 24, 39), outline=(51, 65, 85), width=1)
    draw.rounded_rectangle([w - 230, ay + 12, w - 50, ay + 38], radius=6, fill=(194, 65, 12))
    draw.text((w - 140, ay + 25), reshape_arabic("رقابة وتعديلات اليوم"), fill=(255, 255, 255), font=font_sec, anchor="mm")

    audit_lines = report_data.get("audit_lines", [])[:3]
    if not audit_lines:
        draw.text((w // 2, ay + 100), reshape_arabic("لا توجد عمليات استثنائية أو تعديلات حساسة مسجلة اليوم"), fill=(148, 163, 184), font=font_item_lbl, anchor="mm")
    else:
        line_y = ay + 52
        for line in audit_lines:
            draw.ellipse([w - 55, line_y + 4, w - 49, line_y + 10], fill=(251, 146, 60))
            draw.text((w - 65, line_y), reshape_arabic(line), fill=(226, 232, 240), font=font_ai, anchor="ra")
            line_y += 32

    # Footer
    footer_text = reshape_arabic(f"نظام {gym_name} الذكي — إصدار الرقابة والإدارة التنفيذية")
    draw.text((w // 2, h - 35), footer_text, fill=(100, 116, 139), font=font_meta, anchor="mm")

    img.save(str(png_file_path), "PNG")
    logger.info("Generated polished manager report PNG at: %s", png_file_path)
    return f"reports/{png_filename}"


def prepare_manager_daily_report():
    """
    Compiles today's complete managerial report, renders executive graphics summary image,
    includes Gym AI forecasting and recommendations, and enqueues to the manager mobile number.
    """
    import calendar
    from datetime import date, timedelta
    from decimal import Decimal
    from apps.core.models import GymProfile, AuditLog
    from apps.payments.models import Payment, PaymentOperationType, BarSale
    from apps.expenses.models import Expense
    from apps.members.models import Member, Subscription, CheckInEvent

    profile = GymProfile.get_solo()
    manager_phone = profile.manager_mobile
    if not manager_phone:
        return None

    today = timezone.localdate()
    gym_name = profile.gym_name or "Systemize Gym"
    curr = profile.currency or "ج.م"

    # Daily Financials
    payments_today = Payment.objects.filter(created_at__date=today)
    pos_revenue = payments_today.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    neg_refunds = payments_today.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    total_revenue = pos_revenue + neg_refunds
    total_payments_count = payments_today.count()

    # Breakdown by Payment Method
    cash_collected = payments_today.filter(payment_method__icontains="نقدي").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    instapay_collected = payments_today.filter(payment_method__icontains="انستا").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    wallet_collected = payments_today.filter(payment_method__icontains="محفظ").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    visa_collected = payments_today.filter(payment_method__icontains="فيزا").aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

    # Expenses
    expenses_today = Expense.objects.filter(expense_date=today)
    total_expenses = expenses_today.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    net_cash = total_revenue - total_expenses

    # Bar Sales & Realized Profit Today
    bar_sales_today_qs = BarSale.objects.filter(paid_at__date=today, is_paid=True).select_related("product")
    bar_sales_today = bar_sales_today_qs.aggregate(s=Sum("total_price"))["s"] or Decimal("0.00")
    bar_profit_today = Decimal("0.00")
    for s in bar_sales_today_qs:
        if s.product:
            cost = s.product.cost_price or Decimal("0.00")
            bar_profit_today += (s.unit_price - cost) * s.quantity

    # Subscriptions & Discounts
    subs_today = Subscription.objects.filter(created_at__date=today)
    new_subs_count = subs_today.count()
    total_discounts_today = subs_today.aggregate(total=Sum("discount"))["total"] or Decimal("0.00")

    # Private Coaching
    private_subs_today = subs_today.filter(has_private=True)
    private_count = private_subs_today.count()
    private_rev = private_subs_today.aggregate(total=Sum("private_price"))["total"] or Decimal("0.00")
    coaches_comm = private_subs_today.aggregate(total=Sum("coach_commission_amount"))["total"] or Decimal("0.00")
    gym_private_profit = private_rev - coaches_comm

    # Checkins today
    checkins_today_count = CheckInEvent.objects.filter(checked_in_at__date=today).count()

    # Gym AI Intelligence & Run-Rate Forecasting
    cur_year = today.year
    cur_month = today.month
    _, total_days_in_month = calendar.monthrange(cur_year, cur_month)
    days_passed = max(1, today.day)
    mtd_rev = Payment.objects.filter(
        created_at__year=cur_year, created_at__month=cur_month, amount__gt=0
    ).aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    daily_velocity = mtd_rev / Decimal(str(days_passed))
    projected_month_rev = (daily_velocity * Decimal(str(total_days_in_month))).quantize(Decimal("0.00"))

    expiring_soon_count = Member.objects.filter(
        last_subscription_end__gte=today,
        last_subscription_end__lte=today + timedelta(days=7),
    ).count()

    active_members_count = Member.objects.filter(last_subscription_end__gte=today).count()
    expired_members_count = Member.objects.filter(Q(last_subscription_end__lt=today) | Q(last_subscription_end__isnull=True)).count()

    ai_lines = [
        f"توقعات إغلاق الشهر: {projected_month_rev} {curr} (بمعدل سرعة {daily_velocity:.0f} {curr}/يوم)",
        f"متابعة التجديد: {expiring_soon_count} لاعب تنتهي باقاتهم خلال 7 أيام (فرصة تحصيل مبكر)",
        f"مؤشر النشاط: {active_members_count} عضو نشط مقابل {expired_members_count} غير مجدد (يوصى بحملة استعادة)",
        f"توجيه الإعلانات: تكثيف الترويج بين 5:00 م - 9:00 م لتحقيق أعلى عائد تحويلي",
    ]

    # Audit Events today
    audit_today = AuditLog.objects.filter(created_at__date=today).order_by("-created_at")[:8]
    audit_count = audit_today.count()
    audit_section = ""
    if audit_count > 0:
        alines = [f"• [{timezone.localtime(a.created_at).strftime('%H:%M')}] {a.details}" for a in audit_today[:5]]
        audit_section = (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🚨 *رقابة العمليات والتعديلات ({audit_count})*:\n"
            + "\n".join(alines) + "\n"
        )

    refund_str = f" (تتضمن مستردات ملغاة: {neg_refunds} {curr})" if neg_refunds < 0 else ""

    report_text = (
        f"📊 *تقرير الإدارة اليومي الشامل - {gym_name}*\n"
        f"📅 التاريخ: {today.strftime('%Y-%m-%d')}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *إجمالي الإيرادات اليوم*: {total_revenue} {curr}{refund_str}\n"
        f"   └ 💵 نقدي (Cash): {cash_collected} {curr}\n"
        f"   └ ⚡ انستا باي (InstaPay): {instapay_collected} {curr}\n"
        f"   └ 📱 محافظ إلكترونية: {wallet_collected} {curr}\n"
        f"   └ 💳 فيزا / بنكي: {visa_collected} {curr}\n"
        f"📉 *إجمالي المصروفات اليوم*: {total_expenses} {curr}\n"
        f"💵 *صافي الخزينة الفعلي*: {net_cash} {curr}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🥤 *مبيعات البار اليوم*: {bar_sales_today} {curr} (صافي ربح: +{bar_profit_today} {curr})\n"
        f"🏋️‍♂️ *اشتراكات التدريب الخاص (Private)*: {private_count} مشترك (دخل: {private_rev} {curr})\n"
        f"   └ عمولة الكباتن: {coaches_comm} {curr} | صافي دخل الصالة: {gym_private_profit} {curr}\n"
        f"🎁 *الخصومات الممنوحة اليوم*: {total_discounts_today} {curr}\n"
        f"📝 *عضويات جديدة ومجددة*: {new_subs_count} | 👤 *دخول بصمة الوجه*: {checkins_today_count}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 *مختصر توصيات وتوقعات ذكاء الجيم (AI Insights)*:\n"
        f"• 🎯 توقعات إغلاق الشهر الجاري: *{projected_month_rev} {curr}*\n"
        f"• ⚠️ أعضاء أوشكت اشتراكاتهم على الانتهاء: *{expiring_soon_count} لاعب* (تواصل مبكر)\n"
        f"• 👥 قوام الصالة: *{active_members_count} نشط* مقابل *{expired_members_count} منتهي*\n"
        f"• 📢 توجيه الحملات: أنسب توقيت لترويج العروض بين 5:00 م - 9:00 م\n"
        f"{audit_section}"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"مرفق بطاقة التقرير التنفيذية الشاملة 📊\n"
        f"تم إعداد التقرير تلقائياً بواسطة نظام {gym_name} الذكي."
    )

    report_data = {
        "gym_name": gym_name,
        "currency": curr,
        "date_str": today.strftime("%Y-%m-%d"),
        "time_str": timezone.localtime().strftime("%I:%M %p"),
        "total_revenue": total_revenue,
        "total_payments_count": total_payments_count,
        "total_expenses": total_expenses,
        "net_cash": net_cash,
        "cash_collected": cash_collected,
        "bar_sales_today": bar_sales_today,
        "bar_profit_today": bar_profit_today,
        "total_discounts_today": total_discounts_today,
        "new_subs_count": new_subs_count,
        "private_count": private_count,
        "private_rev": private_rev,
        "coaches_comm": coaches_comm,
        "gym_private_profit": gym_private_profit,
        "checkins_today_count": checkins_today_count,
        "projected_month_rev": projected_month_rev,
        "expiring_soon_count": expiring_soon_count,
        "ai_lines": ai_lines,
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
    qs = Member.objects.filter(mobile__isnull=False).exclude(mobile="")

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
    gym_name = profile.gym_name or "Systemize Gym"
    today = timezone.localdate()
    queued_count = 0
    batch_tag = f"bulk_{category}_{today.isoformat()}_{int(timezone.now().timestamp())}"

    for m in members:
        m.refresh_status()
        end_date_str = m.last_subscription_end.strftime("%Y-%m-%d") if m.last_subscription_end else "غير محدد"
        days_diff = (m.last_subscription_end - today).days if m.last_subscription_end else 0

        from apps.messaging.message_bank import get_random_message, format_template_safely

        ctx = {
            "name": m.name or "كابتن",
            "gym_name": gym_name,
            "end_date": end_date_str,
            "days_left": abs(days_diff),
            "remaining": str(m.current_remaining),
            "remaining_amount": str(m.current_remaining),
            "plan": m.last_subscription_type or "الاشتراك",
            "plan_name": m.last_subscription_type or "الاشتراك",
            "phone": m.mobile,
        }

        raw_template = message_template.strip()
        if raw_template in ["__RANDOM_BANK__", "__AUTO_VARIATION__"]:
            # Pick from bank based on target category
            bank_cat = "expired" if category == "non_sub" else ("reminder_1" if category == "expiring_soon" else "general")
            text = get_random_message(bank_cat, ctx)
        elif "---" in raw_template:
            # Multi-variation separated by '---'
            sub_templates = [st.strip() for st in raw_template.split("---") if st.strip()]
            text = format_template_safely(random.choice(sub_templates), ctx)
        else:
            text = format_template_safely(raw_template, ctx)

        dedup = f"{m.mobile}_{batch_tag}"
        msg = enqueue_message(
            mobile=m.mobile,
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
