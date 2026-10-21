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
    {
        "id": "intro_calc",
        "title": "عرض النظام وحاسبة الأسعار التفاعلية",
        "category": "تعريف وعرض",
        "text": "أهلاً بحضرتك كابتن {name}، يسعدنا تواصلك بخصوص نظام Systemize لإدارة الجيمات وبصمة الوجه الذكية AI.\nتقدر تحسب تكلفة باقتك وإمكانية التقسيط بنفسك مباشرة عبر الرابط التالي:\nhttps://mostafa-donia.github.io/HULK_gym_web_face_recogniations/\nجاهز لأي استفسار أو تحديد موعد ديمو تجريبي لصالتك {gym_name}."
    },
    {
        "id": "roi_loss",
        "title": "دراسة الجدوى وتوفير الخسائر (احسبها صح)",
        "category": "مبيعات وإقناع",
        "text": "كابتن {name}، دراسة بسيطة:\nلو كل يوم بتخسر اشتراك واحد بس بـ 400 ج، ده معناه 12,000 ج شهرياً و 144,000 ج سنوياً مهدرة!\nنظام بصمة الوجه والواتساب الآلي بيقفلوا التسريب ده وبيدفعوا تمنهم بنفسهم من أول شهر.\nاحسبها لصالتك {gym_name} وشوف التفاصيل:\nhttps://mostafa-donia.github.io/HULK_gym_web_face_recogniations/"
    },
    {
        "id": "installment_offer",
        "title": "عرض التقسيط المرن (3 شهور أو 6 شهور)",
        "category": "عروض وأسعار",
        "text": "مساء الخير كابتن {name}، متاح حالياً تقسيط نظام Systemize لصالة {gym_name} على 3 شهور (+10%) أو 6 شهور (+20%) فقط لتسهيل التشغيل الفوري بدون ضغط مالي.\nهل تحب نجهز لحضرتك ديمو تجريبي أو نحدد موعد للتركيب؟"
    },
    {
        "id": "followup_check",
        "title": "متابعة واستفسار بعد إرسال العرض",
        "category": "متابعة دورية",
        "text": "أهلاً كابتن {name}، بنتابع مع حضرتك بخصوص نظام {gym_name}.. هل اطلعت على العرض والحاسبة؟ ولو في أي استفسار أو حابب نجرب السيستم مع حضرتك أنا تحت أمرك في أي وقت."
    },
    {
        "id": "demo_invite",
        "title": "دعوة لتجربة ديمو مجاني",
        "category": "تجربة مجانية",
        "text": "كابتن {name}، بنقدم لحضرتك نسخة ديمو تجريبية مجانية لنظام Systemize لصالة {gym_name} لتجربة كل الميزات على أرض الواقع.\nنقدر نحدد موعد لتجهيز النسخة في الوقت المناسب لحضرتك."
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


def calculate_followup_stats(leads_dict: dict) -> dict:
    """Calculates counts for today, overdue, upcoming, and status counts."""
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
        st = lead.get("status", "new")
        if st in stage_counts:
            stage_counts[st] += 1

        fdate_str = lead.get("next_followup_date")
        timing_status = "none"  # "overdue", "today", "upcoming", "none"
        remaining_days = None

        if fdate_str and st not in ["won", "lost"]:
            try:
                # Accept ISO or YYYY-MM-DD format
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
        lead_copy["timing_status"] = timing_status
        lead_copy["remaining_days"] = remaining_days
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
    """Adds a new lead or updates existing lead."""
    data = load_crm_data()
    leads = data["leads"]

    lead_id = lead_data.get("id")
    is_new = False
    if not lead_id or lead_id not in leads:
        lead_id = f"LEAD-{int(time.time() * 1000) % 1000000:06d}"
        is_new = True

    now_iso = datetime.now().isoformat()

    gym_name = (lead_data.get("gym_name") or "").strip()
    contact_name = (lead_data.get("contact_name") or "").strip()
    phone = (lead_data.get("phone") or "").strip()

    if not gym_name and not contact_name:
        raise ValueError("يجب كتابة اسم الجيم أو اسم المسؤول على الأقل.")

    existing = leads.get(lead_id, {})

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
        "gym_name": gym_name or existing.get("gym_name", "جيم غير مسمى"),
        "contact_name": contact_name or existing.get("contact_name", "كابتن"),
        "phone": phone or existing.get("phone", ""),
        "city": (lead_data.get("city") or existing.get("city", "")).strip(),
        "source": (lead_data.get("source") or existing.get("source", "مباشر / فيسبوك")).strip(),
        "status": lead_data.get("status") or existing.get("status", "new"),
        "budget": lead_data.get("budget") or existing.get("budget", ""),
        "interested_package": lead_data.get("interested_package") or existing.get("interested_package", "باقة أساسية + بصمة وجه"),
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

    if next_days is not None and next_days > 0:
        lead["next_followup_date"] = (datetime.now() + timedelta(days=next_days)).strftime("%Y-%m-%d 14:00")
    elif next_days == 0:
        # Done or closed
        lead["next_followup_date"] = ""

    save_crm_data(data)
    return {"success": True, "lead": lead}


def delete_lead(lead_id: str) -> bool:
    """Deletes a lead from CRM."""
    data = load_crm_data()
    if lead_id in data["leads"]:
        del data["leads"][lead_id]
        save_crm_data(data)
        return True
    return False


def render_template_text(template_text: str, lead: dict) -> str:
    """Fills placeholders in template text with lead info."""
    name = lead.get("contact_name") or "كابتن"
    gym_name = lead.get("gym_name") or "صالتكم الرياضية"
    city = lead.get("city") or "مدينتكم"
    budget = lead.get("budget") or "الميزانية المحددة"
    pkg = lead.get("interested_package") or "باقة النظام"

    text = template_text.replace("{name}", name)
    text = text.replace("{gym_name}", gym_name)
    text = text.replace("{city}", city)
    text = text.replace("{budget}", budget)
    text = text.replace("{package}", pkg)
    return text


def send_whatsapp_to_lead(lead_id: str, message_text: str, auto_desktop: bool = False) -> dict:
    """
    Sends WhatsApp message to a lead.
    - If auto_desktop is True, uses native desktop automation.
    - Also generates clean wa.me link for browser/phone view.
    """
    data = load_crm_data()
    if lead_id not in data["leads"]:
        raise ValueError("العميل غير موجود.")

    lead = data["leads"][lead_id]
    phone = lead.get("phone", "")
    norm_phone = normalize_phone(phone)

    if not norm_phone:
        raise ValueError("رقم الهاتف غير مسجل للعميل.")

    rendered = render_template_text(message_text, lead)
    encoded_text = rendered.replace("\n", "%0A")
    web_link = f"https://wa.me/{norm_phone}?text={encoded_text}"

    auto_success = False
    error_msg = ""

    if auto_desktop:
        try:
            if _whatsapp_desktop_available and wa_engine:
                success, err, _ = wa_engine.send_message(
                    name=lead.get("contact_name", "كابتن"),
                    phone=norm_phone,
                    message_text=rendered,
                    gym_name=lead.get("gym_name", "Systemize OS"),
                    use_clipboard=True,
                    close_after=True
                )
                auto_success = success
                if not success:
                    error_msg = err
            else:
                # Direct protocol launch
                import webbrowser
                proto_url = f"whatsapp://send?phone={norm_phone}&text={encoded_text}"
                webbrowser.open(proto_url)
                auto_success = True
        except Exception as ex:
            error_msg = str(ex)
            auto_success = False

    # Log in lead's history
    now_iso = datetime.now().isoformat()
    lead.setdefault("whatsapp_history", []).append({
        "timestamp": now_iso,
        "text": rendered,
        "auto_sent": auto_success if auto_desktop else False,
        "phone": norm_phone
    })
    lead["last_contacted_at"] = now_iso
    save_crm_data(data)

    return {
        "success": True,
        "web_link": web_link,
        "auto_desktop_attempted": auto_desktop,
        "auto_desktop_success": auto_success,
        "error_message": error_msg,
        "rendered_message": rendered,
        "phone": norm_phone
    }


def start_bulk_whatsapp_campaign(lead_ids: list, template_text: str, delay_between_seconds: int = 4):
    """Starts a background thread to send automated WhatsApp messages to multiple leads safely."""
    global _bulk_queue_status

    with _bulk_queue_lock:
        if _bulk_queue_status["is_running"]:
            return False, "هناك حملة إرسال أخرى قيد التشغيل بالفعل حالياً."

        _bulk_queue_status["is_running"] = True
        _bulk_queue_status["total"] = len(lead_ids)
        _bulk_queue_status["sent"] = 0
        _bulk_queue_status["failed"] = 0
        _bulk_queue_status["current_lead"] = ""
        _bulk_queue_status["logs"] = []

    def _worker():
        global _bulk_queue_status
        data = load_crm_data()
        leads = data.get("leads", {})

        for idx, lid in enumerate(lead_ids):
            if lid not in leads:
                continue

            lead = leads[lid]
            lead_name = f"{lead.get('gym_name', '')} ({lead.get('contact_name', '')})"
            with _bulk_queue_lock:
                _bulk_queue_status["current_lead"] = lead_name

            try:
                res = send_whatsapp_to_lead(lid, template_text, auto_desktop=True)
                with _bulk_queue_lock:
                    if res.get("auto_desktop_success", False):
                        _bulk_queue_status["sent"] += 1
                        _bulk_queue_status["logs"].append(f"✓ تم الإرسال بنجاح إلى: {lead_name}")
                    else:
                        _bulk_queue_status["failed"] += 1
                        _bulk_queue_status["logs"].append(f"⚠ تعذر الإرسال التلقائي إلى: {lead_name}")
            except Exception as e:
                with _bulk_queue_lock:
                    _bulk_queue_status["failed"] += 1
                    _bulk_queue_status["logs"].append(f"✗ خطأ عند إرسال: {lead_name} ({e})")

            # Safe human-like pause between messages to avoid WhatsApp spam triggers
            sleep_time = random.uniform(max(2.5, delay_between_seconds - 1), delay_between_seconds + 2.5)
            time.sleep(sleep_time)

        with _bulk_queue_lock:
            _bulk_queue_status["is_running"] = False
            _bulk_queue_status["current_lead"] = "اكتملت الحملة بنجاح ✓"

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return True, "تم بدء حملة الإرسال التلقائي في الخلفية بنجاح."


def get_bulk_queue_status() -> dict:
    """Returns the current state of the background WhatsApp sending queue."""
    with _bulk_queue_lock:
        return dict(_bulk_queue_status)
