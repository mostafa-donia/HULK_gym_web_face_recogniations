import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware

from apps.accounts.models import User, UserRole
from apps.core.models import GymProfile
from apps.expenses.models import Expense, ExpenseCategory
from apps.members.models import Member, MemberStatus, Plan, Subscription
from apps.messaging.models import WhatsAppMessageBank
from apps.payments.models import Payment, PaymentMethod, PaymentOperationType


def parse_date_safe(val: Any) -> Optional[datetime.date]:
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


class Command(BaseCommand):
    help = "Migrate historical data from legacy JSON files in v1/data into the Django SQLite database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            type=str,
            default="d:/move/career/gym system/v1/data",
            help="Path to legacy data directory",
        )

    def handle(self, *args, **options):
        data_dir = Path(options["data_dir"])
        if not data_dir.exists():
            self.stderr.write(self.style.ERROR(f"Data directory not found: {data_dir}"))
            return

        self.stdout.write(self.style.NOTICE(f"Starting data migration from: {data_dir}"))

        # 1. Default Users
        manager_user, created_m = User.objects.get_or_create(
            username="manager",
            defaults={"role": UserRole.MANAGER, "first_name": "مدير", "last_name": "الصالة"},
        )
        if created_m or not manager_user.has_usable_password():
            manager_user.set_password("1234")
            manager_user.role = UserRole.MANAGER
            manager_user.save()
            self.stdout.write(self.style.SUCCESS("Created Manager user: manager (password: 1234)"))

        assistant_user, created_a = User.objects.get_or_create(
            username="assistant",
            defaults={"role": UserRole.ASSISTANT, "first_name": "موظف", "last_name": "الاستقبال"},
        )
        if created_a or not assistant_user.has_usable_password():
            assistant_user.set_password("1234")
            assistant_user.role = UserRole.ASSISTANT
            assistant_user.save()
            self.stdout.write(self.style.SUCCESS("Created Assistant user: assistant (password: 1234)"))

        # 2. Settings, Plans, Payment Methods & Categories
        settings_file = data_dir / "settings.json"
        if settings_file.exists():
            settings_data = json.loads(settings_file.read_text(encoding="utf-8"))
            profile = GymProfile.get_solo()
            profile.manager_mobile = settings_data.get("manager_mobile", "01080922432")
            profile.daily_report_time = settings_data.get("daily_report_time", "17:09")
            profile.whatsapp_enabled = bool(settings_data.get("whatsapp_enabled", True))
            profile.whatsapp_send_mode = settings_data.get("whatsapp_send_mode", "paste")
            profile.whatsapp_letter_delay = float(settings_data.get("whatsapp_letter_delay", 0.001))
            if settings_data.get("expired_message_template"):
                profile.expired_message_template = settings_data["expired_message_template"]
            profile.save()

            # Plans
            for plan_dict in settings_data.get("plans", []):
                Plan.objects.update_or_create(
                    name=plan_dict["name"],
                    defaults={
                        "price": Decimal(str(plan_dict.get("price", 0.0))),
                        "duration_days": int(plan_dict.get("duration_days", 28)),
                        "months": int(plan_dict.get("months", 1)),
                        "frequency": plan_dict.get("frequency", "كل يوم"),
                        "is_active": True,
                    },
                )

            # Payment Methods
            for pm in settings_data.get("payment_methods", []):
                PaymentMethod.objects.get_or_create(name=pm)

            # Expense Categories
            for cat in settings_data.get("expense_categories", []):
                ExpenseCategory.objects.get_or_create(name=cat)

            self.stdout.write(self.style.SUCCESS("Migrated settings, plans, payment methods, and expense categories."))

        # 3. Message Bank
        msg_bank_file = data_dir / "whatsapp_message_bank.json"
        if msg_bank_file.exists():
            bank_data = json.loads(msg_bank_file.read_text(encoding="utf-8"))
            for category, variations in bank_data.items():
                if isinstance(variations, list):
                    WhatsAppMessageBank.objects.update_or_create(
                        category=category,
                        defaults={"variations": variations},
                    )
            self.stdout.write(self.style.SUCCESS("Migrated WhatsApp message bank templates."))

        # 4. Members & Subscriptions
        members_file = data_dir / "members.json"
        legacy_member_count = 0
        legacy_enrolled_count = 0
        if members_file.exists():
            members_data = json.loads(members_file.read_text(encoding="utf-8"))
            legacy_member_count = len(members_data)
            for m in members_data:
                mid = m.get("member_id", "").strip()
                if not mid:
                    continue
                fp_id = m.get("fingerprint_id")
                if fp_id is not None and fp_id != "" and fp_id != 0:
                    try:
                        fp_id = int(fp_id)
                        legacy_enrolled_count += 1
                    except Exception:
                        fp_id = None
                else:
                    fp_id = None

                member_obj, _ = Member.objects.update_or_create(
                    member_id=mid,
                    defaults={
                        "name": m.get("name", "").strip() or mid,
                        "mobile": m.get("mobile", "").strip(),
                        "gender": m.get("gender", "male") or "male",
                        "current_status": m.get("current_status", MemberStatus.EXPIRED),
                        "fingerprint_id": fp_id,
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

            self.stdout.write(self.style.SUCCESS(f"Migrated {Member.objects.count()} members."))

        # 5. Payments
        payments_file = data_dir / "payments.json"
        legacy_payment_count = 0
        legacy_revenue_total = Decimal("0.00")
        if payments_file.exists():
            payments_data = json.loads(payments_file.read_text(encoding="utf-8"))
            legacy_payment_count = len(payments_data)
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
                legacy_revenue_total += amt

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

            self.stdout.write(self.style.SUCCESS(f"Migrated {Payment.objects.count()} payments."))

        # 6. Expenses
        expenses_file = data_dir / "expenses.json"
        if expenses_file.exists():
            expenses_data = json.loads(expenses_file.read_text(encoding="utf-8"))
            for exp in expenses_data:
                cat_name = exp.get("category", "اخري")
                cat_obj, _ = ExpenseCategory.objects.get_or_create(name=cat_name)
                exp_date = parse_date_safe(exp.get("date", exp.get("expense_date"))) or datetime.today().date()
                Expense.objects.create(
                    category=cat_obj,
                    amount=Decimal(str(exp.get("amount", 0.0))),
                    description=exp.get("description", "") or "",
                    expense_date=exp_date,
                    created_by=manager_user,
                )

        # 7. Print Reconciliation Report
        db_member_count = Member.objects.count()
        db_payment_count = Payment.objects.count()
        db_revenue_total = sum((p.amount for p in Payment.objects.all()), Decimal("0.00"))
        db_enrolled_count = Member.objects.filter(fingerprint_id__isnull=False).count()

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.MIGRATE_HEADING("HULK GYM DATA MIGRATION RECONCILIATION REPORT"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Members:  Legacy = {legacy_member_count} | DB = {db_member_count}")
        self.stdout.write(f"Payments: Legacy = {legacy_payment_count} | DB = {db_payment_count} | Diff = {db_payment_count - legacy_payment_count}")
        self.stdout.write(f"Revenue:  Legacy = {legacy_revenue_total:.2f} EGP | DB = {db_revenue_total:.2f} EGP | Diff = {(db_revenue_total - legacy_revenue_total):.2f} EGP")
        self.stdout.write(f"Biometrics: Enrolled Legacy = {legacy_enrolled_count} | DB = {db_enrolled_count}")
        self.stdout.write("=" * 60)

        if db_payment_count == legacy_payment_count and db_revenue_total == legacy_revenue_total:
            self.stdout.write(self.style.SUCCESS("[OK] RECONCILIATION VERIFIED: 100% PERFECT FINANCIAL & RECORD PARITY"))
        else:
            self.stdout.write(self.style.WARNING("[NOTICE] RECONCILIATION NOTICE: Some discrepancy detected."))
