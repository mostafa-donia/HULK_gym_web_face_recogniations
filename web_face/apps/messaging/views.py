import json
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q

from apps.accounts.decorators import manager_required
from apps.core.models import GymProfile
from apps.messaging.models import WhatsAppMessage, MessageStatus, MessageType
from apps.messaging.services import (
    dispatch_message_record,
    dispatch_all_pending,
    enqueue_message,
    prepare_due_reminders,
    prepare_manager_daily_report,
    filter_members_for_bulk,
    prepare_bulk_campaign,
    get_pending_summary,
)


@login_required
def whatsapp_queue_view(request):
    """
    Complete WhatsApp Management Dashboard matching screenshot:
    Search, filters, reminder generator, bulk campaign modal trigger,
    managerial report, and multi-select batch actions.
    """
    search_q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")
    type_filter = request.GET.get("msg_type", "all")

    qs = WhatsAppMessage.objects.all().order_by("-created_at")

    if search_q:
        qs = qs.filter(
            Q(recipient_name__icontains=search_q)
            | Q(mobile__icontains=search_q)
            | Q(message__icontains=search_q)
            | Q(error_detail__icontains=search_q)
        )

    if status_filter != "all" and status_filter in dict(MessageStatus.choices):
        qs = qs.filter(status=status_filter)

    if type_filter != "all" and type_filter in dict(MessageType.choices):
        qs = qs.filter(msg_type=type_filter)

    total_pending = WhatsAppMessage.objects.filter(status=MessageStatus.PENDING).count()
    total_sent = WhatsAppMessage.objects.filter(status=MessageStatus.SENT).count()
    total_failed = WhatsAppMessage.objects.filter(status=MessageStatus.FAILED).count()
    total_count = WhatsAppMessage.objects.count()

    profile = GymProfile.get_solo()
    pending_summary = get_pending_summary()

    context = {
        "messages_list": qs[:250],  # display latest 250
        "displayed_count": qs.count(),
        "search_q": search_q,
        "status_filter": status_filter,
        "type_filter": type_filter,
        "total_pending": total_pending,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "total_count": total_count,
        "status_choices": MessageStatus.choices,
        "type_choices": MessageType.choices,
        "gym_profile": profile,
        "pending_summary": pending_summary,
        "whatsapp_desktop_installed": pending_summary.get("desktop_installed", True),
        "whatsapp_desktop_status": pending_summary.get("desktop_status", ""),
        "open_send_pending": request.GET.get("open_send_pending") == "1",
    }
    return render(request, "messaging/whatsapp_queue.html", context)


@login_required
def whatsapp_bulk_send_view(request):
    """
    Handles submission from the Bulk Send modal (Category, Date Range, File/Photo, Link).
    """
    if request.method != "POST":
        return redirect("messaging:whatsapp_queue")

    category = request.POST.get("category", "non_sub")
    preset_range = request.POST.get("preset_range", "all")
    date_from_str = request.POST.get("date_from", "").strip()
    date_to_str = request.POST.get("date_to", "").strip()
    message_template = request.POST.get("message_template", "").strip()
    link = request.POST.get("link", "").strip()
    send_now = bool(request.POST.get("send_now"))
    attachment = request.FILES.get("attachment")

    date_from = None
    date_to = None
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    if not message_template:
        messages.error(request, "يرجى كتابة نص الرسالة للإرسال الجماعي.")
        return redirect("messaging:whatsapp_queue")

    res = prepare_bulk_campaign(
        category=category,
        message_template=message_template,
        link=link,
        attachment=attachment,
        date_from=date_from,
        date_to=date_to,
        preset_range=preset_range,
    )

    queued = res.get("queued", 0)
    if queued > 0:
        messages.success(request, f"🚀 تم تجهيز وإضافة {queued} رسالة إلى طابور الواتساب بنجاح!")
        if send_now:
            dispatch_res = dispatch_all_pending(limit=queued)
            messages.info(request, f"تمت معالجة الإرسال الفوري: {dispatch_res['sent']} مرسلة، {dispatch_res['failed']} فاشلة.")
    else:
        messages.warning(request, "لم يتم العثور على أي أعضاء مطابقين للشروط المحددة لتجهيز الرسائل لهم.")

    return redirect("messaging:whatsapp_queue")


