import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.template.loader import render_to_string
from PIL import Image, ImageDraw, ImageFont

from apps.core.models import GymProfile
from apps.core.text_utils import reshape_arabic, get_arabic_font
from apps.messaging.models import WhatsAppMessage, MessageType, MessageStatus
from apps.payments.models import Payment, PaymentOperationType

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

    font_title = get_arabic_font(size=25, bold=True)
    font_sub = get_arabic_font(size=16, bold=False)
    font_bold = get_arabic_font(size=18, bold=True)
    font_normal = get_arabic_font(size=16, bold=False)
    font_sm = get_arabic_font(size=16, bold=False)

    raw_gym_name = profile.gym_name or "سينا سبا | CINA SPA"
    curr = profile.currency or "ج.م"
    theme_rgb = profile.get_primary_color_rgb() if hasattr(profile, "get_primary_color_rgb") else (225, 29, 72)

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
            c_name = subscription.coach.name.replace("كابتن", "").strip() if subscription.coach else ""
            coach_str = f"كابتن {c_name}" if c_name else "مدرب خاص"
            priv_text = f"{coach_str} ({subscription.private_price} {curr})"
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

    remaining_info = f"المتبقي دين: {member.current_remaining} {profile.currency}" if member.current_remaining > 0 else "الحساب: خالص السداد بالكامل ✓"

    is_new_member = (payment.operation_type == PaymentOperationType.NEW_SUBSCRIPTION) or (
        member.subscriptions.count() <= 1 and payment.operation_type not in [PaymentOperationType.RENEWAL, PaymentOperationType.BAR_SALE, PaymentOperationType.REFUND]
    )
    target_msg_type = MessageType.WELCOME if is_new_member else MessageType.RECEIPT

    if getattr(profile, "whatsapp_randomize_templates", True):
        from apps.messaging.message_bank import get_random_message
        ctx = {
            "name": member.name,
            "gym_name": profile.gym_name or "Systemize Gym",
            "member_id": member.member_id,
            "amount": f"{payment.amount}",
            "amount_paid": f"{payment.amount}",
            "currency": profile.currency or "جنيه",
            "invoice_no": payment.invoice_no,
            "remaining": f"{member.current_remaining}",
            "remaining_amount": f"{member.current_remaining}",
            "remaining_text": remaining_info,
            "date": payment.created_at.strftime("%Y-%m-%d"),
            "today": payment.created_at.strftime("%Y-%m-%d"),
            "plan": subscription.plan_name if subscription else op_name,
            "plan_name": subscription.plan_name if subscription else op_name,
            "phone": member.mobile,
        }
        category_key = "welcome" if is_new_member else "receipt"
        receipt_text = get_random_message(category_key, ctx)
        if sub_info and not is_new_member:
            receipt_text += f"\n{sub_info}"
        if "مرفق" not in receipt_text:
            receipt_text += "\nمرفق الفاتورة الإلكترونية الرسمية 📄"
    else:
        if is_new_member:
            receipt_text = (
                f"🎉 مرحباً بك كابتن {member.name} في عائلة {profile.gym_name}!\n"
                f"نورتنا وشرفتنا بانضمامك كعضو جديد معنا 💪\n"
                f"كود العضوية الخاص بك: {member.member_id} 🪪\n"
                f"الباقة المسجلة: {subscription.plan_name if subscription else op_name}\n"
                f"المبلغ المسدد: {payment.amount} {profile.currency}\n"
                f"{remaining_info}\n"
                f"{sub_info}\n"
                f"مرفق الفاتورة الإلكترونية الرسمية 📄\n"
                f"كل كباتن وإدارة الجيم في خدمتك ومتحمسين لرحلتك الرياضية معنا! 🚀"
            )
        else:
            receipt_text = (
                f"إيصال مالي رسمي من {profile.gym_name}\n"
                f"أهلاً كابتن {member.name} 👋\n"
                f"نوع العملية: {op_name}\n"
                f"رقم الفاتورة: {payment.invoice_no}\n"
                f"المبلغ المدفوع: {payment.amount} {profile.currency}\n"
                f"{remaining_info}"
                f"{sub_info}\n"
                f"مرفق الفاتورة الإلكترونية الرسمية 📄\n"
                f"شكراً لاختيارك {profile.gym_name} 💪"
            )

    clean_invoice_no = payment.invoice_no.replace("/", "_").replace("\\", "_")
    dedup_key = f"{'welcome' if is_new_member else 'receipt'}:{member.mobile}:{clean_invoice_no}"

    from django.utils import timezone
    from apps.messaging.services import get_first_time_send_after

    send_after = get_first_time_send_after(member.mobile, member=member)
    initial_status = MessageStatus.SCHEDULED if (send_after and send_after > timezone.now()) else MessageStatus.PENDING

    msg_obj, created = WhatsAppMessage.objects.get_or_create(
        dedup_key=dedup_key,
        defaults={
            "mobile": member.mobile,
            "message": receipt_text,
            "msg_type": target_msg_type,
            "recipient_name": member.name,
            "recipient_type": "member",
            "attachment": rel_invoice_path or "",
            "status": initial_status,
            "send_after": send_after,
        },
    )

    if not created and rel_invoice_path:
        msg_obj.attachment = rel_invoice_path
        msg_obj.message = receipt_text
        msg_obj.save(update_fields=["attachment", "message"])

    return msg_obj


