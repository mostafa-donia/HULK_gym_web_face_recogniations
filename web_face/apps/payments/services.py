import logging
from decimal import Decimal
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.template.loader import render_to_string
from PIL import Image, ImageDraw, ImageFont

from apps.core.models import GymProfile
from apps.core.text_utils import reshape_arabic
from apps.messaging.models import WhatsAppMessage, MessageType, MessageStatus
from apps.payments.models import Payment

logger = logging.getLogger(__name__)


def generate_invoice_html_file(payment: Payment, subscription=None) -> str:
    """
    Renders an ultra-fast, lightweight standalone HTML invoice (< 4 KB)
    with the exact layout and inline styling matching the system's official receipt.
    Saves the file to media/invoices/invoice_{invoice_no}.html and returns the relative path.
    """
    profile = GymProfile.get_solo()
    member = payment.member

    if subscription is None and member:
        subscription = member.subscriptions.order_by("-created_at").first()

    context = {
        "payment": payment,
        "member": member,
        "subscription": subscription,
        "profile": profile,
    }

    html_content = render_to_string("payments/invoice_standalone.html", context)

    # Ensure media/invoices folder exists
    invoices_dir = Path(settings.MEDIA_ROOT) / "invoices"
    invoices_dir.mkdir(parents=True, exist_ok=True)

    clean_invoice_no = payment.invoice_no.replace("/", "_").replace("\\", "_")
    filename = f"invoice_{clean_invoice_no}.html"
    file_path = invoices_dir / filename

    file_path.write_text(html_content, encoding="utf-8")
    logger.info("Generated standalone HTML invoice at: %s (size: %d bytes)", file_path, len(html_content))

    return f"invoices/{filename}"


