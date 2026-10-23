import os
import sys
import json
import time
import uuid
import random
import threading
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
CRM_FILE = os.path.join(BASE_DIR, "crm_leads.json")

# Ensure utf-8 output
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Try importing existing whatsapp_sender from web_face if available
_whatsapp_desktop_available = False
try:
    sys.path.insert(0, os.path.join(PARENT_DIR, "web_face"))
    from apps.messaging import whatsapp_sender as wa_engine
    _whatsapp_desktop_available = True
except Exception as e:
    wa_engine = None
    _whatsapp_desktop_available = False

DEFAULT_TEMPLATES = [
    # Systemize Gym OS Templates
    {
        "id": "gym_intro_calc",
        "product_id": "systemize_gym",
        "title": "عرض جيم: حاسبة الأسعار وبصمة الوجه الذكية",
        "category": "Gym OS",
        "text": "أهلاً بحضرتك كابتن {name}، يسعدنا تواصلك بخصوص نظام Systemize لإدارة الجيمات وبصمة الوجه الذكية AI.\nتقدر تحسب تكلفة باقتك وإمكانية التقسيط بنفسك مباشرة عبر الرابط التالي:\nhttps://mostafa-donia.github.io/HULK_gym_web_face_recogniations/\nجاهز لأي استفسار أو تحديد موعد ديمو تجريبي لصالتك {business_name}."
    },
    {
        "id": "gym_roi_loss",
        "product_id": "systemize_gym",
        "title": "عرض جيم: دراسة الجدوى وتوفير الخسائر (احسبها صح)",
        "category": "Gym OS",
        "text": "كابتن {name}، دراسة بسيطة:\nلو كل يوم بتخسر اشتراك واحد بس بـ 400 ج، ده معناه 12,000 ج شهرياً و 144,000 ج سنوياً مهدرة!\nنظام بصمة الوجه والواتساب الآلي بيقفلوا التسريب ده وبيدفعوا تمنهم بنفسهم من أول شهر.\nاحسبها لصالتك {business_name} وشوف التفاصيل:\nhttps://mostafa-donia.github.io/HULK_gym_web_face_recogniations/"
    },
    {
        "id": "gym_installment",
        "product_id": "systemize_gym",
        "title": "عرض جيم: عرض التقسيط المرن (3 أو 6 شهور)",
        "category": "Gym OS",
        "text": "مساء الخير كابتن {name}، متاح حالياً تقسيط نظام Systemize Gym OS لصالة {business_name} على 3 شهور (+10%) أو 6 شهور (+20%) فقط لتسهيل التشغيل الفوري بدون ضغط مالي.\nهل تحب نجهز لحضرتك ديمو تجريبي أو نحدد موعد للتركيب؟"
    },
    {
        "id": "gym_followup",
        "product_id": "systemize_gym",
        "title": "عرض جيم: متابعة واستفسار بعد إرسال العرض",
        "category": "Gym OS",
        "text": "أهلاً كابتن {name}، بنتابع مع حضرتك بخصوص نظام {business_name}.. هل اطلعت على العرض والحاسبة؟ ولو في أي استفسار أو حابب نجرب السيستم مع حضرتك أنا تحت أمرك في أي وقت."
    },
    # Systemize POS & Inventory Templates
    {
        "id": "pos_intro",
        "product_id": "systemize_pos",
        "title": "عرض محلات: نظام الكاشير السريع والمخازن",
        "category": "POS & Inventory",
        "text": "مساء الخير أستاذ {name}، بخصوص إدارة مبيعات ومخازن {business_name}، بنقدم لحضرتك نظام Systemize POS & Inventory:\n• شاشة كاشير فوري تدعم الباركود والطباعة الحرارية.\n• جرد دوري وتنبيهات فورية بنواقص المخزون.\n• إدارة ديون العملاء وحسابات الموردين وفواتير الشراء.\nجاهز لتحديد موعد لمعاينة ديمو مباشر للمحل."
    },
    {
        "id": "pos_security",
        "product_id": "systemize_pos",
        "title": "عرض محلات: منع عجز الدرج وضبط أرباح المحل",
        "category": "POS & Inventory",
        "text": "أستاذ {name}، مع نظام Systemize POS تقدر تقفل ثغرات عجز الدرج والسرقات تماماً عن طريق تقفيل شيفتات الكاشير وسندات الصرف النقدية ومتابعة الأرباح الصافية لكل صنف في {business_name}.\nهل تحب نجهز لحضرتك ديمو تجريبي للبرنامج؟"
    },
    # Systemize Clinic OS Templates
    {
        "id": "clinic_intro",
        "product_id": "systemize_clinic",
        "title": "عرض عيادات: إدارة المواعيد والملفات الطبية والروشتات",
        "category": "Clinic OS",
        "text": "دكتور {name}، تحياتنا لحضرتك من Systemize Clinic OS:\nنظام متكامل لتنظيم عيادتكم / مركزكم الطبي {business_name}:\n• حجز المواعيد اليومية ومنع تكدس المرضى.\n• سجل طبي شامل لتاريخ المريض والروشتات المطبوعة.\n• رسائل واتساب آلية لتذكير المرضى بميعاد الكشف والاستشارة.\nجاهزون لترتيب تجربة سريعة للنظام بالعيادة."
    },
    # General Followup
    {
        "id": "general_followup",
        "product_id": "all",
        "title": "رسالة متابعة عامة ودية",
        "category": "عام",
        "text": "أهلاً بحضرتك {name}، بنتواصل للمتابعة مع حضرتك بخصوص {business_name}.. هل في أي تفاصيل أو استفسار بخصوص البرنامج تحب نوضحه لحضرتك؟ تحت أمرك في أي وقت."
    }
]