# =========================================================================
# 💰 MULTI-TREASURY FINANCIAL ACCOUNTS & INTERNAL TRANSFERS SERVICE
# =========================================================================

import uuid
from django.db import transaction
from django.db.models import Sum, Q


def resolve_account_for_payment_method(payment_method_name, branch=None):
    from apps.payments.models import FinancialAccount, AccountType
    if not payment_method_name:
        payment_method_name = "نقدي"
    pm_clean = str(payment_method_name).strip().lower()

    # 1. Match Vodafone Cash / Electronic Wallet
    if any(k in pm_clean for k in ["فودافون", "vodafone", "محفظة", "wallet", "كاش إلكتروني", "electronic"]):
        acc = FinancialAccount.objects.filter(account_type=AccountType.VODAFONE_CASH, is_active=True).first()
        if not acc:
            acc = FinancialAccount.objects.filter(name__icontains="فودافون", is_active=True).first()
        if acc:
            return acc

    # 2. Match Bank / InstaPay / Visa / Card
    if any(k in pm_clean for k in ["انستا", "إنستا", "insta", "بنك", "bank", "فيزا", "visa", "بطاقة", "card", "pos"]):
        acc = FinancialAccount.objects.filter(account_type=AccountType.BANK, is_active=True).first()
        if not acc:
            acc = FinancialAccount.objects.filter(name__icontains="بنك", is_active=True).first()
        if acc:
            return acc

    # 3. Default to Cash account
    acc = FinancialAccount.objects.filter(account_type=AccountType.CASH, is_active=True).first()
    if not acc:
        acc = FinancialAccount.objects.filter(name__icontains="كاش", is_active=True).first()
    if not acc:
        FinancialAccount.get_default_accounts(branch=branch)
        acc = FinancialAccount.objects.filter(account_type=AccountType.CASH, is_active=True).first()
    return acc