def generate_invoice_image_file(payment: Payment, subscription=None) -> str:
    """
    Renders an official graphical receipt image (PNG) matching the payment record.
    Saves to media/invoices/invoice_{clean_invoice_no}.png and returns the relative path.
    """
    profile = GymProfile.get_solo()
    member = payment.member

    if subscription is None and member:
        subscription = member.subscriptions.order_by("-created_at").first()

    invoices_dir = Path(settings.MEDIA_ROOT) / "invoices"
    invoices_dir.mkdir(parents=True, exist_ok=True)

    clean_invoice_no = payment.invoice_no.replace("/", "_").replace("\\", "_")
    png_filename = f"invoice_{clean_invoice_no}.png"
    png_file_path = invoices_dir / png_filename

    w, h = 640, 720
    img = Image.new("RGB", (w, h), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    # Card background
    draw.rounded_rectangle([20, 20, w - 20, h - 20], radius=16, fill=(255, 255, 255), outline=(203, 213, 225), width=2)

    # Header bar
    draw.rounded_rectangle([20, 20, w - 20, 110], radius=16, fill=(15, 23, 42))
    draw.rectangle([20, 90, w - 20, 110], fill=(15, 23, 42))

    try:
        font_title = ImageFont.truetype("tahomabd.ttf", 24)
        font_sub = ImageFont.truetype("tahoma.ttf", 15)
        font_bold = ImageFont.truetype("tahomabd.ttf", 17)
        font_normal = ImageFont.truetype("tahoma.ttf", 16)
        font_sm = ImageFont.truetype("tahoma.ttf", 13)
    except Exception:
        try:
            font_title = ImageFont.truetype("arialbd.ttf", 24)
            font_sub = ImageFont.truetype("arial.ttf", 15)
            font_bold = ImageFont.truetype("arialbd.ttf", 17)
            font_normal = ImageFont.truetype("arial.ttf", 16)
            font_sm = ImageFont.truetype("arial.ttf", 13)
        except Exception:
            font_title = font_sub = font_bold = font_normal = font_sm = ImageFont.load_default()

    gym_title = reshape_arabic(profile.gym_name or "HULK GYM")
    draw.text((w // 2, 45), gym_title, fill=(132, 204, 22), font=font_title, anchor="mm")
    draw.text((w // 2, 80), reshape_arabic(f"إيصال سداد رسمي | OFFICIAL RECEIPT #{payment.invoice_no}"), fill=(203, 213, 225), font=font_sub, anchor="mm")

    y = 135
    date_str = payment.created_at.strftime("%Y-%m-%d %I:%M %p")
    draw.rectangle([40, y, w - 40, y + 40], fill=(241, 245, 249))
    draw.text((55, y + 12), f"Date: {date_str}", fill=(71, 85, 105), font=font_sm)
    draw.text((w - 55, y + 12), f"Invoice: #{payment.invoice_no}", fill=(15, 23, 42), font=font_bold, anchor="ra")

    y = 195
    mem_name = reshape_arabic(member.name if member else "عميل كاش")
    draw.text((55, y), reshape_arabic("اسم العضو:"), fill=(100, 116, 139), font=font_normal)
    draw.text((w - 55, y), mem_name, fill=(15, 23, 42), font=font_bold, anchor="ra")

    y += 35
    mem_code = member.member_id if member else "-"
    mem_mobile = member.mobile if member else "-"
    draw.text((55, y), reshape_arabic("كود العضو / الهاتف:"), fill=(100, 116, 139), font=font_normal)
    draw.text((w - 55, y), f"{mem_code} | {mem_mobile}", fill=(15, 23, 42), font=font_normal, anchor="ra")

    y += 40
    draw.line([(40, y), (w - 40, y)], fill=(226, 232, 240), width=1)

    y += 20
    plan_name = reshape_arabic(subscription.plan_name if subscription else (payment.get_operation_type_display()))
    draw.text((55, y), reshape_arabic("نوع الاشتراك / الباقة:"), fill=(100, 116, 139), font=font_normal)
    draw.text((w - 55, y), plan_name, fill=(2, 132, 199), font=font_bold, anchor="ra")

    if subscription:
        y += 35
        sub_period = f"{subscription.start_date.strftime('%Y-%m-%d')} to {subscription.end_date.strftime('%Y-%m-%d')}"
        draw.text((55, y), reshape_arabic("فترة الصلاحية:"), fill=(100, 116, 139), font=font_normal)
        draw.text((w - 55, y), sub_period, fill=(15, 23, 42), font=font_normal, anchor="ra")

    y += 40
    draw.line([(40, y), (w - 40, y)], fill=(226, 232, 240), width=1)

    y += 20
    draw.rounded_rectangle([40, y, w - 40, y + 130], radius=10, fill=(248, 250, 252), outline=(226, 232, 240), width=1)

    curr = reshape_arabic(profile.currency or "ج.م")
    fy = y + 15
    draw.text((60, fy), reshape_arabic("المبلغ الإجمالي:"), fill=(71, 85, 105), font=font_normal)
    draw.text((w - 60, fy), f"{payment.amount} {curr}", fill=(15, 23, 42), font=font_bold, anchor="ra")

    fy += 35
    draw.text((60, fy), reshape_arabic("المبلغ المدفوع:"), fill=(22, 163, 74), font=font_bold)
    draw.text((w - 60, fy), f"{payment.amount} {curr}", fill=(22, 163, 74), font=font_bold, anchor="ra")

    fy += 35
    rem = member.current_remaining if member else Decimal("0.00")
    draw.text((60, fy), reshape_arabic("المتبقي كدين:"), fill=(220, 38, 38) if rem > 0 else (71, 85, 105), font=font_normal)
    draw.text((w - 60, fy), f"{rem} {curr}", fill=(220, 38, 38) if rem > 0 else (71, 85, 105), font=font_bold, anchor="ra")

    y += 150
    if rem <= 0:
        draw.rounded_rectangle([w // 2 - 130, y, w // 2 + 130, y + 38], radius=8, fill=(220, 252, 231), outline=(34, 197, 94), width=1)
        draw.text((w // 2, y + 19), reshape_arabic("PAID IN FULL / خالص السداد ✓"), fill=(21, 128, 61), font=font_bold, anchor="mm")
    else:
        draw.rounded_rectangle([w // 2 - 130, y, w // 2 + 130, y + 38], radius=8, fill=(254, 242, 242), outline=(239, 68, 68), width=1)
        draw.text((w // 2, y + 19), reshape_arabic(f"المتبقي دين: {rem} {curr}"), fill=(185, 28, 28), font=font_bold, anchor="mm")

    thank_you_text = reshape_arabic(f"شكراً لاختياركم {profile.gym_name or 'HULK GYM'}!")
    draw.text((w // 2, h - 50), thank_you_text, fill=(148, 163, 184), font=font_sm, anchor="mm")

    img.save(str(png_file_path), "PNG")
    logger.info("Generated standalone PNG invoice at: %s", png_file_path)
    return f"invoices/{png_filename}"
    logger.info("Generated standalone PNG invoice at: %s", png_file_path)
    return f"invoices/{png_filename}"


def queue_payment_receipt_whatsapp(payment: Payment, subscription=None) -> Optional[WhatsAppMessage]:
    """
    Generates the HTML invoice document and PNG receipt image, formats receipt caption text,
    and queues a WhatsAppMessage with the receipt PNG image attached for WhatsApp Desktop delivery.
    """
    member = payment.member
    if not member or not member.mobile:
        return None

    profile = GymProfile.get_solo()
    if not profile.whatsapp_enabled:
        return None

    # 1. Generate standalone HTML and PNG invoice files
    rel_invoice_path = None
    try:
        generate_invoice_html_file(payment, subscription)
        rel_invoice_path = generate_invoice_image_file(payment, subscription)
    except Exception as exc:
        logger.exception("Failed to generate invoice files: %s", exc)

    # 2. Build receipt text
    op_name = payment.get_operation_type_display()
    if subscription:
        sub_info = f"\nالباقة: {subscription.plan_name}\nصالح حتى: {subscription.end_date.strftime('%Y-%m-%d')}"
    else:
        sub_info = ""

    remaining_info = f"\nالمتبقي دين: {member.current_remaining} {profile.currency}" if member.current_remaining > 0 else "\nالحساب: خالص السداد بالكامل ✓"

    receipt_text = (
        f"إيصال مالي رسمي من {profile.gym_name}\n"
        f"أهلاً كابتن {member.name} 👋\n"
        f"نوع العملية: {op_name}\n"
        f"رقم الفاتورة: {payment.invoice_no}\n"
        f"المبلغ المدفوع: {payment.amount} {profile.currency}"
        f"{remaining_info}"
        f"{sub_info}\n"
        f"مرفق الفاتورة الإلكترونية الرسمية 📄\n"
        f"شكراً لاختيارك {profile.gym_name} 💪"
    )

    clean_invoice_no = payment.invoice_no.replace("/", "_").replace("\\", "_")
    dedup_key = f"receipt:{member.mobile}:{clean_invoice_no}"

    msg_obj, created = WhatsAppMessage.objects.get_or_create(
        dedup_key=dedup_key,
        defaults={
            "mobile": member.mobile,
            "message": receipt_text,
            "msg_type": MessageType.RECEIPT,
            "recipient_name": member.name,
            "recipient_type": "member",
            "attachment": rel_invoice_path or "",
            "status": MessageStatus.PENDING,
        },
    )

    if not created and rel_invoice_path and not msg_obj.attachment:
        msg_obj.attachment = rel_invoice_path
        msg_obj.save(update_fields=["attachment"])

    return msg_obj
