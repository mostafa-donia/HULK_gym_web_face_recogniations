import re
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.http import HttpResponse, JsonResponse, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.models import GymProfile, AuditLog
from apps.members.models import Member
from apps.messaging.models import MessageType, WhatsAppMessage
from apps.payments.models import (
    Payment,
    PaymentMethod,
    PaymentOperationType,
    BarProduct,
    BarSale,
    BarProductCategory,
)
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
    from apps.core.branch_context import filter_by_branch
    import datetime

    query = request.GET.get("q", "").strip()
    operation_type = request.GET.get("operation_type", "").strip()
    payment_method = request.GET.get("payment_method", "").strip()
    period = request.GET.get("period", "").strip()
    date_from_str = request.GET.get("date_from", "").strip()
    date_to_str = request.GET.get("date_to", "").strip()

    payments = Payment.objects.select_related("member", "created_by").all().order_by("-created_at")
    payments = filter_by_branch(payments, request)

    # 1. Search Query Filter
    if query:
        payments = payments.filter(
            Q(invoice_no__icontains=query)
            | Q(payment_id__icontains=query)
            | Q(member__name__icontains=query)
            | Q(member__mobile__icontains=query)
            | Q(notes__icontains=query)
        )

    # 2. Operation Type Filter
    if operation_type and operation_type != "all":
        payments = payments.filter(operation_type=operation_type)

    # 3. Payment Method Filter
    if payment_method and payment_method != "all":
        payments = payments.filter(payment_method=payment_method)

    # 4. Time / Period Filter
    today = timezone.localdate()
    if period == "today":
        payments = payments.filter(created_at__date=today)
    elif period == "yesterday":
        payments = payments.filter(created_at__date=today - datetime.timedelta(days=1))
    elif period == "this_week":
        start_week = today - datetime.timedelta(days=today.weekday())
        payments = payments.filter(created_at__date__gte=start_week)
    elif period == "this_month":
        payments = payments.filter(created_at__year=today.year, created_at__month=today.month)
    else:
        # Custom dates if provided
        if date_from_str:
            try:
                df = datetime.datetime.strptime(date_from_str, "%Y-%m-%d").date()
                payments = payments.filter(created_at__date__gte=df)
            except ValueError:
                pass
        if date_to_str:
            try:
                dt = datetime.datetime.strptime(date_to_str, "%Y-%m-%d").date()
                payments = payments.filter(created_at__date__lte=dt)
            except ValueError:
                pass

    # Aggregates for filtered result
    total_count = payments.count()
    pos_sum = payments.filter(amount__gt=0).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    neg_sum = payments.filter(amount__lt=0).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    net_total = pos_sum + neg_sum

    # Active payment methods for dropdown
    active_methods = PaymentMethod.objects.filter(is_active=True).values_list("name", flat=True)

    paginator = Paginator(payments, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    profile = GymProfile.get_solo()

    context = {
        "page_obj": page_obj,
        "query": query,
        "operation_type": operation_type,
        "payment_method": payment_method,
        "period": period,
        "date_from": date_from_str,
        "date_to": date_to_str,
        "total_count": total_count,
        "pos_sum": pos_sum,
        "neg_sum": abs(neg_sum),
        "net_total": net_total,
        "operation_choices": PaymentOperationType.choices,
        "active_methods": list(active_methods) or ["نقدي", "انستا باي", "محفظة الكترونية", "فيزا"],
        "gym_profile": profile,
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
def download_invoice_image_view(request, payment_id):
    """Generates and serves the official high-resolution PNG receipt image for direct download."""
    payment = get_object_or_404(Payment, id=payment_id)
    from apps.payments.services import generate_invoice_image_file
    rel_path = generate_invoice_image_file(payment)

    from django.conf import settings
    from pathlib import Path
    full_path = Path(settings.MEDIA_ROOT) / rel_path

    if full_path.exists():
        clean_no = payment.invoice_no.replace("/", "_").replace("\\", "_")
        return FileResponse(open(full_path, "rb"), as_attachment=True, filename=f"invoice_{clean_no}.png")

    messages.error(request, "تعذر تحميل صورة الفاتورة.")
    return redirect("payments:payment_detail", payment_id=payment.id)


@login_required
def send_receipt_whatsapp_now_view(request, payment_id):
    """Queues and immediately attempts to dispatch the HTML/PNG invoice via WhatsApp."""
    payment = get_object_or_404(Payment, id=payment_id)
    msg_obj = queue_payment_receipt_whatsapp(payment)

    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.GET.get("format") == "json"
        or "application/json" in request.headers.get("Accept", "")
    )

    if not msg_obj:
        err_msg = "تعذر إرسال الفاتورة: لا يوجد رقم هاتف مسجل للعضو أو أن خدمة الواتساب معطلة في الإعدادات."
        if is_ajax:
            return JsonResponse({"success": False, "error": err_msg})
        messages.error(request, err_msg)
        return redirect("payments:payment_detail", payment_id=payment.id)

    from apps.messaging.models import MessageStatus
    from apps.messaging.services import dispatch_message_record, promote_due_scheduled_messages

    promote_due_scheduled_messages()
    msg_obj.refresh_from_db()

    # User explicitly clicked Send: promote from SCHEDULED to PENDING immediately
    if msg_obj.status == MessageStatus.SCHEDULED:
        msg_obj.status = MessageStatus.PENDING
        msg_obj.send_after = None
        msg_obj.save(update_fields=["status", "send_after"])

    # If requested via AJAX to prepare message ID for client overlay runner
    if is_ajax and request.GET.get("queue_only") == "1":
        return JsonResponse({
            "success": True,
            "message_id": msg_obj.id,
            "mobile": msg_obj.mobile,
            "recipient_name": payment.member.name if payment.member else "",
            "invoice_no": payment.invoice_no,
            "message": msg_obj.message,
            "has_attachment": bool(msg_obj.attachment),
        })

    dispatched = dispatch_message_record(msg_obj, return_to_system=True)

    if is_ajax:
        return JsonResponse({
            "success": True,
            "dispatched": dispatched,
            "message_id": msg_obj.id,
            "mobile": msg_obj.mobile,
            "recipient_name": payment.member.name if payment.member else "",
            "status": msg_obj.status,
            "message": msg_obj.message,
        })

    if dispatched:
        messages.success(request, f"✓ تم إرسال الفاتورة الرسمية بنجاح إلى هاتف {payment.member.name} عبر الواتساب!")
    else:
        messages.warning(request, f"تمت إضافة الفاتورة لطابور رسائل الواتساب (يرجى التأكد من تشغيل نافذة WhatsApp Desktop).")

    return redirect("payments:payment_detail", payment_id=payment.id)


def generate_next_bar_sale_id() -> str:
    """Generates unique sequential BAR-XXXXX code."""
    import re
    max_num = 0
    for sid in BarSale.objects.values_list("sale_id", flat=True):
        if sid:
            match = re.search(r"\d+", str(sid))
            if match:
                val = int(match.group())
                if val > max_num:
                    max_num = val
    next_num = max(max_num + 1, BarSale.objects.count() + 1, 1)
    while BarSale.objects.filter(sale_id=f"BAR-{next_num:05d}").exists():
        next_num += 1
    return f"BAR-{next_num:05d}"


@login_required
def bar_quick_sale_view(request):
    """
    Fast Bar / Inventory Purchase action directly from home page or bar modal.
    No heavy WhatsApp or invoice mandatory, but safely records treasury payment and decrements stock.
    Supports paid vs unpaid (deferred payment until after workout).
    """
    if request.method != "POST":
        return redirect("core:dashboard")

    product_id = request.POST.get("product_id")
    try:
        quantity = max(1, int(request.POST.get("quantity", 1) or 1))
    except (ValueError, TypeError):
        quantity = 1

    product = get_object_or_404(BarProduct, id=product_id)
    member_id = request.POST.get("member_id")
    buyer_name = request.POST.get("buyer_name", "").strip()
    buyer_phone = request.POST.get("buyer_phone", "").strip()
    payment_status = request.POST.get("payment_status", "paid")
    is_paid = (payment_status == "paid")
    payment_method = request.POST.get("payment_method", "نقدي")
    notes = request.POST.get("notes", "").strip()

    member = None
    if member_id:
        member = Member.objects.filter(id=member_id).first()

    if member and not buyer_name:
        buyer_name = member.name
    elif not buyer_name:
        buyer_name = "عميل نقدي / لاعب"

    if member and not buyer_phone and member.mobile:
        buyer_phone = member.mobile

    # Validation: If payment is deferred / unpaid, a valid phone number is mandatory!
    if not is_paid:
        clean_phone = re.sub(r"[^\d]", "", buyer_phone)
        if len(clean_phone) < 10 or len(clean_phone) > 15:
            messages.error(
                request,
                "⚠️ خطأ: يجب إدخال رقم هاتف صحيح للمشتري (11 رقم مثل: 010xxxxxxxx) عند تسجيل الطلب بالآجل (لم يدفع بعد) لضمان المتابعة والتحصيل."
            )
            next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
            return redirect(next_url)

    unit_price = product.price
    total_price = (unit_price * quantity).quantize(Decimal("0.01"))

    from apps.core.branch_context import get_active_branch
    active_branch = get_active_branch(request)
    sale_branch = (
        active_branch
        or (member.branch if member and member.branch else None)
        or (product.branch if product and product.branch else None)
        or getattr(request.user, "branch", None)
    )

    with transaction.atomic():
        # Decrement stock
        product.stock_quantity = product.stock_quantity - quantity
        product.save(update_fields=["stock_quantity", "updated_at"])

        sale_code = generate_next_bar_sale_id()

        payment = None
        if is_paid:
            pay_id, inv_no = generate_next_payment_id()
            payment = Payment.objects.create(
                payment_id=pay_id,
                invoice_no=inv_no,
                operation_type=PaymentOperationType.BAR_SALE,
                member=member,
                branch=sale_branch,
                amount=total_price,
                payment_method=payment_method,
                notes=f"مبيعات بار: {product.name} (عدد {quantity}) - المشتري: {buyer_name}{(' | ' + notes) if notes else ''}",
                created_by=request.user,
            )

        sale = BarSale.objects.create(
            sale_id=sale_code,
            product=product,
            branch=sale_branch,
            member=member,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            is_paid=is_paid,
            payment_method=payment_method,
            payment=payment,
            notes=notes if notes else ("" if is_paid else "آجل - هيدفع بعد التمرين"),
            paid_at=timezone.now() if is_paid else None,
            created_by=request.user,
        )

        phone_info = f" (هاتف: {buyer_phone})" if buyer_phone else ""
        AuditLog.log(
            action_type="BAR_SALE_PAID" if is_paid else "BAR_SALE_UNPAID",
            description=f"طلب بار ({'تم الدفع' if is_paid else 'آجل'}): {product.name} x {quantity} بمبلغ {total_price} ج للمتدرب {buyer_name}{phone_info}",
            user=request.user,
            member=member,
            amount=total_price,
        )

    if is_paid:
        messages.success(request, f"✓ تم تسجيل بيع {quantity}x {product.name} بمبلغ {total_price} ج.م وتم التحصيل بالخزينة بنجاح.")
    else:
        messages.warning(request, f"⏳ تم تسجيل طلب البار ({quantity}x {product.name} - {total_price} ج.م) بالآجل (لم يُدفع بعد) للمتدرب: {buyer_name}.")

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)


