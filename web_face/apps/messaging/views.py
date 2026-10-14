from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.messaging.models import WhatsAppMessage, MessageStatus, MessageType
from apps.messaging.services import dispatch_message_record, dispatch_all_pending, enqueue_message


@login_required
def whatsapp_queue_view(request):
    """
    Displays the WhatsApp outgoing message queue with filters and statuses.
    Accessible to Manager and Assistant.
    """
    status_filter = request.GET.get("status", "all")
    qs = WhatsAppMessage.objects.all()

    if status_filter != "all" and status_filter in dict(MessageStatus.choices):
        qs = qs.filter(status=status_filter)

    total_pending = WhatsAppMessage.objects.filter(status=MessageStatus.PENDING).count()
    total_sent = WhatsAppMessage.objects.filter(status=MessageStatus.SENT).count()
    total_failed = WhatsAppMessage.objects.filter(status=MessageStatus.FAILED).count()

    context = {
        "messages_list": qs[:100],  # Show latest 100
        "status_filter": status_filter,
        "total_pending": total_pending,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "status_choices": MessageStatus.choices,
    }
    return render(request, "messaging/whatsapp_queue.html", context)


@login_required
def whatsapp_retry_view(request, message_id):
    """
    Resets a failed message status back to pending.
    """
    msg_obj = get_object_or_404(WhatsAppMessage, id=message_id)
    msg_obj.status = MessageStatus.PENDING
    msg_obj.error_detail = ""
    msg_obj.save()
    messages.success(request, f"تمت إعادة تعيين الرسالة للمستلم {msg_obj.recipient_name or msg_obj.mobile} للإرسال مجدداً.")
    return redirect("messaging:whatsapp_queue")


@login_required
def whatsapp_dispatch_now_view(request):
    """
    Attempts to dispatch pending messages in the queue now.
    """
    res = dispatch_all_pending(limit=10)
    if res["processed"] == 0:
        messages.info(request, "لا توجد رسائل معلقة في الطابور حالياً.")
    else:
        messages.info(
            request,
            f"تمت معالجة {res['processed']} رسالة: {res['sent']} تم الإرسال بنجاح، و {res['failed']} فشل (تحقق من تشغيل برنامج الواتساب)."
        )
    return redirect("messaging:whatsapp_queue")


@login_required
def whatsapp_compose_view(request):
    """
    Enqueues a custom direct WhatsApp message to any number.
    """
    if request.method == "POST":
        mobile = request.POST.get("mobile", "").strip()
        recipient_name = request.POST.get("recipient_name", "").strip()
        message_text = request.POST.get("message", "").strip()

        if not mobile or not message_text:
            messages.error(request, "يرجى كتابة رقم الهاتف ونص الرسالة.")
        else:
            enqueue_message(
                mobile=mobile,
                message=message_text,
                msg_type=MessageType.CUSTOM,
                recipient_name=recipient_name,
                recipient_type="member",
            )
            messages.success(request, "تمت إضافة الرسالة إلى طابور الواتساب بنجاح.")
            return redirect("messaging:whatsapp_queue")

    return render(request, "messaging/compose.html")


@login_required
def whatsapp_delete_view(request, message_id):
    """
    Removes a message from the queue.
    """
    msg_obj = get_object_or_404(WhatsAppMessage, id=message_id)
    msg_obj.delete()
    messages.info(request, "تم حذف الرسالة من الطابور.")
    return redirect("messaging:whatsapp_queue")