@login_required
def whatsapp_count_recipients_api(request):
    """
    AJAX endpoint for live recipient count preview in the Bulk Send modal.
    """
    category = request.GET.get("category", "non_sub")
    preset_range = request.GET.get("preset_range", "all")
    date_from_str = request.GET.get("date_from", "").strip()
    date_to_str = request.GET.get("date_to", "").strip()

    date_from = None
    date_to = None
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    qs = filter_members_for_bulk(
        category=category,
        date_from=date_from,
        date_to=date_to,
        preset_range=preset_range,
    )
    return JsonResponse({"success": True, "count": qs.count()})


@login_required
def whatsapp_prepare_reminders_view(request):
    """
    Prepares due reminders (3 days, 1 day, expired).
    """
    res = prepare_due_reminders()
    queued = res.get("queued", 0)
    if queued > 0:
        messages.success(request, f"✓ تم فحص الاشتراكات وتجهيز {queued} رسالة تذكير في طابور الواتساب.")
    else:
        messages.info(request, "النظام محدث: لا توجد تذكيرات جديدة مستحقة التجهيز اليوم.")
    return redirect("messaging:whatsapp_queue")


@login_required
def whatsapp_manager_report_view(request):
    """
    Generates and queues today's managerial financial & attendance report.
    """
    profile = GymProfile.get_solo()
    if not profile.manager_mobile:
        messages.error(request, "لم يتم إدخال رقم هاتف المدير في الإعدادات لتجهيز التقرير.")
        return redirect("messaging:whatsapp_queue")

    success = prepare_manager_daily_report()
    if success:
        messages.success(request, f"✓ تم إعداد تقرير المدير اليومي وإضافته لطابور الإرسال للرقم ({profile.manager_mobile}).")
    else:
        messages.error(request, "تعذر تجهيز تقرير المدير اليومي.")
    return redirect("messaging:whatsapp_queue")