@login_required
def bar_settle_sale_view(request, sale_id):
    """
    Settles an unpaid/deferred Bar order when the player pays after finishing their workout.
    Marks sale as paid, creates Payment record in treasury, and records audit trail.
    """
    sale = get_object_or_404(BarSale, id=sale_id)

    if sale.is_paid:
        messages.info(request, "هذا الطلب مسدد بالفعل ومسجل بالخزينة.")
        return redirect(request.META.get("HTTP_REFERER") or "core:dashboard")

    payment_method = request.POST.get("payment_method", "نقدي") if request.method == "POST" else "نقدي"

    from apps.core.branch_context import get_active_branch
    settle_branch = (
        sale.branch
        or (sale.member.branch if sale.member and sale.member.branch else None)
        or get_active_branch(request)
        or getattr(request.user, "branch", None)
    )

    with transaction.atomic():
        pay_id, inv_no = generate_next_payment_id()
        payment = Payment.objects.create(
            payment_id=pay_id,
            invoice_no=inv_no,
            operation_type=PaymentOperationType.BAR_SALE,
            member=sale.member,
            branch=settle_branch,
            amount=sale.total_price,
            payment_method=payment_method,
            notes=f"سداد آجل بار: {sale.product.name} (عدد {sale.quantity}) - اللاعب: {sale.buyer_name}",
            created_by=request.user,
        )

        sale.is_paid = True
        sale.paid_at = timezone.now()
        sale.payment = payment
        sale.payment_method = payment_method
        if not sale.branch and settle_branch:
            sale.branch = settle_branch
            sale.save(update_fields=["is_paid", "paid_at", "payment", "payment_method", "branch"])
        else:
            sale.save(update_fields=["is_paid", "paid_at", "payment", "payment_method"])

        AuditLog.log(
            action_type="BAR_SALE_SETTLED",
            description=f"سداد وتحصيل آجل بار: {sale.product.name} x {sale.quantity} بمبلغ {sale.total_price} ج من {sale.buyer_name}",
            user=request.user,
            member=sale.member,
            amount=sale.total_price,
        )

    messages.success(request, f"✓ تم سداد وتحصيل حساب البار ({sale.product.name} - {sale.total_price} ج.م) من {sale.buyer_name} وإضافته للخزينة بنجاح!")
    return redirect(request.META.get("HTTP_REFERER") or "core:dashboard")