# Background queue execution state
_bulk_queue_lock = threading.Lock()
_bulk_queue_status = {
    "is_running": False,
    "total": 0,
    "sent": 0,
    "failed": 0,
    "current_lead": "",
    "logs": []
}


def load_crm_data() -> dict:
    """Loads CRM leads and settings from JSON with default initial structure."""
    if not os.path.exists(CRM_FILE):
        initial = {
            "leads": {},
            "templates": DEFAULT_TEMPLATES,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        save_crm_data(initial)
        return initial

    try:
        with open(CRM_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "leads" not in data:
                data["leads"] = {}
            if "templates" not in data or not data["templates"]:
                data["templates"] = DEFAULT_TEMPLATES
            return data
    except Exception:
        return {"leads": {}, "templates": DEFAULT_TEMPLATES}


def save_crm_data(data: dict):
    """Saves CRM data safely to file."""
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(CRM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_phone(phone: str) -> str:
    """Cleans phone numbers to valid Egyptian / international format."""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("20") and len(digits) == 12:
        return digits
    if digits.startswith("01") and len(digits) == 11:
        return "2" + digits
    if digits.startswith("1") and len(digits) == 10:
        return "20" + digits
    return digits


def calculate_followup_stats(leads_dict: dict, product_id: str = None) -> dict:
    """Calculates counts for today, overdue, upcoming, and status counts with product scoping."""
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    today_end = datetime(now.year, now.month, now.day, 23, 59, 59)

    leads_list = []
    overdue_count = 0
    today_count = 0
    upcoming_count = 0
    stage_counts = {
        "new": 0,
        "contacted": 0,
        "interested": 0,
        "demo_scheduled": 0,
        "offer_sent": 0,
        "followup": 0,
        "won": 0,
        "lost": 0
    }

    for lead_id, lead in leads_dict.items():
        # Product filter
        lead_prod = lead.get("product_id", "systemize_gym")
        if product_id and product_id != "all" and lead_prod != product_id:
            continue

        st = lead.get("status", "new")
        if st in stage_counts:
            stage_counts[st] += 1

        fdate_str = lead.get("next_followup_date")
        timing_status = "none"  # "overdue", "today", "upcoming", "none"
        remaining_days = None

        if fdate_str and st not in ["won", "lost"]:
            try:
                if "T" in fdate_str:
                    fdate = datetime.fromisoformat(fdate_str.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
                else:
                    fdate = datetime.strptime(fdate_str[:10], "%Y-%m-%d")

                diff = (fdate.date() - now.date()).days
                remaining_days = diff

                if fdate < today_start:
                    timing_status = "overdue"
                    overdue_count += 1
                elif today_start <= fdate <= today_end or diff == 0:
                    timing_status = "today"
                    today_count += 1
                else:
                    timing_status = "upcoming"
                    upcoming_count += 1
            except Exception:
                timing_status = "none"

        lead_copy = dict(lead)
        lead_copy["id"] = lead_id
        lead_copy["product_id"] = lead_prod
        lead_copy["timing_status"] = timing_status
        lead_copy["remaining_days"] = remaining_days
        # Ensure business_name is present
        lead_copy["business_name"] = lead.get("business_name") or lead.get("gym_name", "نشاط بدون اسم")
        leads_list.append(lead_copy)

    # Sort: overdue first, then today, then upcoming, then rest
    def sort_key(x):
        timing_priority = {"overdue": 0, "today": 1, "upcoming": 2, "none": 3}
        p = timing_priority.get(x["timing_status"], 3)
        rem = x["remaining_days"] if x["remaining_days"] is not None else 9999
        return (p, rem, x.get("created_at", ""))

    leads_list.sort(key=sort_key)

    return {
        "leads": leads_list,
        "stats": {
            "total": len(leads_list),
            "today": today_count,
            "overdue": overdue_count,
            "upcoming": upcoming_count,
            "stages": stage_counts
        }
    }


def add_or_update_lead(lead_data: dict) -> dict:
    """Adds a new lead or updates existing lead with multi-product tagging."""
    data = load_crm_data()
    leads = data["leads"]

    lead_id = lead_data.get("id")
    is_new = False
    if not lead_id or lead_id not in leads:
        lead_id = f"LEAD-{int(time.time() * 1000) % 1000000:06d}"
        is_new = True

    now_iso = datetime.now().isoformat()

    business_name = (lead_data.get("business_name") or lead_data.get("gym_name") or "").strip()
    contact_name = (lead_data.get("contact_name") or "").strip()
    phone = (lead_data.get("phone") or "").strip()

    if not business_name and not contact_name:
        raise ValueError("يجب كتابة اسم النشاط التجاري أو اسم المسؤول على الأقل.")

    existing = leads.get(lead_id, {})
    product_id = lead_data.get("product_id") or existing.get("product_id") or "systemize_gym"

    # Compute next followup date if interval provided
    interval_days = lead_data.get("followup_days_interval")
    next_fdate = lead_data.get("next_followup_date")
    if interval_days is not None and str(interval_days).isdigit() and int(interval_days) > 0:
        next_fdate = (datetime.now() + timedelta(days=int(interval_days))).strftime("%Y-%m-%d %H:%M")

    # Handle notes array
    notes = existing.get("notes", [])
    new_note_text = (lead_data.get("new_note") or "").strip()
    if new_note_text:
        notes.append({
            "timestamp": now_iso,
            "text": new_note_text,
            "author": "المطور"
        })

    lead_record = {
        "product_id": product_id,
        "gym_name": business_name or existing.get("gym_name", "نشاط تجاري"),
        "business_name": business_name or existing.get("business_name", existing.get("gym_name", "نشاط تجاري")),
        "contact_name": contact_name or existing.get("contact_name", "العميل"),
        "phone": phone or existing.get("phone", ""),
        "city": (lead_data.get("city") or existing.get("city", "")).strip(),
        "source": (lead_data.get("source") or existing.get("source", "مباشر / فيسبوك")).strip(),
        "status": lead_data.get("status") or existing.get("status", "new"),
        "budget": lead_data.get("budget") or existing.get("budget", ""),
        "interested_package": lead_data.get("interested_package") or existing.get("interested_package", "باقة أساسية"),
        "next_followup_date": next_fdate if next_fdate is not None else existing.get("next_followup_date", ""),
        "followup_note": lead_data.get("followup_note") or existing.get("followup_note", ""),
        "notes": notes,
        "whatsapp_history": existing.get("whatsapp_history", []),
        "created_at": existing.get("created_at", now_iso),
        "last_contacted_at": lead_data.get("last_contacted_at") or existing.get("last_contacted_at", now_iso if is_new else "")
    }

    leads[lead_id] = lead_record
    save_crm_data(data)

    return {"lead_id": lead_id, "lead": lead_record, "is_new": is_new}


def record_followup_call(lead_id: str, note_text: str, next_days: int = None, new_status: str = None) -> dict:
    """Records a call/meeting interaction and automatically schedules next follow-up."""
    data = load_crm_data()
    if lead_id not in data["leads"]:
        raise ValueError("العميل غير موجود.")

    lead = data["leads"][lead_id]
    now_iso = datetime.now().isoformat()

    if note_text:
        lead.setdefault("notes", []).append({
            "timestamp": now_iso,
            "text": note_text,
            "author": "المطور"
        })

    lead["last_contacted_at"] = now_iso

    if new_status:
        lead["status"] = new_status

    if next_days is not None and int(next_days) > 0:
        lead["next_followup_date"] = (datetime.now() + timedelta(days=int(next_days))).strftime("%Y-%m-%d %H:%M")
        lead["followup_note"] = note_text[:80] if note_text else "متابعة دورية"

    save_crm_data(data)
    return {"lead_id": lead_id, "lead": lead}


def delete_lead(lead_id: str) -> bool:
    """Deletes a lead from CRM."""
    data = load_crm_data()
    if lead_id in data["leads"]:
        del data["leads"][lead_id]
        save_crm_data(data)
        return True
    return False


def format_template_message(template_text: str, lead: dict) -> str:
    """Replaces placeholders in template text with lead values."""
    contact_name = lead.get("contact_name") or "كابتن"
    b_name = lead.get("business_name") or lead.get("gym_name") or "صالتكم"
    city = lead.get("city") or "مدينتكم"

    text = template_text
    text = text.replace("{name}", contact_name)
    text = text.replace("{contact_name}", contact_name)
    text = text.replace("{gym_name}", b_name)
    text = text.replace("{business_name}", b_name)
    text = text.replace("{city}", city)
    return text


def send_whatsapp_to_lead(lead_id: str, message: str, auto_desktop: bool = False) -> dict:
    """Sends WhatsApp message to lead via Desktop Automation or web link fallback."""
    data = load_crm_data()
    if lead_id not in data["leads"]:
        raise ValueError("العميل غير موجود.")

    lead = data["leads"][lead_id]
    phone = normalize_phone(lead.get("phone", ""))
    if not phone:
        raise ValueError("رقم الهاتف غير مسجل لهذا العميل.")

    formatted_msg = format_template_message(message, lead)
    now_iso = datetime.now().isoformat()

    lead.setdefault("whatsapp_history", []).append({
        "timestamp": now_iso,
        "text": formatted_msg,
        "auto_sent": auto_desktop,
        "phone": phone
    })
    lead["last_contacted_at"] = now_iso
    save_crm_data(data)

    if auto_desktop and _whatsapp_desktop_available and wa_engine:
        def _send_bg():
            try:
                wa_engine.send_whatsapp_message_direct(phone, formatted_msg)
            except Exception as e:
                print(f"[CRM WhatsApp Error]: {e}")

        threading.Thread(target=_send_bg, daemon=True).start()
        return {
            "success": True,
            "mode": "desktop_automation",
            "message": "جاري إرسال الرسالة عبر تطبيق واتساب لسطح المكتب في الخلفية..."
        }

    # Fallback to direct WhatsApp Web URL
    import urllib.parse
    encoded = urllib.parse.quote(formatted_msg)
    wa_url = f"https://wa.me/{phone}?text={encoded}"
    return {
        "success": True,
        "mode": "web_url",
        "url": wa_url,
        "message": "تم تجهيز رابط المحادثة المباشر عبر واتساب."
    }


def start_bulk_whatsapp_campaign(lead_ids: list, message_template: str, delay_seconds: int = 4) -> tuple[bool, str]:
    """Starts background automated WhatsApp campaign to multiple leads."""
    global _bulk_queue_status

    with _bulk_queue_lock:
        if _bulk_queue_status["is_running"]:
            return False, "توجد حملة واتساب جماعية قيد التنفيذ بالفعل حالياً."

        _bulk_queue_status["is_running"] = True
        _bulk_queue_status["total"] = len(lead_ids)
        _bulk_queue_status["sent"] = 0
        _bulk_queue_status["failed"] = 0
        _bulk_queue_status["current_lead"] = ""
        _bulk_queue_status["logs"] = [f"بدء إرسال الحملة إلى {len(lead_ids)} عميل محتمل..."]

    def _worker():
        global _bulk_queue_status
        data = load_crm_data()
        leads = data.get("leads", {})

        for lid in lead_ids:
            with _bulk_queue_lock:
                if not _bulk_queue_status["is_running"]:
                    break

            lead = leads.get(lid)
            if not lead:
                continue

            phone = normalize_phone(lead.get("phone", ""))
            name = lead.get("contact_name") or lead.get("business_name", "عميل")

            with _bulk_queue_lock:
                _bulk_queue_status["current_lead"] = f"{name} ({phone})"

            if not phone:
                with _bulk_queue_lock:
                    _bulk_queue_status["failed"] += 1
                    _bulk_queue_status["logs"].append(f"⚠️ تخطي {name}: رقم الهاتف غير صحيح.")
                continue

            msg = format_template_message(message_template, lead)

            sent_ok = False
            if _whatsapp_desktop_available and wa_engine:
                try:
                    res = wa_engine.send_whatsapp_message_direct(phone, msg)
                    sent_ok = bool(res.get("success", False)) if isinstance(res, dict) else True
                except Exception as e:
                    sent_ok = False

            now_iso = datetime.now().isoformat()
            lead.setdefault("whatsapp_history", []).append({
                "timestamp": now_iso,
                "text": msg,
                "auto_sent": True,
                "phone": phone
            })
            lead["last_contacted_at"] = now_iso

            with _bulk_queue_lock:
                if sent_ok:
                    _bulk_queue_status["sent"] += 1
                    _bulk_queue_status["logs"].append(f"✓ تم الإرسال إلى {name} بنجاح.")
                else:
                    _bulk_queue_status["failed"] += 1
                    _bulk_queue_status["logs"].append(f"❌ تعذر الإرسال إلى {name}.")

            time.sleep(max(2, delay_seconds))

        save_crm_data(data)

        with _bulk_queue_lock:
            _bulk_queue_status["is_running"] = False
            _bulk_queue_status["logs"].append("🎉 اكتمل تنفيذ حملة الواتساب الجماعية.")

    threading.Thread(target=_worker, daemon=True).start()
    return True, f"تم بدء إرسال الحملة إلى {len(lead_ids)} عميل محتمل في الخلفية."


def get_bulk_queue_status() -> dict:
    """Returns status of ongoing WhatsApp bulk queue."""
    with _bulk_queue_lock:
        return dict(_bulk_queue_status)


def import_leads_bulk(
    records: list,
    product_id: str = "systemize_restaurant",
    default_status: str = "new",
    update_existing: bool = True
) -> dict:
    """
    Imports a list of potential customer leads (from Excel, CSV, JSON, or text) into crm_leads.json.
    Deduplicates by normalized phone number or business name.
    """
    data = load_crm_data()
    leads = data["leads"]

    phone_to_id = {}
    for lid, l in leads.items():
        p = normalize_phone(l.get("phone", ""))
        if p:
            phone_to_id[p] = lid

    added_count = 0
    updated_count = 0
    skipped_count = 0
    errors = []

    now_iso = datetime.now().isoformat()
    now_ts = int(time.time() * 1000)

    for idx, row in enumerate(records):
        try:
            raw_phone = str(row.get("phone") or row.get("mobile") or row.get("tel") or row.get("هاتف") or row.get("موبايل") or "").strip()
            norm_phone = normalize_phone(raw_phone)

            business_name = str(row.get("business_name") or row.get("name") or row.get("restaurant_name") or row.get("gym_name") or row.get("اسم_النشاط") or row.get("المطعم") or row.get("الصالة") or "").strip()
            contact_name = str(row.get("contact_name") or row.get("owner_name") or row.get("manager_name") or row.get("المسؤول") or row.get("المدير") or "").strip()
            city = str(row.get("city") or row.get("governorate") or row.get("المدينة") or row.get("المحافظة") or "").strip()
            source = str(row.get("source") or row.get("المصدر") or "استيراد ملف / حملة تسويقية").strip()
            notes_text = str(row.get("notes") or row.get("note") or row.get("ملاحظات") or "").strip()
            budget = str(row.get("budget") or row.get("الميزانية") or "").strip()
            interested_pkg = str(row.get("interested_package") or row.get("package") or row.get("الباقة") or "").strip()

            if not business_name and not contact_name:
                skipped_count += 1
                continue

            existing_id = phone_to_id.get(norm_phone) if norm_phone else None

            if existing_id and not update_existing:
                skipped_count += 1
                continue

            if existing_id and update_existing:
                lead = leads[existing_id]
                if business_name and not lead.get("business_name"):
                    lead["business_name"] = business_name
                if contact_name and not lead.get("contact_name"):
                    lead["contact_name"] = contact_name
                if city and not lead.get("city"):
                    lead["city"] = city
                if notes_text:
                    lead.setdefault("notes", []).append({
                        "timestamp": now_iso,
                        "text": f"ملاحظة مستوردة: {notes_text}"
                    })
                lead["product_id"] = product_id or lead.get("product_id") or "systemize_restaurant"
                updated_count += 1
            else:
                seq_id = (now_ts + idx) % 1000000
                new_id = f"LEAD-{seq_id:06d}"
                lead = {
                    "product_id": product_id or "systemize_restaurant",
                    "business_name": business_name or contact_name,
                    "gym_name": business_name or contact_name,
                    "contact_name": contact_name or business_name,
                    "phone": norm_phone or raw_phone,
                    "city": city,
                    "source": source,
                    "status": default_status or "new",
                    "budget": budget,
                    "interested_package": interested_pkg or "ترشيح ذكي حسب احتياج النشاط",
                    "next_followup_date": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d 14:00"),
                    "followup_note": "اتصال تعريفي وتحديد موعد عرض ديمو مباشر",
                    "notes": [{"timestamp": now_iso, "text": f"تم استيراد العميل للمنظومة. {notes_text}".strip()}] if notes_text else [],
                    "whatsapp_history": [],
                    "created_at": now_iso,
                    "last_contacted_at": now_iso
                }
                leads[new_id] = lead
                if norm_phone:
                    phone_to_id[norm_phone] = new_id
                added_count += 1

        except Exception as e:
            errors.append(f"السطر {idx + 1}: {str(e)}")

    save_crm_data(data)
    return {
        "success": True,
        "added_count": added_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "total_processed": len(records),
        "errors": errors
    }