@login_required
def whatsapp_batch_action_view(request):
    """
    Processes batch actions from the toolbar (Send selected, resend failed, delete selected, etc.).
    """
    if request.method != "POST":
        return redirect("messaging:whatsapp_queue")

    action = request.POST.get("action", "")
    selected_ids = request.POST.getlist("selected_ids")

    if action == "send_pending":
        # Send all pending messages (up to 50)
        res = dispatch_all_pending(limit=50)
        if res["processed"] == 0:
            messages.info(request, "لا توجد رسائل معلقة حالياً في الطابور.")
        else:
            messages.info(request, f"تمت معالجة {res['processed']} رسالة: {res['sent']} نجاح، {res['failed']} فشل.")

    elif action in ["send_selected_pending", "send_selected"]:
        if not selected_ids:
            messages.warning(request, "يرجى تحديد رسالة واحدة على الأقل بالضغط على المربع بجانبها.")
        else:
            res = dispatch_all_pending(limit=len(selected_ids), selected_ids=selected_ids)
            messages.success(request, f"تمت معالجة إرسال {res['processed']} رسالة محددة: {res['sent']} نجاح، {res['failed']} فشل.")

    elif action == "send_10_pending":
        res = dispatch_all_pending(limit=10)
        messages.success(request, f"تمت معالجة دفعة 10 رسائل معلقة: {res['sent']} نجاح، {res['failed']} فشل.")

    elif action == "resend_selected":
        # Reset selected to pending and send
        if not selected_ids:
            messages.warning(request, "يرجى تحديد رسالة واحدة على الأقل بالضغط على المربع بجانبها.")
        else:
            msgs = WhatsAppMessage.objects.filter(id__in=selected_ids)
            msgs.update(status=MessageStatus.PENDING, error_detail="")
            for m in msgs:
                dispatch_message_record(m)
            messages.success(request, f"تمت إعادة إرسال {len(msgs)} رسالة محددة.")

    elif action == "force_resend_selected":
        # Force send selected even if marked SENT
        if not selected_ids:
            messages.warning(request, "يرجى تحديد رسائل لتنفيذ الإرسال القسري.")
        else:
            msgs = WhatsAppMessage.objects.filter(id__in=selected_ids)
            for m in msgs:
                dispatch_message_record(m)
            messages.success(request, f"تم تنفيذ الإرسال القسري لـ {len(msgs)} رسالة.")

    elif action == "resend_failed_to_pending":
        # Re-queue all failed to pending
        count = WhatsAppMessage.objects.filter(status=MessageStatus.FAILED).update(status=MessageStatus.PENDING, error_detail="")
        messages.success(request, f"تمت إعادة {count} رسالة فاشلة إلى حالة المعلق (جاهز للإرسال).")

    elif action == "delete_selected":
        if not selected_ids:
            messages.warning(request, "يرجى تحديد رسائل لحذفها.")
        else:
            deleted_count, _ = WhatsAppMessage.objects.filter(id__in=selected_ids).delete()
            messages.success(request, f"تم حذف {deleted_count} رسالة محددة من الطابور.")

    elif action == "delete_sent":
        count, _ = WhatsAppMessage.objects.filter(status=MessageStatus.SENT).delete()
        messages.success(request, f"تم حذف {count} رسالة مرسلة بنجاح من الأرشيف.")

    elif action == "delete_failed":
        count, _ = WhatsAppMessage.objects.filter(status=MessageStatus.FAILED).delete()
        messages.success(request, f"تم حذف {count} رسالة فاشلة من الطابور.")

    elif action == "delete_all":
        count, _ = WhatsAppMessage.objects.all().delete()
        messages.success(request, f"تم تفريغ طابور الواتساب بالكامل ({count} رسالة).")

    return redirect("messaging:whatsapp_queue")


@login_required
def whatsapp_retry_view(request, message_id):
    """Resets a single message to pending."""
    msg_obj = get_object_or_404(WhatsAppMessage, id=message_id)
    msg_obj.status = MessageStatus.PENDING
    msg_obj.error_detail = ""
    msg_obj.save()
    messages.success(request, f"تمت إعادة تعيين الرسالة للمستلم {msg_obj.recipient_name or msg_obj.mobile} للإرسال مجدداً.")
    return redirect("messaging:whatsapp_queue")


@login_required
def whatsapp_dispatch_now_view(request):
    """Dispatches batch of pending messages."""
    res = dispatch_all_pending(limit=25)
    if res["processed"] == 0:
        messages.info(request, "لا توجد رسائل معلقة في الطابور حالياً.")
    else:
        messages.info(
            request,
            f"تمت معالجة {res['processed']} رسالة: {res['sent']} تم الإرسال بنجاح، و {res['failed']} فشل."
        )
    return redirect("messaging:whatsapp_queue")


@login_required
def whatsapp_compose_view(request):
    """Enqueues a custom direct WhatsApp message to any number."""
    if request.method == "POST":
        mobile = request.POST.get("mobile", "").strip()
        recipient_name = request.POST.get("recipient_name", "").strip()
        message_text = request.POST.get("message", "").strip()
        link = request.POST.get("link", "").strip()
        attachment = request.FILES.get("attachment")

        if not mobile or not message_text:
            messages.error(request, "يرجى كتابة رقم الهاتف ونص الرسالة.")
        else:
            enqueue_message(
                mobile=mobile,
                message=message_text,
                msg_type=MessageType.CUSTOM,
                recipient_name=recipient_name,
                recipient_type="member",
                link=link,
                attachment=attachment,
            )
            messages.success(request, "تمت إضافة الرسالة إلى طابور الواتساب بنجاح.")
            return redirect("messaging:whatsapp_queue")

    return render(request, "messaging/compose.html")