@login_required
def bar_cancel_sale_view(request, sale_id):
    """Cancels a mistaken Bar sale and restores product stock."""
    sale = get_object_or_404(BarSale, id=sale_id)

    with transaction.atomic():
        product = sale.product
        product.stock_quantity += sale.quantity
        product.save(update_fields=["stock_quantity", "updated_at"])

        if sale.payment:
            sale.payment.delete()

        AuditLog.log(
            action_type="BAR_SALE_CANCELLED",
            description=f"إلغاء طلب بار واسترجاع الكمية ({sale.quantity}) إلى المخزون: {product.name}",
            user=request.user,
            member=sale.member,
            amount=sale.total_price,
        )

        sale.delete()

    messages.info(request, "تم إلغاء عملية البار واسترجاع الكمية للمخزون بنجاح.")
    return redirect(request.META.get("HTTP_REFERER") or "core:dashboard")


@login_required
def bar_inventory_view(request):
    """Full inventory, products management, and sales log for the Bar."""
    from apps.core.branch_context import get_active_branch
    active_branch = get_active_branch(request)

    products = BarProduct.objects.all().order_by("category", "name")
    if active_branch:
        products = products.filter(Q(branch=active_branch) | Q(branch__isnull=True))

    filter_type = request.GET.get("filter", "all")

    sales_qs = BarSale.objects.select_related("product", "member", "created_by").order_by("-created_at")
    if active_branch:
        sales_qs = sales_qs.filter(
            Q(branch=active_branch)
            | Q(member__branch=active_branch)
            | Q(payment__branch=active_branch)
        )

    if filter_type == "unpaid":
        sales_qs = sales_qs.filter(is_paid=False)
    elif filter_type == "paid":
        sales_qs = sales_qs.filter(is_paid=True)

    paginator = Paginator(sales_qs, 30)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    today = timezone.localdate()
    total_products_count = products.count()
    total_stock_units = products.aggregate(Sum("stock_quantity"))["stock_quantity__sum"] or 0

    base_unpaid = BarSale.objects.filter(is_paid=False)
    base_paid = BarSale.objects.filter(is_paid=True)
    if active_branch:
        branch_filter = (
            Q(branch=active_branch)
            | Q(member__branch=active_branch)
            | Q(payment__branch=active_branch)
        )
        base_unpaid = base_unpaid.filter(branch_filter)
        base_paid = base_paid.filter(branch_filter)

    total_unpaid_debt = (
        base_unpaid.aggregate(Sum("total_price"))["total_price__sum"]
        or Decimal("0.00")
    )
    unpaid_orders_count = base_unpaid.count()
    total_bar_revenue = (
        base_paid.aggregate(Sum("total_price"))["total_price__sum"]
        or Decimal("0.00")
    )
    today_bar_revenue = (
        base_paid.filter(paid_at__date=today).aggregate(Sum("total_price"))["total_price__sum"]
        or Decimal("0.00")
    )

    # 1. Bar Expenses in Expenses Ledger
    from apps.expenses.models import Expense, ExpenseCategory
    bar_cat = ExpenseCategory.objects.filter(name__icontains="بار").first()
    if not bar_cat:
        bar_cat = ExpenseCategory.objects.create(name="مشتريات ومصاريف البار", is_active=True)

    bar_exp_qs = Expense.objects.filter(category=bar_cat)
    if active_branch:
        bar_exp_qs = bar_exp_qs.filter(branch=active_branch)
    total_bar_expenses = bar_exp_qs.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")

    # 2. Realized Actual Net Profit on Sold Products
    realized_sales_profit = Decimal("0.00")
    for s in base_paid.select_related("product"):
        if s.product:
            cost = s.product.cost_price or Decimal("0.00")
            realized_sales_profit += (s.unit_price - cost) * s.quantity

    context = {
        "products": products,
        "page_obj": page_obj,
        "filter_type": filter_type,
        "total_products_count": total_products_count,
        "total_stock_units": total_stock_units,
        "total_unpaid_debt": total_unpaid_debt,
        "unpaid_orders_count": unpaid_orders_count,
        "total_bar_revenue": total_bar_revenue,
        "today_bar_revenue": today_bar_revenue,
        "total_bar_expenses": total_bar_expenses,
        "realized_sales_profit": realized_sales_profit,
        "categories": BarProductCategory.choices,
        "payment_methods": PaymentMethod.objects.filter(is_active=True),
        "profile": GymProfile.get_solo(),
        "active_branch": active_branch,
    }
    return render(request, "payments/bar_inventory.html", context)


