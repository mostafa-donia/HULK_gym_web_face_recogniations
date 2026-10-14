import logging
from django.utils import timezone
from apps.messaging.models import WhatsAppMessage, MessageStatus, MessageType

logger = logging.getLogger(__name__)


def enqueue_message(mobile: str, message: str, msg_type: str = MessageType.CUSTOM, recipient_name: str = "", recipient_type: str = "member", dedup_key: str = None) -> WhatsAppMessage:
    """
    Enqueues a message for WhatsApp delivery with deduplication.
    """
    if not mobile or not message:
        return None

    # Clean phone number
    cleaned_mobile = "".join(filter(str.isdigit, str(mobile)))
    if not cleaned_mobile:
        return None

    # Generate dedup_key if not provided
    if not dedup_key:
        dedup_key = f"{cleaned_mobile}_{msg_type}_{timezone.localdate().isoformat()}"

    existing = WhatsAppMessage.objects.filter(dedup_key=dedup_key).first()
    if existing:
        return existing

    return WhatsAppMessage.objects.create(
        mobile=cleaned_mobile,
        message=message.strip(),
        msg_type=msg_type,
        recipient_name=recipient_name.strip(),
        recipient_type=recipient_type,
        status=MessageStatus.PENDING,
        dedup_key=dedup_key,
    )


def dispatch_message_record(msg_obj: WhatsAppMessage) -> bool:
    """
    Attempts delivery of a single WhatsApp message using whatsapp_sender.
    Captures errors gracefully and updates database record.
    """
    try:
        from apps.messaging import whatsapp_sender
        # Verify WhatsApp window readiness
        # If WhatsApp is not open/ready or headless, handle gracefully
        success = whatsapp_sender.send_message(
            phone=msg_obj.mobile,
            message=msg_obj.message,
        )
        if success:
            msg_obj.status = MessageStatus.SENT
            msg_obj.sent_at = timezone.now()
            msg_obj.error_detail = ""
            msg_obj.save()
            return True
        else:
            msg_obj.status = MessageStatus.FAILED
            msg_obj.error_detail = "WhatsApp sender returned unsuccessful (window not active or chat not found)."
            msg_obj.save()
            return False
    except Exception as exc:
        logger.exception("Failed to dispatch WhatsApp message %s", msg_obj.id)
        msg_obj.status = MessageStatus.FAILED
        msg_obj.error_detail = str(exc)
        msg_obj.save()
        return False


def dispatch_all_pending(limit: int = 20) -> dict:
    """
    Dispatches a batch of pending messages.
    """
    pending = WhatsAppMessage.objects.filter(status=MessageStatus.PENDING).order_by("created_at")[:limit]
    sent_count = 0
    failed_count = 0

    for msg in pending:
        if dispatch_message_record(msg):
            sent_count += 1
        else:
            failed_count += 1

    return {
        "processed": len(pending),
        "sent": sent_count,
        "failed": failed_count,
    }