@login_required
def whatsapp_delete_view(request, message_id):
    """Removes a single message from the queue."""
    msg_obj = get_object_or_404(WhatsAppMessage, id=message_id)
    msg_obj.delete()
    messages.info(request, "تم حذف الرسالة من الطابور.")
    return redirect("messaging:whatsapp_queue")


@login_required
def whatsapp_pending_summary_api(request):
    """
    Returns live count and breakdown of pending routine messages
    for the 30-min reminder overlay and the send pending modal.
    """
    summary = get_pending_summary()
    return JsonResponse({"success": True, **summary})


@login_required
def whatsapp_pending_messages_api(request):
    """
    Returns pending messages for the send pending modal with filtering by routine type.
    """
    msg_type = request.GET.get("msg_type", "all").strip()
    search = request.GET.get("q", "").strip()

    qs = WhatsAppMessage.objects.filter(status=MessageStatus.PENDING).order_by("created_at")

    if msg_type and msg_type != "all":
        if msg_type == "other":
            routine_types = [MessageType.RECEIPT, MessageType.REMINDER_1, MessageType.REMINDER_3, MessageType.EXPIRED]
            qs = qs.exclude(msg_type__in=routine_types)
        elif msg_type in dict(MessageType.choices):
            qs = qs.filter(msg_type=msg_type)

    if search:
        qs = qs.filter(
            Q(recipient_name__icontains=search)
            | Q(mobile__icontains=search)
            | Q(message__icontains=search)
        )

    items = []
    for m in qs[:250]:
        items.append({
            "id": m.id,
            "recipient_name": m.recipient_name or "عضو",
            "mobile": m.mobile,
            "msg_type": m.msg_type,
            "msg_type_display": m.get_msg_type_display(),
            "message": m.message,
            "has_attachment": bool(m.attachment),
            "attachment_url": m.attachment.url if m.attachment else "",
            "link": m.link or "",
            "created_at": m.created_at.strftime("%Y-%m-%d %H:%M"),
        })

    summary = get_pending_summary()

    return JsonResponse({
        "success": True,
        "count": len(items),
        "messages": items,
        "summary": summary,
    })


@login_required
def whatsapp_dispatch_batch_api(request):
    """
    AJAX endpoint to dispatch a batch of pending messages (e.g. 10 now, or specific selected IDs).
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required"}, status=405)

    limit = 10
    selected_ids = []
    msg_type = None

    # Support application/json or x-www-form-urlencoded
    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            body = json.loads(request.body.decode("utf-8")) if request.body else {}
            selected_ids = body.get("selected_ids", [])
            limit = int(body.get("limit", 10) or 10)
            msg_type = body.get("msg_type") or None
        except Exception:
            pass
    else:
        limit = int(request.POST.get("limit", 10) or 10)
        selected_ids = request.POST.getlist("selected_ids")
        msg_type = request.POST.get("msg_type") or None

    if selected_ids:
        # If specific IDs were selected, ensure limit is at least length of selected
        limit = max(limit, len(selected_ids))

    res = dispatch_all_pending(limit=limit, selected_ids=selected_ids if selected_ids else None, msg_type=msg_type)
    summary = get_pending_summary()

    if res.get("desktop_installed") is False:
        return JsonResponse({
            "success": False,
            "error": res.get("error", "تطبيق واتساب للكمبيوتر غير مثبت على هذا الجهاز."),
            "desktop_installed": False,
            "summary": summary,
        }, status=400)

    return JsonResponse({
        "success": True,
        "processed": res["processed"],
        "sent": res["sent"],
        "failed": res["failed"],
        "desktop_installed": True,
        "summary": summary,
    })