@login_required
def bar_product_create_view(request):
    """Add a new product to Bar inventory."""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category = request.POST.get("category", "drinks")
        price = Decimal(request.POST.get("price", "0.00") or "0.00")
        cost_price = Decimal(request.POST.get("cost_price", "0.00") or "0.00")
        stock_quantity = int(request.POST.get("stock_quantity", 0) or 0)
        min_stock_alert = int(request.POST.get("min_stock_alert", 5) or 5)

        if not name or price <= 0:
            messages.error(request, "يرجى كتابة اسم المنتج وسعر البيع بشكل صحيح.")
            return redirect("payments:bar_inventory")

        from apps.core.branch_context import get_active_branch
        active_branch = get_active_branch(request) or getattr(request.user, "branch", None)

        product = BarProduct.objects.create(
            name=name,
            category=category,
            price=price,
            cost_price=cost_price,
            stock_quantity=stock_quantity,
            min_stock_alert=min_stock_alert,
            branch=active_branch,
        )
        AuditLog.log(
            action_type="BAR_PRODUCT_CREATED",
            description=f"إضافة منتج بار جديد: {product.name} (سعر {product.price} ج | كمية {product.stock_quantity})",
            user=request.user,
        )
        messages.success(request, f"✓ تم إضافة المنتج '{product.name}' إلى مخزون البار بنجاح.")

    return redirect("payments:bar_inventory")


