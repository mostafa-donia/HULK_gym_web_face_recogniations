from datetime import date, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.decorators import manager_required
from apps.core.models import GymProfile, AuditLog, log_audit_event
from apps.members.models import Member, MemberStatus, Plan, Subscription
from apps.messaging.models import MessageType, WhatsAppMessage
from apps.payments.models import Payment, PaymentMethod, PaymentOperationType
from apps.payments.services import queue_payment_receipt_whatsapp
from apps.payroll.models import Employee, EmployeeRole, EmployeeStatus, PrivateTrainingRecord, TrainerClientAssignment


def generate_next_member_id() -> str:
    """
    Safely generates the next unique sequential MEM-XXXXX identifier.
    Finds the true maximum existing numeric ID across all members and verifies availability.
    """
    import re
    max_num = 0
    for mid in Member.objects.values_list("member_id", flat=True):
        if mid:
            match = re.search(r"\d+", str(mid))
            if match:
                val = int(match.group())
                if val > max_num:
                    max_num = val

    next_num = max(max_num + 1, Member.objects.count() + 1, 1)
    while Member.objects.filter(member_id=f"MEM-{next_num:05d}").exists():
        next_num += 1

    return f"MEM-{next_num:05d}"


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


def compute_plan_end_date(plan, start_date: date) -> date:
    """Calculates subscription end date based on gym rules:
    - 1 session ('جلسة واحدة' or duration_days == 1): ends on start_date
    - 14 days ('يوم ويوم' - day on, day off) & 28 days ('كل يوم'):
      Friday is an official gym holiday, so both 14-day and 28-day plans represent
      a 1-month subscription.
      Calculation: start_date + relativedelta(months=plan.months) - relativedelta(days=1)
      e.g. starting on 13 Oct -> ends on 12 Nov.
    """
    if plan.name == "جلسة واحدة" or getattr(plan, "duration_days", 30) == 1 or getattr(plan, "frequency", "") == "جلسة واحدة":
        return start_date

    months = getattr(plan, "months", 1) or 1
    return start_date + relativedelta(months=months) - relativedelta(days=1)