def get_account_balance_details(account, branch=None):
    """
    Computes real-time inflows, outflows, transfers in/out, and net balance for a FinancialAccount.
    """
    from apps.payments.models import Payment, MoneyTransfer, AccountType
    from apps.expenses.models import Expense

    payments_qs = Payment.objects.all()
    expenses_qs = Expense.objects.all()
    transfers_in_qs = MoneyTransfer.objects.filter(to_account=account)
    transfers_out_qs = MoneyTransfer.objects.filter(from_account=account)

    if branch:
        payments_qs = payments_qs.filter(branch=branch)
        expenses_qs = expenses_qs.filter(branch=branch)
        transfers_in_qs = transfers_in_qs.filter(branch=branch)
        transfers_out_qs = transfers_out_qs.filter(branch=branch)

    # Inflows: Payments explicitly assigned or matching this account type
    if account.account_type == AccountType.CASH:
        p_filter = Q(account=account) | (
            Q(account__isnull=True) & (
                Q(payment_method__icontains="نقد") |
                Q(payment_method__icontains="كاش") |
                Q(payment_method__icontains="cash") |
                Q(payment_method="")
            )
        )
    elif account.account_type == AccountType.VODAFONE_CASH:
        p_filter = Q(account=account) | (
            Q(account__isnull=True) & (
                Q(payment_method__icontains="فودافون") |
                Q(payment_method__icontains="vodafone") |
                Q(payment_method__icontains="محفظة") |
                Q(payment_method__icontains="wallet")
            )
        )
    elif account.account_type == AccountType.BANK:
        p_filter = Q(account=account) | (
            Q(account__isnull=True) & (
                Q(payment_method__icontains="انستا") |
                Q(payment_method__icontains="إنستا") |
                Q(payment_method__icontains="insta") |
                Q(payment_method__icontains="بنك") |
                Q(payment_method__icontains="bank") |
                Q(payment_method__icontains="فيزا") |
                Q(payment_method__icontains="visa") |
                Q(payment_method__icontains="بطاقة") |
                Q(payment_method__icontains="pos")
            )
        )
    else:
        p_filter = Q(account=account)

    total_inflows = payments_qs.filter(p_filter).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    # Outflows: Expenses explicitly assigned, or if cash, unassigned expenses default to cash
    if account.account_type == AccountType.CASH:
        e_filter = Q(account=account) | Q(account__isnull=True)
    else:
        e_filter = Q(account=account)

    total_outflows = expenses_qs.filter(e_filter).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    # Transfers
    transfers_in = transfers_in_qs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    transfers_out = transfers_out_qs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    current_balance = (
        Decimal(str(account.initial_balance or "0.00"))
        + total_inflows
        - total_outflows
        + transfers_in
        - transfers_out
    )

    return {
        "account": account,
        "initial_balance": Decimal(str(account.initial_balance or "0.00")),
        "inflows": total_inflows,
        "outflows": total_outflows,
        "transfers_in": transfers_in,
        "transfers_out": transfers_out,
        "current_balance": current_balance,
    }


def get_all_financial_accounts_summary(branch=None):
    """
    Returns balance details for all active financial accounts, plus overall totals.
    """
    from apps.payments.models import FinancialAccount
    FinancialAccount.get_default_accounts(branch=branch)
    accounts = FinancialAccount.objects.filter(is_active=True).order_by("id")

    items = []
    total_balance = Decimal("0.00")
    total_inflows = Decimal("0.00")
    total_outflows = Decimal("0.00")

    for acc in accounts:
        details = get_account_balance_details(acc, branch=branch)
        items.append(details)
        total_balance += details["current_balance"]
        total_inflows += details["inflows"]
        total_outflows += details["outflows"]

    return {
        "accounts_details": items,
        "total_balance": total_balance,
        "total_inflows": total_inflows,
        "total_outflows": total_outflows,
    }


def execute_money_transfer(from_account, to_account, amount, fee=Decimal("0.00"), transfer_date=None, reference_no="", notes="", user=None, branch=None):
    """
    Executes an internal transfer between financial accounts with fee deduction.
    """
    from apps.payments.models import MoneyTransfer
    from apps.expenses.models import Expense, ExpenseCategory
    from django.utils import timezone

    if from_account.id == to_account.id:
        raise ValueError("لا يمكن التحويل من وإلى نفس الحساب المالي.")

    amount = Decimal(str(amount or "0.00"))
    fee = Decimal(str(fee or "0.00"))

    if amount <= Decimal("0.00"):
        raise ValueError("مبلغ التحويل يجب أن يكون أكبر من الصفر.")

    if fee < Decimal("0.00"):
        raise ValueError("رسوم التحويل لا يمكن أن تكون قيمة سالبة.")

    if not transfer_date:
        transfer_date = timezone.localdate()

    transfer_id = f"TRF-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    with transaction.atomic():
        transfer = MoneyTransfer.objects.create(
            transfer_id=transfer_id,
            from_account=from_account,
            to_account=to_account,
            amount=amount,
            fee=fee,
            transfer_date=transfer_date,
            reference_no=reference_no or "",
            notes=notes or "",
            created_by=user,
            branch=branch,
        )

        # If there is a transfer fee, record it as an Expense automatically
        if fee > Decimal("0.00"):
            category, _ = ExpenseCategory.objects.get_or_create(
                name="رسوم ومصاريف تحويلات بنكية ومحافظ",
                defaults={"is_active": True},
            )
            Expense.objects.create(
                category=category,
                amount=fee,
                account=from_account,
                description=f"رسوم تحويل مبلغ {amount} ج.م من {from_account.name} إلى {to_account.name} (رقم التحويل: {transfer_id})",
                expense_date=transfer_date,
                created_by=user,
                branch=branch,
            )

        return transfer