@login_required
def bar_product_edit_view(request, product_id):
    """Edit price, cost, name, or alert threshold of a Bar product."""
    product = get_object_or_404(BarProduct, id=product_id)

    if request.method == "POST":
        product.name = request.POST.get("name", product.name).strip()
        product.category = request.POST.get("category", product.category)
        product.price = Decimal(request.POST.get("price", product.price) or product.price)
        product.cost_price = Decimal(request.POST.get("cost_price", product.cost_price) or product.cost_price)
        product.min_stock_alert = int(request.POST.get("min_stock_alert", product.min_stock_alert) or product.min_stock_alert)
        product.save()

        messages.success(request, f"✓ تم تحديث بيانات المنتج '{product.name}' بنجاح.")

    return redirect("payments:bar_inventory")


@login_required
def bar_product_restock_view(request, product_id):
    """Quick restock addition (+10, +24, +50, or custom qty)."""
    product = get_object_or_404(BarProduct, id=product_id)

    if request.method == "POST":
        try:
            add_qty = int(request.POST.get("add_quantity", 0) or 0)
        except (ValueError, TypeError):
            add_qty = 0

        if add_qty > 0:
            product.stock_quantity += add_qty
            product.save(update_fields=["stock_quantity", "updated_at"])
            AuditLog.log(
                action_type="BAR_PRODUCT_RESTOCKED",
                description=f"تزويد مخزون المنتج: {product.name} بـ +{add_qty} قطعة (الإجمالي الجديد: {product.stock_quantity})",
                user=request.user,
            )
            messages.success(request, f"✓ تم إضافة {add_qty} قطعة إلى رصيد '{product.name}'. الرصيد الحالي: {product.stock_quantity}.")
        else:
            messages.error(request, "الكمية المضافة يجب أن تكون أكبر من الصفر.")

    return redirect(request.META.get("HTTP_REFERER") or "payments:bar_inventory")


@login_required
def bar_product_delete_view(request, product_id):
    """Delete or safely deactivate product from Bar inventory with audit logging."""
    if request.method != "POST":
        return redirect("payments:bar_inventory")

    product = get_object_or_404(BarProduct, id=product_id)
    name = product.name

    if product.sales.exists():
        product.is_active = False
        product.stock_quantity = 0
        product.save(update_fields=["is_active", "stock_quantity", "updated_at"])
        AuditLog.log(
            action_type="BAR_PRODUCT_DEACTIVATED",
            description=f"تعطيل منتج بار لوجود مبيعات سابقة له: {name}",
            user=request.user,
        )
        messages.warning(request, f"تم تعطيل المنتج '{name}' وإخفاؤه من البار لوجود فواتير مبيعات سابقة له حفاظاً على سلامة الحسابات.")
    else:
        product.delete()
        AuditLog.log(
            action_type="BAR_PRODUCT_DELETED",
            description=f"حذف منتج بار نهائياً: {name}",
            user=request.user,
        )
        messages.success(request, f"✓ تم حذف المنتج '{name}' نهائياً من مخزون البار بنجاح.")

    return redirect("payments:bar_inventory")