@login_required
def member_list_view(request):
    today = timezone.localdate()
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("filter", "all")
    plan_filter = request.GET.get("plan", "all")
    gender_filter = request.GET.get("gender", "all")

    # Global KPI counts for top overview badges
    total_count = Member.objects.count()
    active_count = Member.objects.filter(last_subscription_end__gte=today).count()
    expired_count = total_count - active_count
    debt_count = Member.objects.filter(current_remaining__gt=0).count()

    members = Member.objects.all()

    # Search filter
    if query:
        members = members.filter(
            Q(name__icontains=query)
            | Q(mobile__icontains=query)
            | Q(member_id__icontains=query)
            | Q(last_subscription_type__icontains=query)
        )

    # Status filter
    if status_filter == "active":
        members = members.filter(last_subscription_end__gte=today)
    elif status_filter == "expired":
        members = members.filter(Q(last_subscription_end__lt=today) | Q(last_subscription_end__isnull=True))
    elif status_filter in ["debt", "remaining"]:
        members = members.filter(current_remaining__gt=0)
    elif status_filter == "expiring_soon":
        members = members.filter(
            last_subscription_end__gte=today,
            last_subscription_end__lte=today + timedelta(days=3),
        )
    elif status_filter in ["face", "fingerprint"]:
        members = members.filter(has_face_enrolled=True)

    # Plan filter
    if plan_filter != "all" and plan_filter:
        members = members.filter(last_subscription_type=plan_filter)

    # Gender filter
    if gender_filter in ["male", "female"]:
        members = members.filter(gender=gender_filter)

    # Ordering
    if status_filter == "expired":
        members = members.order_by("last_subscription_end")
    elif status_filter in ["debt", "remaining"]:
        members = members.order_by("-current_remaining")
    else:
        members = members.order_by("-id")

    filtered_count = members.count()

    paginator = Paginator(members, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Enrich page objects with precomputed days status for crystal clear rendering
    enriched_members = []
    for m in page_obj:
        is_active = bool(m.last_subscription_end and m.last_subscription_end >= today)
        if is_active:
            days_left = (m.last_subscription_end - today).days
            days_expired = 0
            if days_left == 0:
                days_status_text = "اليوم الأخير"
                status_color = "warning"
            elif days_left == 1:
                days_status_text = "يتبقى يوم واحد"
                status_color = "warning"
            else:
                days_status_text = f"يتبقى {days_left} يوم"
                status_color = "success" if days_left > 3 else "warning"
            status_text = "مشترك حالياً"
        else:
            days_left = 0
            if m.last_subscription_end:
                days_expired = (today - m.last_subscription_end).days
                if days_expired == 0:
                    days_status_text = "انتهى اليوم"
                elif days_expired == 1:
                    days_status_text = "انتهى منذ يوم"
                else:
                    days_status_text = f"انتهى منذ {days_expired} يوم"
            else:
                days_expired = 0
                days_status_text = "بدون اشتراك"
            status_color = "expired"
            status_text = "غير مشترك"

        enriched_members.append({
            "member": m,
            "is_active": is_active,
            "days_left": days_left,
            "days_expired": days_expired,
            "days_status_text": days_status_text,
            "status_color": status_color,
            "status_text": status_text,
            "has_debt": m.current_remaining > Decimal("0.00"),
        })

    plans_list = Plan.objects.filter(is_active=True).order_by("name")

    context = {
        "page_obj": page_obj,
        "enriched_members": enriched_members,
        "query": query,
        "status_filter": status_filter,
        "plan_filter": plan_filter,
        "gender_filter": gender_filter,
        "total_count": total_count,
        "active_count": active_count,
        "expired_count": expired_count,
        "debt_count": debt_count,
        "filtered_count": filtered_count,
        "plans_list": plans_list,
        "today": today,
    }
    return render(request, "members/member_list.html", context)


@login_required
def member_detail_view(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    today = timezone.localdate()
    is_active = bool(member.last_subscription_end and member.last_subscription_end >= today)
    days_left = max(0, (member.last_subscription_end - today).days) if is_active else 0
    days_expired = (today - member.last_subscription_end).days if (member.last_subscription_end and not is_active) else 0

    subscriptions = member.subscriptions.all().order_by("-start_date")
    payments = member.payments.all().order_by("-created_at")
    checkins = member.check_ins.all().order_by("-checked_in_at")[:15]
    coaches = Employee.objects.filter(role=EmployeeRole.TRAINER, status=EmployeeStatus.ACTIVE).order_by("name")

    context = {
        "member": member,
        "is_active": is_active,
        "days_left": days_left,
        "days_expired": days_expired,
        "subscriptions": subscriptions,
        "payments": payments,
        "checkins": checkins,
        "coaches": coaches,
        "today": today,
    }
    return render(request, "members/member_detail.html", context)


@login_required
def member_create_view(request):
    coaches = Employee.objects.filter(role=EmployeeRole.TRAINER, status=EmployeeStatus.ACTIVE).order_by("name")
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        mobile = request.POST.get("mobile", "").strip()
        gender = request.POST.get("gender", "male")
        notes = request.POST.get("notes", "").strip()

        has_private = request.POST.get("has_private") in ["1", "on", "true"]
        private_price = Decimal(request.POST.get("private_price", "600.00") or "600.00") if has_private else Decimal("600.00")
        coach_id = request.POST.get("assigned_coach_id")
        assigned_coach = None
        if coach_id:
            assigned_coach = Employee.objects.filter(id=coach_id, role=EmployeeRole.TRAINER).first()

        if has_private and not assigned_coach:
            messages.error(request, "يرجى اختيار الكابتن المسؤول عن التدريب الخاص (Private).")
            return render(request, "members/member_form.html", {"initial_name": name, "coaches": coaches})

        renewal_discount = Decimal(request.POST.get("renewal_discount", "0.00") or "0.00")
        discount_enabled = request.POST.get("discount_enabled") in ["1", "on", "true"]

        if not name:
            messages.error(request, "اسم العضو مطلوب.")
            return render(request, "members/member_form.html", {"coaches": coaches})

        mid = generate_next_member_id()
        member = Member.objects.create(
            member_id=mid,
            name=name,
            mobile=mobile,
            gender=gender,
            notes=notes,
            has_private=has_private,
            private_price=private_price,
            assigned_coach=assigned_coach,
            renewal_discount=renewal_discount,
            discount_enabled=discount_enabled,
            current_status=MemberStatus.EXPIRED,
        )

        if has_private:
            log_audit_event(
                user=request.user,
                action="private_status_changed",
                target_model="Member",
                target_id=str(member.id),
                details=f"تفعيل التدريب الخاص (Private) للعضو الجديد {member.name} مع كابتن {assigned_coach.name if assigned_coach else 'غير محدد'} بسعر {private_price} ج",
                amount=private_price,
            )
        if discount_enabled and renewal_discount > Decimal("0.00"):
            log_audit_event(
                user=request.user,
                action="discount_preset_changed",
                target_model="Member",
                target_id=str(member.id),
                details=f"تحديد خصم تجديد معتمد للعضو الجديد {member.name} بقيمة {renewal_discount} ج",
                amount=renewal_discount,
            )

        # Attempt seamless Google Contacts sync in background thread so request never hangs
        if mobile:
            try:
                import threading
                from apps.core.google_contacts import sync_single_member_to_google
                threading.Thread(target=sync_single_member_to_google, args=(member,), daemon=True).start()
            except Exception:
                pass

        messages.success(request, f"تمت إضافة العضو {member.name} ({member.member_id}) بنجاح!")
        
        # Check if user wants to subscribe immediately
        if "add_subscription" in request.POST:
            return redirect(f"/members/subscription/create/?member_id={member.id}")

        return redirect(f"/members/{member.id}/")

    initial_name = request.GET.get("name", "")
    return render(request, "members/member_form.html", {"initial_name": initial_name, "coaches": coaches})


@login_required
def member_edit_view(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    plans = Plan.objects.filter(is_active=True).order_by("price")
    coaches = Employee.objects.filter(role=EmployeeRole.TRAINER, status=EmployeeStatus.ACTIVE).order_by("name")

    if request.method == "POST":
        old_mobile = (member.mobile or "").strip()
        member.name = request.POST.get("name", member.name).strip()
        member.mobile = request.POST.get("mobile", member.mobile).strip()
        member.gender = request.POST.get("gender", member.gender)
        member.notes = request.POST.get("notes", member.notes).strip()

        mobile_changed = bool(member.mobile and member.mobile != old_mobile)
        if mobile_changed:
            member.google_contact_synced_at = None

        # Track sensitive changes for audit
        old_has_private = member.has_private
        old_private_price = member.private_price
        old_coach = member.assigned_coach
        old_discount_enabled = member.discount_enabled
        old_renewal_discount = member.renewal_discount

        new_has_private = request.POST.get("has_private") in ["1", "on", "true"]
        new_private_price = Decimal(request.POST.get("private_price", str(member.private_price or "600.00")) or "600.00")
        coach_id = request.POST.get("assigned_coach_id")
        new_coach = Employee.objects.filter(id=coach_id, role=EmployeeRole.TRAINER).first() if coach_id else None

        if new_has_private and not new_coach:
            messages.error(request, "يرجى اختيار الكابتن المسؤول عن التدريب الخاص (Private).")
            return render(request, "members/member_form.html", {"member": member, "is_edit": True, "coaches": coaches, "plans": plans})

        new_discount_enabled = request.POST.get("discount_enabled") in ["1", "on", "true"]
        new_renewal_discount = Decimal(request.POST.get("renewal_discount", str(member.renewal_discount or "0.00")) or "0.00")

        member.has_private = new_has_private
        member.private_price = new_private_price
        member.assigned_coach = new_coach
        member.discount_enabled = new_discount_enabled
        member.renewal_discount = new_renewal_discount

        # Log audit if private settings changed
        if old_has_private != new_has_private or old_private_price != new_private_price or old_coach != new_coach:
            status_desc = "تفعيل" if new_has_private else "إلغاء تفعيل"
            coach_str = new_coach.name if new_coach else "بدون كابتن"
            log_audit_event(
                user=request.user,
                action="private_status_changed",
                target_model="Member",
                target_id=str(member.id),
                details=f"تم {status_desc} التدريب الخاص للاعب {member.name}. السعر: {new_private_price} ج، الكابتن: {coach_str}",
                amount=new_private_price if new_has_private else Decimal("0.00"),
            )

        # Log audit if renewal discount changed
        if old_discount_enabled != new_discount_enabled or old_renewal_discount != new_renewal_discount:
            status_desc = "تفعيل" if new_discount_enabled else "إلغاء"
            log_audit_event(
                user=request.user,
                action="discount_preset_changed",
                target_model="Member",
                target_id=str(member.id),
                details=f"تم {status_desc} خصم التجديد للاعب {member.name}. القيمة: {new_renewal_discount} ج (سابقاً: {old_renewal_discount} ج)",
                amount=new_renewal_discount,
            )

        # Support editing and correcting the member's plan if misswritten
        edit_plan = request.POST.get("edit_plan") == "1" or "last_subscription_type" in request.POST
        if edit_plan:
            plan_name = request.POST.get("last_subscription_type", "").strip()
            custom_plan = request.POST.get("custom_plan_name", "").strip()
            if custom_plan:
                plan_name = custom_plan

            if plan_name:
                member.last_subscription_type = plan_name

            sub_start_str = request.POST.get("last_subscription_start", "").strip()
            if sub_start_str:
                try:
                    member.last_subscription_start = date.fromisoformat(sub_start_str)
                except Exception:
                    pass

            sub_end_str = request.POST.get("last_subscription_end", "").strip()
            if sub_end_str:
                try:
                    member.last_subscription_end = date.fromisoformat(sub_end_str)
                except Exception:
                    pass

            paid_str = request.POST.get("current_paid", "").strip()
            if paid_str:
                try:
                    member.current_paid = Decimal(paid_str)
                except Exception:
                    pass

            rem_str = request.POST.get("current_remaining", "").strip()
            if rem_str:
                try:
                    member.current_remaining = Decimal(rem_str)
                except Exception:
                    pass

            # Synchronize with the latest subscription record if one exists
            latest_sub = member.subscriptions.order_by("-created_at").first()
            if latest_sub:
                if plan_name:
                    latest_sub.plan_name = plan_name
                if member.last_subscription_start:
                    latest_sub.start_date = member.last_subscription_start
                if member.last_subscription_end:
                    latest_sub.end_date = member.last_subscription_end
                if paid_str:
                    latest_sub.paid_amount = member.current_paid
                if rem_str:
                    latest_sub.remaining_amount = member.current_remaining
                latest_sub.save()

        member.refresh_status()
        member.save()
        if mobile_changed or (member.mobile and not member.google_contact_synced_at):
            try:
                from apps.core.google_contacts import trigger_async_member_google_sync
                trigger_async_member_google_sync(member)
            except Exception:
                pass
        messages.success(request, f"تم تحديث بيانات العضو {member.name} وتصحيح الاشتراك بنجاح.")
        return redirect("members:member_detail", member_id=member.id)

    context = {
        "member": member,
        "is_edit": True,
        "plans": plans,
        "coaches": coaches,
    }
    return render(request, "members/member_form.html", context)


@login_required
def member_quick_private_update_view(request, member_id):
    """Quick modal/card update from Member Detail page for Private Add-on and/or Renewal Discount independently."""
    member = get_object_or_404(Member, id=member_id)
    if request.method == "POST":
        update_target = request.POST.get("update_target", "all")

        # 1. Update Private Training if targeted or present
        if update_target in ["all", "private"]:
            old_has_private = member.has_private
            old_private_price = member.private_price
            old_coach = member.assigned_coach

            new_has_private = request.POST.get("has_private") in ["1", "on", "true"]
            new_private_price = Decimal(request.POST.get("private_price", str(member.private_price or "600.00")) or "600.00")
            coach_id = request.POST.get("assigned_coach_id")
            new_coach = Employee.objects.filter(id=coach_id, role=EmployeeRole.TRAINER).first() if coach_id else None

            if new_has_private and not new_coach:
                messages.error(request, "يرجى اختيار الكابتن المسؤول عن التدريب الخاص (Private).")
                return redirect(f"/members/{member.id}/")

            member.has_private = new_has_private
            member.private_price = new_private_price if new_has_private else Decimal("0.00")
            member.assigned_coach = new_coach if new_has_private else None

            if old_has_private != new_has_private or old_private_price != new_private_price or old_coach != new_coach:
                status_desc = "تفعيل" if new_has_private else "إلغاء تفعيل"
                coach_str = new_coach.name if new_coach else "بدون كابتن"
                log_audit_event(
                    user=request.user,
                    action="private_status_changed",
                    target_model="Member",
                    target_id=str(member.id),
                    details=f"تم {status_desc} التدريب الخاص للاعب {member.name}. السعر: {new_private_price} ج، الكابتن: {coach_str}",
                    amount=new_private_price if new_has_private else Decimal("0.00"),
                )

        # 2. Update Renewal Discount if targeted or present (Standalone for any plan: normal or private)
        if update_target in ["all", "discount"]:
            old_discount_enabled = member.discount_enabled
            old_renewal_discount = member.renewal_discount

            new_discount_enabled = request.POST.get("discount_enabled") in ["1", "on", "true"]
            new_renewal_discount = Decimal(request.POST.get("renewal_discount", str(member.renewal_discount or "0.00")) or "0.00")

            member.discount_enabled = new_discount_enabled
            member.renewal_discount = new_renewal_discount if new_discount_enabled else Decimal("0.00")

            if old_discount_enabled != new_discount_enabled or old_renewal_discount != new_renewal_discount:
                status_desc = "تفعيل" if new_discount_enabled else "إلغاء"
                log_audit_event(
                    user=request.user,
                    action="discount_preset_changed",
                    target_model="Member",
                    target_id=str(member.id),
                    details=f"تم {status_desc} خصم التجديد للاعب {member.name} (للباقات العادية أو البرايفت). القيمة: {new_renewal_discount} ج (سابقاً: {old_renewal_discount} ج)",
                    amount=new_renewal_discount,
                )

        member.save()

        if update_target == "private":
            messages.success(request, f"تم تحديث باقة التدريب الخاص (Private) للاعب {member.name} بنجاح.")
        elif update_target == "discount":
            messages.success(request, f"تم تحديث سياسة خصم التجديد للاعب {member.name} بنجاح.")
        else:
            messages.success(request, f"تم تحديث بيانات التدريب الخاص وسياسة الخصم للاعب {member.name} بنجاح.")

    return redirect("members:member_detail", member_id=member.id)


@login_required
def subscription_edit_view(request, subscription_id):
    """Allows correcting any misswritten plan name, dates, or amounts for a subscription record."""
    subscription = get_object_or_404(Subscription, id=subscription_id)
    member = subscription.member
    plans = Plan.objects.filter(is_active=True).order_by("price")
    payment_methods = PaymentMethod.objects.filter(is_active=True)

    if request.method == "POST":
        plan_name = request.POST.get("plan_name", subscription.plan_name).strip()
        custom_plan = request.POST.get("custom_plan", "").strip()
        if custom_plan:
            plan_name = custom_plan

        start_date_str = request.POST.get("start_date", "").strip()
        end_date_str = request.POST.get("end_date", "").strip()
        price_str = request.POST.get("plan_price", "").strip()
        paid_str = request.POST.get("paid_amount", "").strip()
        rem_str = request.POST.get("remaining_amount", "").strip()
        allowance_days = int(request.POST.get("allowance_days", "0") or "0")
        payment_method = request.POST.get("payment_method", subscription.payment_method)

        subscription.plan_name = plan_name
        if start_date_str:
            subscription.start_date = date.fromisoformat(start_date_str)
        if end_date_str:
            subscription.end_date = date.fromisoformat(end_date_str)
        if price_str:
            subscription.plan_price = Decimal(price_str)
            subscription.net_amount = Decimal(price_str)
        if paid_str:
            subscription.paid_amount = Decimal(paid_str)
        if rem_str:
            rem_val = Decimal(rem_str)
            if rem_val > Decimal("0.00"):
                if allowance_days < 1 or allowance_days > 10:
                    messages.error(request, "عند وجود متبقي (دفع جزئي)، يجب أن تكون مهلة السداد (أيام السماح) بين 1 و 10 أيام كحد أقصى.")
                    return redirect("members:subscription_edit", subscription_id=subscription.id)
            else:
                allowance_days = 0
            subscription.remaining_amount = rem_val
        else:
            allowance_days = 0

        subscription.allowance_days = allowance_days
        subscription.payment_method = payment_method
        subscription.save()

        # If this is the latest subscription for this member, synchronize the Member profile snapshot
        latest_sub = member.subscriptions.order_by("-created_at").first()
        if latest_sub and latest_sub.id == subscription.id:
            member.last_subscription_type = subscription.plan_name
            member.last_subscription_start = subscription.start_date
            member.last_subscription_end = subscription.end_date
            member.current_paid = subscription.paid_amount
            member.current_remaining = subscription.remaining_amount
            if allowance_days > 0 and subscription.remaining_amount > Decimal("0.00"):
                member.follow_up_date = subscription.start_date + timedelta(days=allowance_days)
            else:
                member.follow_up_date = None
            member.refresh_status()
            member.save()

        messages.success(request, f"تم تصحيح وتحديث بيانات الاشتراك ({subscription.plan_name}) بنجاح.")
        return redirect("members:member_detail", member_id=member.id)

    context = {
        "subscription": subscription,
        "member": member,
        "plans": plans,
        "payment_methods": payment_methods,
    }
    return render(request, "members/subscription_edit.html", context)


@login_required
def subscription_create_view(request):
    """Handles both new subscriptions and renewals with exact business logic chaining."""
    today = timezone.localdate()
    plans = Plan.objects.filter(is_active=True).order_by("price")
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    coaches = Employee.objects.filter(role=EmployeeRole.TRAINER, status=EmployeeStatus.ACTIVE).order_by("name")

    member_id_param = request.GET.get("member_id")
    selected_member = Member.objects.filter(id=member_id_param).first() if member_id_param else None

    # Calculate default suggested start date
    suggested_start = today
    if selected_member and selected_member.last_subscription_end and selected_member.last_subscription_end >= today:
        suggested_start = selected_member.last_subscription_end + timedelta(days=1)

    suggested_discount = Decimal("0.00")
    if selected_member and selected_member.subscriptions.exists() and selected_member.discount_enabled:
        suggested_discount = selected_member.renewal_discount

    if request.method == "POST":
        member_id = request.POST.get("member_id")
        member = get_object_or_404(Member, id=member_id)

        plan_id = request.POST.get("plan_id")
        plan = get_object_or_404(Plan, id=plan_id)

        start_date_str = request.POST.get("start_date")
        try:
            start_date = date.fromisoformat(start_date_str)
        except Exception:
            start_date = today

        # 1. Base Plan + Private Add-on Calculation
        plan_price = plan.price

        has_private = request.POST.get("has_private") in ["1", "on", "true"]
        private_price = Decimal(request.POST.get("private_price", "0.00") or "0.00") if has_private else Decimal("0.00")
        
        coach_id = request.POST.get("coach_id")
        coach = None
        if has_private:
            if coach_id:
                coach = Employee.objects.filter(id=coach_id, role=EmployeeRole.TRAINER).first()
            if not coach and member.assigned_coach:
                coach = member.assigned_coach
            if not coach:
                messages.error(request, "يرجى اختيار الكابتن المسؤول عن التدريب الخاص (Private).")
                return redirect(f"{reverse('members:subscription_create')}?member_id={member.id}")

        total_sub_price = plan_price + private_price

        # 2. Discount Handling
        discount = Decimal(request.POST.get("discount", "0.00") or "0.00")
        net_amount = max(Decimal("0.00"), total_sub_price - discount)
        paid_amount = Decimal(request.POST.get("paid_amount", str(net_amount)) or str(net_amount))
        remaining_amount = max(Decimal("0.00"), net_amount - paid_amount)
        allowance_days = int(request.POST.get("allowance_days", "0") or "0")
        payment_method = request.POST.get("payment_method", "نقدي")
        notes = request.POST.get("notes", "").strip()

        # Coach Commission (Monthly Add-on Share from private_price only)
        coach_comm_rate = Decimal("0.5000")
        coach_comm_amount = Decimal("0.00")
        if has_private and coach:
            raw_comm_pct = request.POST.get("coach_commission_pct", "").strip()
            try:
                comm_pct = Decimal(raw_comm_pct) if raw_comm_pct != "" else (coach.commission_percentage or Decimal("50.00"))
            except Exception:
                comm_pct = coach.commission_percentage or Decimal("50.00")
            comm_pct = max(Decimal("0.00"), min(Decimal("100.00"), comm_pct))
            coach_comm_rate = (comm_pct / Decimal("100.00")).quantize(Decimal("0.0001"))
            coach_comm_amount = (private_price * coach_comm_rate).quantize(Decimal("0.01"))

        if remaining_amount > Decimal("0.00"):
            if allowance_days < 1 or allowance_days > 10:
                messages.error(
                    request,
                    "عند الدفع الجزئي ووجود متبقي، يجب تحديد مهلة سداد (أيام السماح) بحيث لا تزيد عن 10 أيام (من 1 إلى 10 أيام)."
                )
                return redirect(f"{reverse('members:subscription_create')}?member_id={member.id}")
        else:
            allowance_days = 0

        end_date = compute_plan_end_date(plan, start_date)

        with transaction.atomic():
            # 1. Create Subscription Contract
            op_type = "renewal" if member.subscriptions.exists() else "new_subscription"
            sub = Subscription.objects.create(
                member=member,
                plan=plan,
                plan_name=plan.name,
                start_date=start_date,
                end_date=end_date,
                plan_price=plan_price,
                has_private=has_private,
                private_price=private_price,
                coach=coach,
                coach_commission_rate=coach_comm_rate,
                coach_commission_amount=coach_comm_amount,
                discount=discount,
                net_amount=net_amount,
                paid_amount=paid_amount,
                remaining_amount=remaining_amount,
                allowance_days=allowance_days,
                operation_type=op_type,
                payment_method=payment_method,
                created_by=request.user,
            )

            # 2. Create Payment Record if money was paid
            payment = None
            if paid_amount > 0:
                pay_id, inv_no = generate_next_payment_id()
                payment = Payment.objects.create(
                    payment_id=pay_id,
                    invoice_no=inv_no,
                    operation_type=op_type,
                    member=member,
                    subscription=sub,
                    amount=paid_amount,
                    payment_method=payment_method,
                    notes=notes,
                    created_by=request.user,
                )

            # 3. Create PrivateTrainingRecord for the Coach (Monthly Subscription Add-on: standard_plan_price = plan_price)
            if has_private and coach:
                PrivateTrainingRecord.objects.create(
                    payment=payment,
                    trainer=coach,
                    client=member,
                    package_price=net_amount,
                    standard_plan_price=plan_price,
                    private_markup=private_price,
                    commission_rate=coach_comm_rate,
                    calculated_commission=coach_comm_amount,
                )
                TrainerClientAssignment.objects.update_or_create(
                    trainer=coach,
                    client=member,
                    defaults={"commission_rate": coach_comm_rate, "is_active": True},
                )

            # 4. Update Member State
            member.last_subscription_start = start_date
            member.last_subscription_end = end_date
            member.last_subscription_type = plan.name
            member.current_paid = paid_amount
            member.current_remaining = remaining_amount
            member.total_paid += paid_amount

            # Update Private status on Member Profile
            member.has_private = has_private
            if has_private:
                member.private_price = private_price
                if coach:
                    member.assigned_coach = coach
            else:
                member.private_price = Decimal("0.00")

            # Save agreed renewal discount if requested or if renewal
            save_discount_for_renewal = request.POST.get("save_discount_for_renewal") in ["1", "on", "true"]
            if save_discount_for_renewal:
                member.renewal_discount = discount
                member.discount_enabled = (discount > 0)

            if allowance_days > 0 and remaining_amount > Decimal("0.00"):
                member.follow_up_date = start_date + timedelta(days=allowance_days)
            else:
                member.follow_up_date = None
            if payment:
                member.last_payment_date = payment.created_at
            member.refresh_status(save=False)
            member.save()

            # 5. Audit Logging for Manager Transparency
            if discount > Decimal("0.00"):
                log_audit_event(
                    user=request.user,
                    action="discount_applied",
                    target_model="Subscription",
                    target_id=str(sub.id),
                    details=f"منح خصم بقيمة {discount} ج.م على اشتراك ({plan.name}) للاعب {member.name} ({sub.get_operation_type_display()})",
                    amount=discount,
                )
            if has_private:
                log_audit_event(
                    user=request.user,
                    action="private_subscribed",
                    target_model="Subscription",
                    target_id=str(sub.id),
                    details=f"تفعيل تدريب خاص (Private) للاعب {member.name} بقيمة {private_price} ج.م مع كابتن {coach.name if coach else 'غير محدد'}",
                    amount=private_price,
                )

            # 6. Queue WhatsApp Receipt
            if member.mobile:
                if payment:
                    queue_payment_receipt_whatsapp(payment, subscription=sub)

        messages.success(request, f"تم تفعيل اشتراك {member.name} بنجاح حتى {end_date}!")
        if not member.has_face_enrolled:
            pay_param = f"&payment_id={payment.id}" if payment else ""
            return redirect(f"/members/{member.id}/?enroll=1{pay_param}")
        if payment:
            return redirect(f"/payments/{payment.id}/?auto=1")
        return redirect("members:member_detail", member_id=member.id)

    members_all = Member.objects.all().order_by("name")[:100]

    context = {
        "plans": plans,
        "payment_methods": payment_methods,
        "selected_member": selected_member,
        "suggested_start": suggested_start,
        "suggested_discount": suggested_discount,
        "members": members_all,
        "coaches": coaches,
    }
    return render(request, "members/subscription_form.html", context)


@login_required
def smart_operations_view(request):
    """
    Dedicated Smart Operations workspace (إدارة العمليات - سجل / جدد / دفع المتبقي).
    Matches the exact layout and behavior of the legacy reference application:
    - Real-time search by name or mobile.
    - If member does not exist -> Automatically switches to 'اشتراك جديد' (New Subscription).
    - If member exists with debt -> Automatically switches to 'دفع المتبقي' (Settle Debt) with option to renew.
    - If member exists without debt -> Automatically switches to 'تجديد اشتراك' (Renewal).
    - Allows choosing custom/old start dates.
    - Allows setting 'أيام السماح' (allowance_days) to determine grace period when payment is partial.
    """
    today = timezone.localdate()
    plans = Plan.objects.filter(is_active=True).order_by("price")
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    profile = GymProfile.get_solo()

    # Fast Ajax autocomplete
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" and request.GET.get("action") == "search":
        from django.http import JsonResponse
        term = request.GET.get("term", "").strip()
        candidates = Member.objects.filter(
            Q(name__icontains=term) | Q(mobile__icontains=term) | Q(member_id__icontains=term)
        )[:15]
        data = []
        for m in candidates:
            data.append({
                "id": m.id,
                "name": m.name,
                "mobile": m.mobile,
                "member_id": m.member_id,
                "gender": m.gender,
                "remaining": float(m.current_remaining),
                "is_active": m.is_active,
                "has_face_enrolled": m.has_face_enrolled,
                "last_end": m.last_subscription_end.strftime("%Y-%m-%d") if m.last_subscription_end else "",
                "last_plan": m.last_subscription_type or "",
                "has_private": m.has_private,
                "private_price": float(m.private_price),
                "coach_id": m.assigned_coach_id,
                "coach_name": m.assigned_coach.name if m.assigned_coach else "",
                "coach_commission_pct": float(m.assigned_coach.commission_percentage) if m.assigned_coach else 50.0,
                "discount_enabled": m.discount_enabled,
                "renewal_discount": float(m.renewal_discount),
            })
        return JsonResponse({"results": data})

    if request.method == "POST":
        op_type = request.POST.get("operation_type", "new_subscription")
        member_id = request.POST.get("member_id", "").strip()

        with transaction.atomic():
            # ======================== CASE 1 & 2: NEW OR RENEWAL SUBSCRIPTION ========================
            if op_type in ["new_subscription", "renewal"]:
                name = request.POST.get("name", "").strip()
                mobile = request.POST.get("mobile", "").strip()
                gender = request.POST.get("gender", "male")
                plan_id = request.POST.get("plan_id")
                plan = get_object_or_404(Plan, id=plan_id)

                # Pre-lookup existing member if provided
                member = None
                if member_id:
                    member = Member.objects.filter(id=member_id).first()
                if not member and mobile:
                    member = Member.objects.filter(mobile=mobile).first()

                start_date_str = request.POST.get("start_date")
                try:
                    start_date = date.fromisoformat(start_date_str)
                except Exception:
                    start_date = today

                plan_price = plan.price
                has_private = request.POST.get("has_private") in ["1", "on", "true"]
                private_price = Decimal(request.POST.get("private_price", "0.00") or "0.00") if has_private else Decimal("0.00")
                coach_id = request.POST.get("coach_id")
                coach = None
                if has_private:
                    if coach_id:
                        coach = Employee.objects.filter(id=coach_id, role=EmployeeRole.TRAINER).first()
                    if not coach and member and member.assigned_coach:
                        coach = member.assigned_coach
                    if not coach:
                        messages.error(request, "يرجى اختيار الكابتن المسؤول عن التدريب الخاص (Private).")
                        return redirect("members:smart_operations")

                discount = Decimal(request.POST.get("discount", "0.00") or "0.00")
                total_sub_price = plan_price + private_price
                net_amount = max(Decimal("0.00"), total_sub_price - discount)
                paid_amount = Decimal(request.POST.get("paid_amount", str(net_amount)) or str(net_amount))
                remaining_amount = max(Decimal("0.00"), net_amount - paid_amount)
                allowance_days = int(request.POST.get("allowance_days", 0) or 0)
                payment_method = request.POST.get("payment_method", "نقدي")
                notes = request.POST.get("notes", "").strip()

                # Coach Commission (Monthly Add-on Share from private_price only)
                coach_comm_rate = Decimal("0.5000")
                coach_comm_amount = Decimal("0.00")
                if has_private and coach:
                    raw_comm_pct = request.POST.get("coach_commission_pct", "").strip()
                    try:
                        comm_pct = Decimal(raw_comm_pct) if raw_comm_pct != "" else (coach.commission_percentage or Decimal("50.00"))
                    except Exception:
                        comm_pct = coach.commission_percentage or Decimal("50.00")
                    comm_pct = max(Decimal("0.00"), min(Decimal("100.00"), comm_pct))
                    coach_comm_rate = (comm_pct / Decimal("100.00")).quantize(Decimal("0.0001"))
                    coach_comm_amount = (private_price * coach_comm_rate).quantize(Decimal("0.01"))

                # Validation: Partial payment requires allowance_days between 1 and 10 days
                if remaining_amount > Decimal("0.00"):
                    if allowance_days < 1 or allowance_days > 10:
                        messages.error(
                            request,
                            "عند الدفع الجزئي ووجود متبقي، يجب تحديد مهلة سداد (أيام السماح) بحيث لا تزيد عن 10 أيام (من 1 إلى 10 أيام)."
                        )
                        redirect_query = mobile or name or ""
                        return redirect(f"{reverse('members:smart_operations')}?query={redirect_query}")
                else:
                    allowance_days = 0

                end_date = compute_plan_end_date(plan, start_date)

                if not member:
                    # New Member
                    member = Member.objects.create(
                        member_id=generate_next_member_id(),
                        name=name or "عضو جديد",
                        mobile=mobile,
                        gender=gender,
                        last_subscription_start=start_date,
                        last_subscription_end=end_date,
                        last_subscription_type=plan.name,
                        current_paid=paid_amount,
                        current_remaining=remaining_amount,
                        total_paid=paid_amount,
                        follow_up_date=start_date + timedelta(days=allowance_days) if (allowance_days > 0 and remaining_amount > Decimal("0.00")) else None,
                        notes=notes,
                        has_private=has_private,
                        private_price=private_price,
                        assigned_coach=coach if has_private else None,
                    )
                    actual_op_type = "new_subscription"
                    if mobile:
                        try:
                            from apps.core.google_contacts import trigger_async_member_google_sync
                            trigger_async_member_google_sync(member)
                        except Exception:
                            pass
                else:
                    # Renewal
                    old_mobile = (member.mobile or "").strip()
                    if name:
                        member.name = name
                    if mobile and mobile != old_mobile:
                        member.mobile = mobile
                        member.google_contact_synced_at = None
                    if gender:
                        member.gender = gender
                    member.last_subscription_start = start_date
                    member.last_subscription_end = end_date
                    member.last_subscription_type = plan.name
                    member.current_paid = paid_amount
                    member.current_remaining += remaining_amount
                    member.total_paid += paid_amount
                    member.has_private = has_private
                    if has_private:
                        member.private_price = private_price
                        if coach:
                            member.assigned_coach = coach
                    else:
                        member.private_price = Decimal("0.00")

                    if allowance_days > 0 and remaining_amount > Decimal("0.00"):
                        member.follow_up_date = start_date + timedelta(days=allowance_days)
                    elif member.current_remaining <= Decimal("0.00"):
                        member.follow_up_date = None
                    member.save()
                    if member.mobile and (member.mobile != old_mobile or not member.google_contact_synced_at):
                        try:
                            from apps.core.google_contacts import trigger_async_member_google_sync
                            trigger_async_member_google_sync(member)
                        except Exception:
                            pass
                    actual_op_type = "renewal"

                member.refresh_status()

                # Create Subscription
                sub = Subscription.objects.create(
                    member=member,
                    plan=plan,
                    plan_name=plan.name,
                    start_date=start_date,
                    end_date=end_date,
                    plan_price=plan_price,
                    has_private=has_private,
                    private_price=private_price,
                    coach=coach,
                    coach_commission_rate=coach_comm_rate,
                    coach_commission_amount=coach_comm_amount,
                    discount=discount,
                    net_amount=net_amount,
                    paid_amount=paid_amount,
                    remaining_amount=remaining_amount,
                    allowance_days=allowance_days,
                    operation_type=actual_op_type,
                    payment_method=payment_method,
                    created_by=request.user,
                )

                # Create Payment if paid
                payment = None
                if paid_amount > Decimal("0.00"):
                    pay_id, inv_no = generate_next_payment_id()
                    payment = Payment.objects.create(
                        payment_id=pay_id,
                        invoice_no=inv_no,
                        operation_type=PaymentOperationType.NEW_SUBSCRIPTION if actual_op_type == "new_subscription" else PaymentOperationType.RENEWAL,
                        member=member,
                        subscription=sub,
                        amount=paid_amount,
                        payment_method=payment_method,
                        notes=notes,
                        created_by=request.user,
                    )

                # Create PrivateTrainingRecord for the Coach
                if has_private and coach:
                    PrivateTrainingRecord.objects.create(
                        payment=payment,
                        trainer=coach,
                        client=member,
                        package_price=net_amount,
                        standard_plan_price=plan_price,
                        private_markup=private_price,
                        commission_rate=coach_comm_rate,
                        calculated_commission=coach_comm_amount,
                    )
                    TrainerClientAssignment.objects.update_or_create(
                        trainer=coach,
                        client=member,
                        defaults={"commission_rate": coach_comm_rate, "is_active": True},
                    )

                # Audit Logging for Manager Transparency
                if discount > Decimal("0.00"):
                    log_audit_event(
                        user=request.user,
                        action="discount_applied",
                        target_model="Subscription",
                        target_id=str(sub.id),
                        details=f"منح خصم بقيمة {discount} ج.م على اشتراك ({plan.name}) للاعب {member.name} عبر العمليات الذكية",
                        amount=discount,
                    )
                if has_private:
                    log_audit_event(
                        user=request.user,
                        action="private_subscribed",
                        target_model="Subscription",
                        target_id=str(sub.id),
                        details=f"تفعيل تدريب خاص (Private) للاعب {member.name} بإضافة {private_price} ج.م مع كابتن {coach.name if coach else 'غير محدد'}",
                        amount=private_price,
                    )

                # Send WhatsApp Receipt with HTML Invoice
                if payment:
                    queue_payment_receipt_whatsapp(payment, subscription=sub)

                messages.success(request, f"تم حفظ {'الاشتراك الجديد' if actual_op_type == 'new_subscription' else 'التجديد'} بنجاح للعضو {member.name} حتى {end_date}!")
                if not member.has_face_enrolled:
                    pay_param = f"&payment_id={payment.id}" if payment else ""
                    return redirect(f"/members/{member.id}/?enroll=1{pay_param}")
                if payment:
                    return redirect(f"/payments/{payment.id}/?auto=1")
                return redirect("members:smart_operations")

            # ======================== CASE 3: SETTLE REMAINING DEBT ========================
            elif op_type == "remaining":
                member = get_object_or_404(Member, id=member_id)
                paid_now = Decimal(request.POST.get("paid_amount", "0.00") or "0.00")
                payment_method = request.POST.get("payment_method", "نقدي")
                notes = request.POST.get("notes", "").strip()

                if paid_now > Decimal("0.00"):
                    prev_remaining = member.current_remaining
                    new_remaining = max(Decimal("0.00"), prev_remaining - paid_now)
                    member.current_remaining = new_remaining
                    member.total_paid += paid_now
                    if new_remaining == Decimal("0.00"):
                        member.follow_up_date = None
                    member.save()

                    pay_id, inv_no = generate_next_payment_id()
                    created_pay = Payment.objects.create(
                        payment_id=pay_id,
                        invoice_no=inv_no,
                        operation_type=PaymentOperationType.REMAINING,
                        member=member,
                        amount=paid_now,
                        payment_method=payment_method,
                        notes=notes or f"سداد متبقي. المتبقي بعد السداد: {new_remaining}",
                        created_by=request.user,
                    )

                    # Send WhatsApp Receipt with HTML Invoice
                    if created_pay:
                        queue_payment_receipt_whatsapp(created_pay)

                    messages.success(request, f"تم تسجيل سداد {paid_now} {profile.currency} للعضو {member.name}. المتبقي الآن: {new_remaining} {profile.currency}")
                    return redirect(f"/payments/{created_pay.id}/?auto=1")
                return redirect("members:smart_operations")

    # Initial GET resolution if query or member_id passed
    pre_query = request.GET.get("q", "").strip()
    pre_member = None
    if request.GET.get("member_id"):
        pre_member = Member.objects.filter(id=request.GET.get("member_id")).first()
    elif pre_query:
        candidates = Member.objects.filter(
            Q(name__iexact=pre_query) | Q(mobile=pre_query) | Q(member_id=pre_query)
        )
        if candidates.count() == 1:
            pre_member = candidates.first()

    coaches = Employee.objects.filter(role=EmployeeRole.TRAINER, status=EmployeeStatus.ACTIVE).order_by("name")

    context = {
        "plans": plans,
        "payment_methods": payment_methods,
        "pre_query": pre_query,
        "pre_member": pre_member,
        "coaches": coaches,
        "today_str": today.strftime("%Y-%m-%d"),
    }
    return render(request, "members/smart_operations.html", context)


@login_required
def member_search_api(request):
    """
    Fast JSON Search API for members by name, code, or phone.
    Used for instant auto-complete in Bar Sales, Quick Payments, and Modal Pickers.
    """
    query = request.GET.get("q", "").strip()
    if not query or len(query) < 1:
        return JsonResponse({"results": []})

    today = timezone.localdate()
    members = Member.objects.filter(
        Q(name__icontains=query) | Q(mobile__icontains=query) | Q(member_id__icontains=query)
    ).order_by("name")[:15]

    results = []
    for m in members:
        is_active = bool(m.last_subscription_end and m.last_subscription_end >= today)
        results.append({
            "id": m.id,
            "member_id": m.member_id,
            "name": m.name,
            "mobile": m.mobile,
            "is_active": is_active,
            "status_label": "نشط" if is_active else "منتهي",
            "has_debt": m.current_remaining > Decimal("0.00"),
            "remaining": str(m.current_remaining),
        })

    return JsonResponse({"results": results})

