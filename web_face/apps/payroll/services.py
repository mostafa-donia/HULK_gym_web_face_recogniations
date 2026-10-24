import os
import logging
from decimal import Decimal
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from apps.core.models import GymProfile
from apps.core.text_utils import reshape_arabic, get_arabic_font
from apps.messaging.models import WhatsAppMessage, MessageType, MessageStatus
from apps.payroll.models import PayrollItem, PayrollRun

logger = logging.getLogger(__name__)


def generate_salary_slip_image(item: PayrollItem) -> Optional[str]:
    """
    Renders an official graphical salary statement slip (PNG) for an employee.
    Saves to media/salary_slips/salary_slip_{item.id}_{clean_period}.png
    and returns the relative media path.
    """
    try:
        profile = GymProfile.get_solo()
        period = item.payroll_run.period if item.payroll_run else "N/A"
        clean_period = str(period).replace("/", "_").replace("-", "_")

        slips_dir = Path(settings.MEDIA_ROOT) / "salary_slips"
        slips_dir.mkdir(parents=True, exist_ok=True)

        png_filename = f"salary_slip_{item.id}_{clean_period}.png"
        png_file_path = slips_dir / png_filename

        w, h = 680, 880
        img = Image.new("RGB", (w, h), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)

        # Card white body
        draw.rounded_rectangle([20, 20, w - 20, h - 20], radius=16, fill=(255, 255, 255), outline=(203, 213, 225), width=2)

        # Header background
        draw.rounded_rectangle([20, 20, w - 20, 115], radius=16, fill=(15, 23, 42))
        draw.rectangle([20, 95, w - 20, 115], fill=(15, 23, 42))

        # Fonts setup (connected modern Arabic font)
        font_title = get_arabic_font(size=25, bold=True)
        font_sub = get_arabic_font(size=16, bold=False)
        font_bold = get_arabic_font(size=18, bold=True)
        font_normal = get_arabic_font(size=16, bold=False)
        font_lg = get_arabic_font(size=24, bold=True)
        font_sm = get_arabic_font(size=16, bold=False)

        raw_gym_name = profile.gym_name or "Systemize Gym"
        curr = profile.currency or "ج.م"
        theme_rgb = (16, 185, 129)  # Emerald green accent for salary

        # Paste Logo if available
        logo_p = profile.get_logo_image_path() if hasattr(profile, "get_logo_image_path") else None
        if logo_p and os.path.exists(logo_p):
            try:
                lim = Image.open(logo_p).convert("RGBA")
                lim.thumbnail((60, 60), Image.Resampling.LANCZOS)
                img.paste(lim, (45, 25), lim)
            except Exception:
                pass

        draw.text((w // 2, 48), reshape_arabic(raw_gym_name), fill=theme_rgb, font=font_title, anchor="mm")
        draw.text((w // 2, 84), reshape_arabic(f"كشف راتب شهري رسمي | SALARY STATEMENT ({period})"), fill=(203, 213, 225), font=font_sub, anchor="mm")

        # Employee Info Bar
        y = 130
        draw.rounded_rectangle([40, y, w - 40, y + 42], radius=8, fill=(241, 245, 249))
        draw.text((55, y + 12), f"Period: {period}", fill=(71, 85, 105), font=font_sm)
        emp_name = item.employee_name_snapshot or (item.employee.name if item.employee else "موظف")
        emp_role = item.role_snapshot or (item.employee.get_role_display() if item.employee else "موظف")
        draw.text((w - 55, y + 11), reshape_arabic(f"الموظف: {emp_name} ({emp_role})"), fill=(15, 23, 42), font=font_bold, anchor="ra")

        def draw_rtl_row(row_y, label_txt, val_txt, val_color=(15, 23, 42), is_bold=False):
            draw.text((w - 55, row_y), reshape_arabic(label_txt), fill=(100, 116, 139), font=font_normal, anchor="ra")
            draw.text((55, row_y), reshape_arabic(val_txt), fill=val_color, font=font_bold if is_bold else font_normal)

        # Employee details rows
        y = 190
        emp_code = item.employee.code if item.employee and hasattr(item.employee, "code") else f"EMP-{item.employee_id}"
        draw_rtl_row(y, "كود الموظف / السجل:", emp_code, val_color=(51, 65, 85), is_bold=True)

        y += 34
        emp_phone = item.employee.phone if item.employee and item.employee.phone else "-"
        draw_rtl_row(y, "رقم الهاتف / الواتساب:", emp_phone, val_color=(51, 65, 85), is_bold=False)

        y += 34
        approval_date = item.payroll_run.approved_at.strftime("%Y-%m-%d %I:%M %p") if item.payroll_run and item.payroll_run.approved_at else timezone.now().strftime("%Y-%m-%d")
        draw_rtl_row(y, "تاريخ ووقت الاعتماد:", approval_date, val_color=(30, 64, 175), is_bold=False)

        y += 32
        draw.line([(40, y), (w - 40, y)], fill=(226, 232, 240), width=1)

        # Financial breakdown box
        y += 18
        box_h = 240
        draw.rounded_rectangle([40, y, w - 40, y + box_h], radius=12, fill=(248, 250, 252), outline=(203, 213, 225), width=1)

        fy = y + 16
        # 1. Fixed Salary
        draw.text((w - 60, fy), reshape_arabic("الراتب الأساسي الثابت:"), fill=(71, 85, 105), font=font_normal, anchor="ra")
        draw.text((60, fy), reshape_arabic(f"{item.fixed_salary} {curr}"), fill=(15, 23, 42), font=font_bold)

        fy += 34
        # 2. Commissions
        comm_val = item.commissions or Decimal("0.00")
        draw.text((w - 60, fy), reshape_arabic("عمولات التدريب الخاص (Private):"), fill=(71, 85, 105), font=font_normal, anchor="ra")
        draw.text((60, fy), reshape_arabic(f"+{comm_val} {curr}"), fill=(16, 185, 129) if comm_val > 0 else (100, 116, 139), font=font_bold)

        fy += 34
        # 3. Bonuses
        bonuses_val = item.bonuses or Decimal("0.00")
        draw.text((w - 60, fy), reshape_arabic("المكافآت والحوافز المعتمدة:"), fill=(71, 85, 105), font=font_normal, anchor="ra")
        draw.text((60, fy), reshape_arabic(f"+{bonuses_val} {curr}"), fill=(16, 185, 129) if bonuses_val > 0 else (100, 116, 139), font=font_bold)

        fy += 34
        # 4. Deductions
        ded_val = item.deductions or Decimal("0.00")
        draw.text((w - 60, fy), reshape_arabic("الخصومات والجزاءات:"), fill=(71, 85, 105), font=font_normal, anchor="ra")
        draw.text((60, fy), reshape_arabic(f"-{ded_val} {curr}"), fill=(220, 38, 38) if ded_val > 0 else (100, 116, 139), font=font_bold)

        fy += 34
        # 5. Advances
        adv_val = item.advances or Decimal("0.00")
        draw.text((w - 60, fy), reshape_arabic("السلف المسحوبة مقدماً:"), fill=(71, 85, 105), font=font_normal, anchor="ra")
        draw.text((60, fy), reshape_arabic(f"-{adv_val} {curr}"), fill=(234, 88, 12) if adv_val > 0 else (100, 116, 139), font=font_bold)

        fy += 38
        draw.line([(55, fy), (w - 55, fy)], fill=(203, 213, 225), width=1)

        # Net Payable Box
        y += box_h + 24
        draw.rounded_rectangle([40, y, w - 40, y + 80], radius=12, fill=(236, 253, 245), outline=(16, 185, 129), width=2)
        draw.text((w - 60, y + 22), reshape_arabic("صافي الراتب المستحق للصرف:"), fill=(6, 95, 70), font=font_bold, anchor="ra")
        draw.text((60, y + 18), reshape_arabic(f"{item.net_payable} {curr}"), fill=(5, 150, 105), font=font_lg)
        draw.text((w - 60, y + 52), reshape_arabic("الحالة: معتمد نهائياً ومحول للصرف ✓"), fill=(16, 185, 129), font=font_sm, anchor="ra")

        # Official Stamp and Footer
        y += 105
        thank_you_text = reshape_arabic(f"تقديراً لجهودكم المتميزة والمخلصة في نجاح وتألق {raw_gym_name} 💪")
        draw.text((w // 2, y), thank_you_text, fill=(71, 85, 105), font=font_bold, anchor="mm")

        img.save(str(png_file_path), "PNG")
        logger.info("Generated standalone PNG salary slip at: %s", png_file_path)
        return f"salary_slips/{png_filename}"
    except Exception as exc:
        logger.exception("Failed to generate salary slip image: %s", exc)
        return None


def get_default_salary_message(item: PayrollItem) -> str:
    """Returns a warm, appreciative, transparent, and cheerful salary WhatsApp message."""
    profile = GymProfile.get_solo()
    period = item.payroll_run.period if item.payroll_run else "N/A"
    curr = profile.currency or "ج.م"
    raw_gym_name = profile.gym_name or "Systemize Gym"

    advances_line = f"• السلف المسحوبة مقدماً: -{item.advances} {curr}\n" if (item.advances and item.advances > 0) else ""
    comm_line = f"• عمولات التدريب الخاص (Private): +{item.commissions} {curr}\n" if (item.commissions and item.commissions > 0) else ""
    bonus_line = f"• المكافآت والحوافز المعتمدة: +{item.bonuses} {curr}\n" if (item.bonuses and item.bonuses > 0) else ""
    ded_line = f"• الخصومات والجزاءات: -{item.deductions} {curr}\n" if (item.deductions and item.deductions > 0) else ""

    return (
        f"ألف مبروك وبالتوفيق والبركة كابتن {item.employee_name_snapshot} 🌟👏\n\n"
        f"خالص شكر وتقدير إدارة {raw_gym_name} على مجهودك وتفانيك الرائع طوال الشهر! 💪\n"
        f"يسعدنا إبلاغك بصدور واعتماد كشف راتبك لشهر {period} 💼✨\n\n"
        f"📋 مفردات الراتب المعتمد:\n"
        f"• الراتب الأساسي الثابت: {item.fixed_salary} {curr}\n"
        f"{comm_line}"
        f"{bonus_line}"
        f"{ded_line}"
        f"{advances_line}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💵 صافي المستحق للاستلام: {item.net_payable} {curr}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"📄 مرفق لسيادتكم صورة كشف الراتب الرسمي المعتمد.\n"
        f"عاش يا بطل، فخورين بوجودك معانا في الفريق ومكملين لنجاحات أكبر سوا إن شاء الله! 🔥🚀"
    )


def queue_payroll_item_whatsapp(item: PayrollItem, custom_message: Optional[str] = None) -> Optional[WhatsAppMessage]:
    """
    Builds friendly salary message text (or uses custom edited text), renders PNG salary statement slip image,
    and queues a WhatsAppMessage in PENDING status.
    """
    if not item.employee or not item.employee.phone:
        return None

    period = item.payroll_run.period if item.payroll_run else "N/A"

    rel_slip_image = generate_salary_slip_image(item)

    msg_text = custom_message.strip() if custom_message else get_default_salary_message(item)

    dedup_key = f"salary:{item.employee.phone}:{period}"
    defaults = {
        "mobile": item.employee.phone,
        "message": msg_text,
        "msg_type": MessageType.SALARY_STATEMENT,
        "recipient_name": item.employee_name_snapshot,
        "recipient_type": "employee",
        "status": MessageStatus.PENDING,
    }
    if rel_slip_image:
        defaults["attachment"] = rel_slip_image

    msg_obj, created = WhatsAppMessage.objects.update_or_create(
        dedup_key=dedup_key,
        defaults=defaults,
    )

    item.whatsapp_sent_at = timezone.now()
    item.save(update_fields=["whatsapp_sent_at"])
    return msg_obj


def queue_all_approved_payroll_whatsapp(payroll_run: PayrollRun) -> int:
    """
    Loops through all PayrollItems for an approved payroll run and adds them
    to WhatsApp pending messages queue with friendly text and slip image.
    """
    items = PayrollItem.objects.filter(payroll_run=payroll_run).select_related("employee", "payroll_run")
    queued_count = 0
    for item in items:
        if item.employee and item.employee.phone:
            try:
                res = queue_payroll_item_whatsapp(item)
                if res:
                    queued_count += 1
            except Exception as e:
                logger.error("Error queuing WhatsApp salary slip for %s: %s", item.employee_name_snapshot, e)

    return queued_count
