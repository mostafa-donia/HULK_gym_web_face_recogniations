from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.models import GymProfile
from apps.members.models import Member
from apps.messaging.models import MessageType, WhatsAppMessage
from apps.payments.models import Payment, PaymentMethod, PaymentOperationType
from apps.payments.services import queue_payment_receipt_whatsapp


def generate_next_payment_id() -> tuple[str, str]:
    """
    Safely generates the next unique sequential (PAY-XXXXX, INV-XXXXX) pair.
    Finds the true maximum existing number across all payments and guarantees uniqueness.
    """
    import re
    max_num = 0
    for pid, inv in Payment.objects.values_list("payment_id", "invoice_no"):
        for val in (pid, inv):
            if val:
                match = re.search(r"\d+", str(val))
                if match:
                    num_val = int(match.group())
                    if num_val > max_num:
                        max_num = num_val

    next_num = max(max_num + 1, Payment.objects.count() + 1, 1)
    while Payment.objects.filter(
        Q(payment_id=f"PAY-{next_num:05d}") | Q(invoice_no=f"INV-{next_num:05d}")
    ).exists():
        next_num += 1

    return f"PAY-{next_num:05d}", f"INV-{next_num:05d}"


@login_required
def payment_list_view(request):
    query = request.GET.get("q", "").strip()
    payments = Payment.objects.select_related("member").all().order_by("-created_at")

    if query:
        payments = payments.filter(
            Q(invoice_no__icontains=query)
            | Q(payment_id__icontains=query)
            | Q(member__name__icontains=query)
            | Q(member__mobile__icontains=query)
        )

    paginator = Paginator(payments, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "query": query,
        "total_count": payments.count(),
    }
    return render(request, "payments/payment_list.html", context)


@login_required
def payment_detail_view(request, payment_id):
    """Printable invoice receipt view for standard browser printing (no POS needed)."""
    payment = get_object_or_404(Payment.objects.select_related("member", "subscription", "created_by"), id=payment_id)
    profile = GymProfile.get_solo()
    auto_redirect = request.GET.get("auto") == "1"

    context = {
        "payment": payment,
        "profile": profile,
        "member": payment.member,
        "subscription": payment.subscription,
        "auto_redirect": auto_redirect,
    }
    return render(request, "payments/payment_receipt.html", context)


@login_required
def settle_debt_view(request, member_id):
    """Settle outstanding remaining balance for a member."""
    member = get_object_or_404(Member, id=member_id)
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    profile = GymProfile.get_solo()

    if request.method == "POST":
        amount = Decimal(request.POST.get("amount", "0.00") or "0.00")
        payment_method = request.POST.get("payment_method", "نقدي")
        notes = request.POST.get("notes", "").strip()

        if amount <= 0:
            messages.error(request, "المبلغ المدفوع يجب أن يكون أكبر من الصفر.")
            return redirect("payments:settle_debt", member_id=member.id)

        if amount > member.current_remaining:
            messages.error(request, f"المبلغ المدفوع ({amount}) أكبر من المتبقي على العضو ({member.current_remaining}).")
            return redirect("payments:settle_debt", member_id=member.id)

        with transaction.atomic():
            pay_id, inv_no = generate_next_payment_id()
            payment = Payment.objects.create(
                payment_id=pay_id,
                invoice_no=inv_no,
                operation_type=PaymentOperationType.REMAINING,
                member=member,
                amount=amount,
                payment_method=payment_method,
                notes=notes or "سداد متبقي اشتراك",
                created_by=request.user,
            )

            member.current_remaining = max(Decimal("0.00"), member.current_remaining - amount)
            member.total_paid += amount
            member.last_payment_date = payment.created_at
            if member.current_remaining <= Decimal("0.00"):
                member.follow_up_date = None
            member.save(update_fields=["current_remaining", "total_paid", "last_payment_date", "follow_up_date"])

            # Queue WhatsApp receipt with HTML invoice
            queue_payment_receipt_whatsapp(payment)

        messages.success(request, f"تم تسجيل سداد {amount} {profile.currency} من متبقي العضو {member.name} بنجاح!")
        return redirect(f"/payments/{payment.id}/?auto=1")

    context = {
        "member": member,
        "payment_methods": payment_methods,
        "profile": profile,
    }
    return render(request, "payments/settle_debt.html", context)


@login_required
def download_invoice_html_view(request, payment_id):
    """Generates and serves the standalone HTML invoice as a direct download file."""
    payment = get_object_or_404(Payment, id=payment_id)
    from apps.payments.services import generate_invoice_html_file
    rel_path = generate_invoice_html_file(payment)

    from django.conf import settings
    from pathlib import Path
    full_path = Path(settings.MEDIA_ROOT) / rel_path

    if full_path.exists():
        content = full_path.read_text(encoding="utf-8")
    else:
        from django.template.loader import render_to_string
        content = render_to_string("payments/invoice_standalone.html", {
            "payment": payment,
            "member": payment.member,
            "profile": GymProfile.get_solo(),
        })

    response = HttpResponse(content, content_type="text/html; charset=utf-8")
    clean_no = payment.invoice_no.replace("/", "_")
    response["Content-Disposition"] = f'attachment; filename="invoice_{clean_no}.html"'
    return response


@login_required
def send_receipt_whatsapp_now_view(request, payment_id):
    """Queues and immediately attempts to dispatch the HTML invoice via WhatsApp."""
    payment = get_object_or_404(Payment, id=payment_id)
    msg_obj = queue_payment_receipt_whatsapp(payment)

    if not msg_obj:
        messages.error(request, "تعذر إرسال الفاتورة: لا يوجد رقم هاتف مسجل للعضو أو أن خدمة الواتساب معطلة.")
        return redirect("payments:payment_detail", payment_id=payment.id)

    from apps.messaging.models import MessageStatus
    from apps.messaging.services import dispatch_message_record, promote_due_scheduled_messages

    promote_due_scheduled_messages()
    msg_obj.refresh_from_db()

    if msg_obj.status == MessageStatus.SCHEDULED and msg_obj.send_after and msg_obj.send_after > timezone.now() and request.GET.get("force") != "1":
        rem_mins = max(1, int((msg_obj.send_after - timezone.now()).total_seconds() // 60) + 1)
        local_time = timezone.localtime(msg_obj.send_after).strftime("%I:%M %p")
        messages.info(
            request,
            f"⏳ هذا رقم هاتف عضو جديد يتم مزامنته الآن مع جهات اتصال Google Contacts. "
            f"تمت جدولة إرسال الفاتورة تلقائياً بعد {rem_mins} دقيقة (الساعة {local_time}) لضمان ظهور الاسم في الواتساب."
        )
        return redirect("payments:payment_detail", payment_id=payment.id)

    dispatched = dispatch_message_record(msg_obj, return_to_system=True)

    if dispatched:
        messages.success(request, f"✓ تم إرسال الفاتورة الرسمية بنجاح إلى هاتف {payment.member.name} عبر الواتساب!")
    else:
        messages.warning(request, f"تمت إضافة الفاتورة لطابور رسائل الواتساب (يرجى التأكد من تشغيل نافذة WhatsApp Desktop).")

    return redirect("payments:payment_detail", payment_id=payment.id)


