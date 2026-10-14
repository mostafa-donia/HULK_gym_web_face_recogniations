from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.models import GymProfile
from apps.members.models import Member
from apps.messaging.models import MessageType, WhatsAppMessage
from apps.payments.models import Payment, PaymentMethod, PaymentOperationType


def generate_next_payment_id() -> tuple[str, str]:
    latest = Payment.objects.order_by("-id").first()
    num = 1
    if latest and latest.payment_id.startswith("PAY-"):
        try:
            num = int(latest.payment_id.replace("PAY-", "")) + 1
        except Exception:
            num = Payment.objects.count() + 1
    return f"PAY-{num:05d}", f"INV-{num:05d}"


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

    context = {
        "payment": payment,
        "profile": profile,
        "member": payment.member,
        "subscription": payment.subscription,
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
            member.save(update_fields=["current_remaining", "total_paid", "last_payment_date"])

            # Queue WhatsApp receipt
            if member.mobile and profile.whatsapp_enabled:
                receipt_text = (
                    f"إيصال سداد متبقي من {profile.gym_name}\n"
                    f"أهلاً {member.name}\n"
                    f"المبلغ المسدد: {amount} {profile.currency}\n"
                    f"المتبقي النهائي: {member.current_remaining} {profile.currency}\n"
                    f"رقم الإيصال: {payment.invoice_no}\n"
                    f"شكراً لك 💪"
                )
                dedup_key = f"debt_receipt:{member.mobile}:{payment.id}"
                WhatsAppMessage.objects.get_or_create(
                    dedup_key=dedup_key,
                    defaults={
                        "mobile": member.mobile,
                        "message": receipt_text,
                        "msg_type": MessageType.RECEIPT,
                        "recipient_name": member.name,
                        "recipient_type": "member",
                        "status": "pending",
                    },
                )

        messages.success(request, f"تم تسجيل سداد {amount} {profile.currency} من متبقي العضو {member.name} بنجاح!")
        return redirect("payments:payment_detail", payment_id=payment.id)

    context = {
        "member": member,
        "payment_methods": payment_methods,
        "profile": profile,
    }
    return render(request, "payments/settle_debt.html", context)
