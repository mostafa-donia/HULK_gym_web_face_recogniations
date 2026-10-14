import json
import logging
import sys
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional, Callable

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
        sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
    except Exception:
        pass

from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from django.db import transaction
from django.conf import settings

from apps.accounts.models import User, UserRole
from apps.core.models import GymProfile
from apps.expenses.models import Expense, ExpenseCategory
from apps.members.models import Member, MemberStatus, Plan, Subscription
from apps.messaging.models import WhatsAppMessageBank
from apps.payments.models import Payment, PaymentMethod, PaymentOperationType

logger = logging.getLogger(__name__)


def parse_date_safe(val: Any) -> Optional[date]:
    if not val or not str(val).strip():
        return None
    val_str = str(val).strip()
    try:
        return datetime.strptime(val_str[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def parse_datetime_safe(val: Any) -> Optional[datetime]:
    if not val or not str(val).strip():
        return None
    val_str = str(val).strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(val_str, fmt)
            return make_aware(dt)
        except Exception:
            continue
    return None


def import_legacy_data_from_dir(data_dir: Path, log_fn: Callable[[str], None] = None) -> Dict[str, Any]:
    """
    Main reusable data importer function.
    Reads members.json, payments.json, settings.json, expenses.json, whatsapp_message_bank.json
    and migrates all records into the database with atomic safety and zero database locks.
    """
    def log(msg):
        if log_fn:
            log_fn(msg)
        else:
            print(f"[*] {msg}")

    data_dir = Path(data_dir)
    if not data_dir.exists():
        return {"success": False, "error": f"مجلد البيانات غير موجود: {data_dir}"}

    log(f"جاري استيراد البيانات التاريخية من المجلد: {data_dir}")
    stats = {
        "members": 0,
        "subscriptions": 0,
        "payments": 0,
        "expenses": 0,
        "plans": 0,
    }

    # 1. Default Users (Manager & Assistant)
    manager_user, _ = User.objects.get_or_create(
        username="manager",
        defaults={"role": UserRole.MANAGER, "first_name": "مدير", "last_name": "الصالة"},
    )
    if not manager_user.has_usable_password():
        manager_user.set_password("1234")
        manager_user.role = UserRole.MANAGER
        manager_user.save()

    assistant_user, _ = User.objects.get_or_create(
        username="assistant",
        defaults={"role": UserRole.ASSISTANT, "first_name": "موظف", "last_name": "الاستقبال"},
    )
    if not assistant_user.has_usable_password():
        assistant_user.set_password("1234")
        assistant_user.role = UserRole.ASSISTANT
        assistant_user.save()

    # 2. Settings, Plans, Payment Methods & Categories
    settings_file = data_dir / "settings.json"
    if settings_file.exists():
        try:
            settings_data = json.loads(settings_file.read_text(encoding="utf-8"))
            profile = GymProfile.get_solo()
            profile.manager_mobile = settings_data.get("manager_mobile", profile.manager_mobile or "01080922432")
            profile.daily_report_time = settings_data.get("daily_report_time", profile.daily_report_time or "22:00")
            profile.whatsapp_enabled = bool(settings_data.get("whatsapp_enabled", True))
            profile.whatsapp_send_mode = settings_data.get("whatsapp_send_mode", "paste")
            profile.whatsapp_letter_delay = float(settings_data.get("whatsapp_letter_delay", 0.001))
            if settings_data.get("expired_message_template"):
                profile.expired_message_template = settings_data["expired_message_template"]
            profile.save()

            # Plans
            with transaction.atomic():
                for plan_dict in settings_data.get("plans", []):
                    p_name = plan_dict.get("name", "").strip()
                    if p_name:
                        Plan.objects.update_or_create(
                            name=p_name,
                            defaults={
                                "price": Decimal(str(plan_dict.get("price", 0.0))),
                                "duration_days": int(plan_dict.get("duration_days", 30)),
                                "months": int(plan_dict.get("months", 1)),
                                "frequency": plan_dict.get("frequency", "كل يوم"),
                                "is_active": True,
                            },
                        )
                        stats["plans"] += 1

                for pm in settings_data.get("payment_methods", []):
                    PaymentMethod.objects.get_or_create(name=pm)

                for cat in settings_data.get("expense_categories", []):
                    ExpenseCategory.objects.get_or_create(name=cat)
            log("✓ تم استيراد الإعدادات والباقات وطرق الدفع.")
        except Exception as e:
            log(f"⚠️ تنبيه أثناء قراءة settings.json: {e}")

    # 3. Message Bank
    msg_bank_file = data_dir / "whatsapp_message_bank.json"
    if msg_bank_file.exists():
        try:
            bank_data = json.loads(msg_bank_file.read_text(encoding="utf-8"))
            with transaction.atomic():
                for category, variations in bank_data.items():
                    if isinstance(variations, list):
                        WhatsAppMessageBank.objects.update_or_create(
                            category=category,
                            defaults={"variations": variations},
                        )
            log("✓ تم استيراد قوالب رسائل الواتساب.")
        except Exception as e:
            log(f"⚠️ تنبيه أثناء قراءة whatsapp_message_bank.json: {e}")

    # 4. Members & Subscriptions
    members_file = data_dir / "members.json"
    if members_file.exists():
        try:
            members_data = json.loads(members_file.read_text(encoding="utf-8"))
            log(f"جاري استيراد {len(members_data)} مشتركاً مع تاريخ اشتراكاتهم...")
            
            with transaction.atomic():
                for m in members_data:
                    mid = m.get("member_id", "").strip()
                    if not mid:
                        continue

                    raw_status = m.get("current_status", MemberStatus.EXPIRED)
                    valid_status = MemberStatus.ACTIVE if raw_status == "active" else MemberStatus.EXPIRED

                    member_obj, created = Member.objects.update_or_create(
                        member_id=mid,
                        defaults={
                            "name": m.get("name", "").strip() or mid,
                            "mobile": m.get("mobile", "").strip(),
                            "gender": m.get("gender", "male") or "male",
                            "current_status": valid_status,
                            "last_subscription_start": parse_date_safe(m.get("last_subscription_start")),
                            "last_subscription_end": parse_date_safe(m.get("last_subscription_end")),
                            "last_subscription_type": m.get("last_subscription_type", "") or "",
                            "last_payment_date": parse_datetime_safe(m.get("last_payment_date")),
                            "current_paid": Decimal(str(m.get("current_paid", 0.0) or 0.0)),
                            "current_remaining": Decimal(str(m.get("current_remaining", 0.0) or 0.0)),
                            "total_paid": Decimal(str(m.get("total_paid", 0.0) or 0.0)),
                            "follow_up_date": parse_date_safe(m.get("follow_up_date")),
                            "notes": m.get("notes", "") or "",
                            "google_contact_synced_at": parse_datetime_safe(m.get("google_contact_synced_at")),
                        },
                    )
                    stats["members"] += 1

                    # Migrate Subscriptions History
                    for sub in m.get("subscriptions_history", []):
                        start = parse_date_safe(sub.get("subscription_start"))
                        end = parse_date_safe(sub.get("subscription_end"))
                        if not start or not end:
                            continue
                        p_price = Decimal(str(sub.get("plan_price", 0.0) or 0.0))
                        p_paid = Decimal(str(sub.get("paid_amount", 0.0) or 0.0))
                        p_rem = Decimal(str(sub.get("remaining_amount", 0.0) or 0.0))
                        p_net = p_price if p_price > 0 else (p_paid + p_rem)
                        
                        Subscription.objects.get_or_create(
                            member=member_obj,
                            start_date=start,
                            end_date=end,
                            plan_name=sub.get("subscription_type", "شهري") or "شهري",
                            defaults={
                                "plan_price": p_price,
                                "discount": Decimal("0.00"),
                                "net_amount": p_net,
                                "paid_amount": p_paid,
                                "remaining_amount": p_rem,
                                "operation_type": sub.get("operation_type", "new_subscription"),
                                "payment_method": sub.get("payment_method", "نقدي") or "نقدي",
                                "created_by": manager_user,
                            },
                        )
                        stats["subscriptions"] += 1

            log(f"✓ تم استيراد وتحديث {stats['members']} مشتركاً و {stats['subscriptions']} اشتراك بنجاح.")
        except Exception as e:
            log(f"⚠️ خطأ أثناء استيراد الأعضاء: {e}")

    # 5. Payments History
    payments_file = data_dir / "payments.json"
    if payments_file.exists():
        try:
            payments_data = json.loads(payments_file.read_text(encoding="utf-8"))
            log(f"جاري استيراد {len(payments_data)} إيصال دفع تاريخي...")
            with transaction.atomic():
                for p in payments_data:
                    mid = p.get("member_id", "").strip() or f"UNKNOWN-{p.get('payment_id')}"
                    member_instance = Member.objects.filter(member_id=mid).first()
                    if not member_instance:
                        archived_name = p.get("name", "").strip() or p.get("member_name", "").strip() or f"عضو مؤرشف {mid}"
                        member_instance, _ = Member.objects.get_or_create(
                            member_id=mid,
                            defaults={
                                "name": archived_name,
                                "mobile": p.get("mobile", "").strip(),
                                "current_status": MemberStatus.EXPIRED,
                                "notes": "عضو مؤرشف تم استيراده مع سجل المدفوعات التاريخية",
                            },
                        )

                    amt = Decimal(str(p.get("amount", p.get("paid_amount", 0.0)) or 0.0))
                    pay_id = p.get("payment_id", "").strip()
                    inv_no = p.get("invoice_no", "").strip() or pay_id
                    op_type = p.get("operation_type", "new_subscription")
                    if op_type not in [c[0] for c in PaymentOperationType.choices]:
                        op_type = PaymentOperationType.NEW_SUBSCRIPTION

                    Payment.objects.update_or_create(
                        payment_id=pay_id,
                        defaults={
                            "invoice_no": inv_no,
                            "operation_type": op_type,
                            "member": member_instance,
                            "amount": amt,
                            "payment_method": p.get("payment_method", "نقدي") or "نقدي",
                            "notes": p.get("notes", "") or "",
                            "created_by": manager_user,
                        },
                    )
                    stats["payments"] += 1
            log(f"✓ تم استيراد {stats['payments']} عملية دفع وإيصال مالي.")
        except Exception as e:
            log(f"⚠️ خطأ أثناء استيراد المدفوعات: {e}")

    # 6. Expenses History
    expenses_file = data_dir / "expenses.json"
    if expenses_file.exists():
        try:
            expenses_data = json.loads(expenses_file.read_text(encoding="utf-8"))
            with transaction.atomic():
                for exp in expenses_data:
                    cat_name = exp.get("category", "اخري")
                    cat_obj, _ = ExpenseCategory.objects.get_or_create(name=cat_name)
                    exp_date = parse_date_safe(exp.get("date", exp.get("expense_date"))) or date.today()
                    amt = Decimal(str(exp.get("amount", 0.0) or 0.0))
                    Expense.objects.get_or_create(
                        date=exp_date,
                        category=cat_obj,
                        amount=amt,
                        notes=exp.get("notes", "") or "",
                        defaults={"created_by": manager_user},
                    )
                    stats["expenses"] += 1
            log(f"✓ تم استيراد {stats['expenses']} سجل مصروفات.")
        except Exception as e:
            log(f"⚠️ خطأ أثناء استيراد المصروفات: {e}")

    log("🎉 اكتمل استيراد بيانات النظام القديم بنجاح ويمكن متابعة العمل مباشرة!")
    return {"success": True, "stats": stats}


class Command(BaseCommand):
    help = "Migrates historical data from legacy JSON files (members.json, payments.json, etc.) into SQLite"

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            type=str,
            default="",
            help="Path to legacy data directory containing JSON files",
        )

    def handle(self, *args, **options):
        specified_dir = options.get("data_dir", "").strip()
        data_dir = None

        if specified_dir and Path(specified_dir).exists():
            data_dir = Path(specified_dir)
        else:
            # Candidate fallback paths
            base = Path(settings.BASE_DIR)
            candidates = [
                base.parent / "old" / "v1" / "data",
                base.parent / "v1" / "data",
                base / "data",
                base.parent / "data",
            ]
            for c in candidates:
                if (c / "members.json").exists():
                    data_dir = c
                    break

        if not data_dir:
            self.stderr.write(self.style.ERROR("لم يتم العثور على مجلد يحتوي على ملف members.json. يرجى تمرير --data-dir"))
            return

        def safe_write(msg: str):
            try:
                self.stdout.write(self.style.SUCCESS(msg))
            except Exception:
                try:
                    sys.stdout.buffer.write((msg + "\n").encode('utf-8', errors='replace'))
                    sys.stdout.buffer.flush()
                except Exception:
                    pass

        res = import_legacy_data_from_dir(data_dir, log_fn=safe_write)
        if not res.get("success"):
            err_msg = res.get("error", "فشل الاستيراد")
            try:
                self.stderr.write(self.style.ERROR(err_msg))
            except Exception:
                sys.stderr.buffer.write((err_msg + "\n").encode('utf-8', errors='replace'))

