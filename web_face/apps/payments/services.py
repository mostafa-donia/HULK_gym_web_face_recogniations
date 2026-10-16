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
    Renders an official graphical receipt image (PNG) matching the payment record,
    including full subscription, Private training, Coach, and Discount breakdown.
    Saves to media/invoices/invoice_{clean_invoice_no}.png and returns the relative path.
    """
    profile = GymProfile.get_solo()
    member = payment.member

    if subscription is None and member:
        subscription = (
            member.subscriptions.filter(created_at__date=payment.created_at.date()).order_by("-created_at").first()
            or member.subscriptions.order_by("-created_at").first()
        )

    invoices_dir = Path(settings.MEDIA_ROOT) / "invoices"
    invoices_dir.mkdir(parents=True, exist_ok=True)

    clean_invoice_no = payment.invoice_no.replace("/", "_").replace("\\", "_")
    png_filename = f"invoice_{clean_invoice_no}.png"
    png_file_path = invoices_dir / png_filename

    w, h = 680, 900
    img = Image.new("RGB", (w, h), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    # Card background
    draw.rounded_rectangle([20, 20, w - 20, h - 20], radius=16, fill=(255, 255, 255), outline=(203, 213, 225), width=2)

    # Header bar
    draw.rounded_rectangle([20, 20, w - 20, 115], radius=16, fill=(15, 23, 42))
    draw.rectangle([20, 95, w - 20, 115], fill=(15, 23, 42))

    try:
        font_title = ImageFont.truetype("tahomabd.ttf", 25)
        font_sub = ImageFont.truetype("tahoma.ttf", 15)
        font_bold = ImageFont.truetype("tahomabd.ttf", 16)
        font_normal = ImageFont.truetype("tahoma.ttf", 15)
        font_sm = ImageFont.truetype("tahoma.ttf", 13)
    except Exception:
        try:
            font_title = ImageFont.truetype("arialbd.ttf", 25)
            font_sub = ImageFont.truetype("arial.ttf", 15)
            font_bold = ImageFont.truetype("arialbd.ttf", 16)
            font_normal = ImageFont.truetype("arial.ttf", 15)
            font_sm = ImageFont.truetype("arial.ttf", 13)
        except Exception:
            font_title = font_sub = font_bold = font_normal = font_sm = ImageFont.load_default()

    raw_gym_name = profile.gym_name or "HULK GYM"
    curr = profile.currency or "ج.م"

    draw.text((w // 2, 48), reshape_arabic(raw_gym_name), fill=(132, 204, 22), font=font_title, anchor="mm")
    draw.text((w // 2, 84), reshape_arabic(f"إيصال سداد مالي رسمي | OFFICIAL RECEIPT #{payment.invoice_no}"), fill=(203, 213, 225), font=font_sub, anchor="mm")

    # Date & Invoice number bar
    y = 132
    date_str = payment.created_at.strftime("%Y-%m-%d %I:%M %p")
    draw.rounded_rectangle([40, y, w - 40, y + 40], radius=8, fill=(241, 245, 249))
    draw.text((55, y + 12), f"Date: {date_str}", fill=(71, 85, 105), font=font_sm)
    draw.text((w - 55, y + 11), reshape_arabic(f"رقم الفاتورة: #{payment.invoice_no}"), fill=(15, 23, 42), font=font_bold, anchor="ra")

    # Helper to draw an RTL row (Label on the right, Value on the left)
    def draw_rtl_row(row_y, label_txt, val_txt, val_color=(15, 23, 42), is_bold=True):
        draw.text((w - 55, row_y), reshape_arabic(label_txt), fill=(100, 116, 139), font=font_normal, anchor="ra")
        draw.text((55, row_y), reshape_arabic(val_txt), fill=val_color, font=font_bold if is_bold else font_normal)

    y = 190
    mem_name = member.name if member else "عميل كاش"
    draw_rtl_row(y, "اسم العضو:", mem_name, val_color=(15, 23, 42), is_bold=True)

    y += 34
    mem_code = member.member_id if member else "-"
    mem_mobile = member.mobile if member else "-"
    draw_rtl_row(y, "كود العضو / الهاتف:", f"{mem_code}  |  {mem_mobile}", val_color=(51, 65, 85), is_bold=False)

    y += 34
    op_display = payment.get_operation_type_display()
    draw_rtl_row(y, "نوع العملية:", op_display, val_color=(30, 64, 175), is_bold=True)

    y += 32
    draw.line([(40, y), (w - 40, y)], fill=(226, 232, 240), width=1)

    y += 18
    plan_name = subscription.plan_name if subscription else op_display
    draw_rtl_row(y, "الباقة / الاشتراك:", plan_name, val_color=(2, 132, 199), is_bold=True)

    if subscription:
        y += 34
        sub_period = f"{subscription.start_date.strftime('%Y-%m-%d')}  ->  {subscription.end_date.strftime('%Y-%m-%d')}"
        draw_rtl_row(y, "فترة صلاحية الاشتراك:", sub_period, val_color=(15, 23, 42), is_bold=False)

        # Private Training status
        y += 34
        if subscription.has_private:
            coach_str = f" - كابتن {subscription.coach.name}" if subscription.coach else ""
            priv_text = f"شامل تدريب خاص ({subscription.private_price} {curr}){coach_str}"
            draw_rtl_row(y, "التدريب الخاص (Private):", priv_text, val_color=(124, 58, 237), is_bold=True)
        else:
            draw_rtl_row(y, "التدريب الخاص (Private):", "بدون تدريب خاص (غير مشترك)", val_color=(100, 116, 139), is_bold=False)

        # Discount status
        y += 34
        if subscription.discount and subscription.discount > Decimal("0.00"):
            disc_text = f"يوجد خصم ({subscription.discount} {curr})"
            draw_rtl_row(y, "حالة الخصم (Discount):", disc_text, val_color=(217, 119, 6), is_bold=True)
        else:
            draw_rtl_row(y, "حالة الخصم (Discount):", f"بدون خصم (0.00 {curr})", val_color=(100, 116, 139), is_bold=False)
    else:
        y += 34
        draw_rtl_row(y, "التدريب الخاص (Private):", "غير مشمول", val_color=(100, 116, 139), is_bold=False)
        y += 34
        draw_rtl_row(y, "حالة الخصم (Discount):", f"بدون خصم (0.00 {curr})", val_color=(100, 116, 139), is_bold=False)

    y += 36
    draw.line([(40, y), (w - 40, y)], fill=(226, 232, 240), width=1)

    # Financial breakdown box
    y += 18
    box_h = 205 if subscription else 135
    draw.rounded_rectangle([40, y, w - 40, y + box_h], radius=12, fill=(248, 250, 252), outline=(203, 213, 225), width=1)

    fy = y + 16
    if subscription:
        draw.text((w - 60, fy), reshape_arabic("سعر الباقة الأساسي:"), fill=(71, 85, 105), font=font_normal, anchor="ra")
        draw.text((60, fy), reshape_arabic(f"{subscription.plan_price} {curr}"), fill=(15, 23, 42), font=font_normal)

        fy += 30
        priv_val = subscription.private_price if subscription.has_private else Decimal("0.00")
        draw.text((w - 60, fy), reshape_arabic("رسوم التدريب الخاص (Private):"), fill=(71, 85, 105), font=font_normal, anchor="ra")
        draw.text((60, fy), reshape_arabic(f"{priv_val} {curr}"), fill=(124, 58, 237) if priv_val > 0 else (100, 116, 139), font=font_normal)

        fy += 30
        disc_val = subscription.discount or Decimal("0.00")
        draw.text((w - 60, fy), reshape_arabic("قيمة الخصم الممنوح:"), fill=(71, 85, 105), font=font_normal, anchor="ra")
        draw.text((60, fy), reshape_arabic(f"{disc_val} {curr}"), fill=(217, 119, 6) if disc_val > 0 else (100, 116, 139), font=font_normal)

        fy += 30
        draw.text((w - 60, fy), reshape_arabic("الصافي المطلوب بعد الخصم:"), fill=(15, 23, 42), font=font_bold, anchor="ra")
        draw.text((60, fy), reshape_arabic(f"{subscription.net_amount} {curr}"), fill=(15, 23, 42), font=font_bold)
        fy += 34
    else:
        draw.text((w - 60, fy), reshape_arabic("المبلغ الإجمالي:"), fill=(71, 85, 105), font=font_normal, anchor="ra")
        draw.text((60, fy), reshape_arabic(f"{payment.amount} {curr}"), fill=(15, 23, 42), font=font_bold)
        fy += 34

    draw.text((w - 60, fy), reshape_arabic("المبلغ المدفوع بهذه الفاتورة:"), fill=(22, 163, 74), font=font_bold, anchor="ra")
    draw.text((60, fy), reshape_arabic(f"{payment.amount} {curr}"), fill=(22, 163, 74), font=font_bold)

    fy += 32
    rem = member.current_remaining if member else Decimal("0.00")
    draw.text((w - 60, fy), reshape_arabic("إجمالي المتبقي كدين:"), fill=(220, 38, 38) if rem > 0 else (71, 85, 105), font=font_normal, anchor="ra")
    draw.text((60, fy), reshape_arabic(f"{rem} {curr}"), fill=(220, 38, 38) if rem > 0 else (71, 85, 105), font=font_bold)

    y += box_h + 22
    if rem <= 0:
        draw.rounded_rectangle([w // 2 - 150, y, w // 2 + 150, y + 40], radius=8, fill=(220, 252, 231), outline=(34, 197, 94), width=1)
        draw.text((w // 2, y + 20), reshape_arabic("PAID IN FULL | خالص السداد بالكامل"), fill=(21, 128, 61), font=font_bold, anchor="mm")
    else:
        draw.rounded_rectangle([w // 2 - 150, y, w // 2 + 150, y + 40], radius=8, fill=(254, 242, 242), outline=(239, 68, 68), width=1)
        draw.text((w // 2, y + 20), reshape_arabic(f"المتبقي دين: {rem} {curr}"), fill=(185, 28, 28), font=font_bold, anchor="mm")

    thank_you_text = reshape_arabic(f"شكراً لاختياركم {raw_gym_name}")
    draw.text((w // 2, h - 42), thank_you_text, fill=(148, 163, 184), font=font_sm, anchor="mm")

    img.save(str(png_file_path), "PNG")
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

    if subscription is None and member:
        subscription = (
            member.subscriptions.filter(created_at__date=payment.created_at.date()).order_by("-created_at").first()
            or member.subscriptions.order_by("-created_at").first()
        )

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
        coach_str = f" (كابتن {subscription.coach.name})" if subscription.has_private and subscription.coach else ""
        private_line = (
            f"\nالتدريب الخاص: شامل برايفت ({subscription.private_price} {profile.currency}){coach_str}"
            if subscription.has_private
            else "\nالتدريب الخاص: بدون برايفت"
        )
        discount_line = (
            f"\nالخصم الممنوح: {subscription.discount} {profile.currency}"
            if subscription.discount and subscription.discount > 0
            else "\nالخصم: بدون خصم"
        )
        sub_info = (
            f"\nالباقة: {subscription.plan_name}"
            f"{private_line}"
            f"{discount_line}"
            f"\nصالح حتى: {subscription.end_date.strftime('%Y-%m-%d')}"
        )
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

    if not created and rel_invoice_path:
        msg_obj.attachment = rel_invoice_path
        msg_obj.message = receipt_text
        msg_obj.save(update_fields=["attachment", "message"])

    return msg_obj
