import logging
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.template.loader import render_to_string

from apps.core.models import GymProfile
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


def queue_payment_receipt_whatsapp(payment: Payment, subscription=None) -> Optional[WhatsAppMessage]:
    """
    Generates the HTML invoice document, formats receipt caption text,
    and queues a WhatsAppMessage with the HTML file attached.
    """
    member = payment.member
    if not member or not member.mobile:
        return None

    profile = GymProfile.get_solo()
    if not profile.whatsapp_enabled:
        return None

    # 1. Generate standalone lightweight HTML invoice file
    try:
        rel_invoice_path = generate_invoice_html_file(payment, subscription)
    except Exception as exc:
        logger.exception("Failed to generate HTML invoice file: %s", exc)
        rel_invoice_path = None

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
