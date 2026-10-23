import os
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import json
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify, send_file

# Add BASE_DIR and web_face to Python path to import licensing crypto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)
sys.path.insert(1, os.path.join(PARENT_DIR, "web_face"))

from apps.core.licensing.crypto import (
    generate_offline_license_token,
    verify_offline_license_token,
)
from apps.core.licensing.hwid import get_hardware_fingerprint

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

CLIENTS_FILE = os.path.join(BASE_DIR, "clients.json")
PRODUCTS_FILE = os.path.join(BASE_DIR, "products.json")


# ==========================================
# PRODUCTS CATALOG MANAGEMENT
# ==========================================

DEFAULT_PRODUCTS = {
    "systemize_gym": {
        "id": "systemize_gym",
        "name": "Systemize Gym OS",
        "arabic_name": "نظام النوادي والصالات الرياضية الذكي",
        "icon": "fa-dumbbell",
        "badge_color": "lime",
        "repo_url": "https://github.com/mostafa-donia/HULK_gym_web_face_recogniations",
        "branch": "main",
        "current_version": "v2.0",
        "updates_allowed": True,
        "default_demo_days": 7,
        "features": [
            {"key": "face_recognition", "name": "بصمة الوجه الذكية AI", "default": True},
            {"key": "gate_relay", "name": "بوابات الدخول ومتحكم الريليه", "default": True},
            {"key": "whatsapp", "name": "رسائل وتنبيهات الواتساب الآلية", "default": True},
            {"key": "telegram", "name": "بوت إشعارات تليجرام للمدير", "default": True},
            {"key": "bar", "name": "مبيعات ومخزون البار والمشروبات", "default": True},
            {"key": "payroll", "name": "المدربين وحساب الرواتب والعمولات", "default": True},
            {"key": "retention", "name": "تتبع تجديدات وركود الأعضاء", "default": True},
            {"key": "reports", "name": "التقارير المالية والمحاسبية", "default": True},
            {"key": "barcode", "name": "قارئ الباركود والـ QR", "default": True},
            {"key": "expenses", "name": "المصروفات وسندات الصرف", "default": True},
            {"key": "multi_branch", "name": "إدارة الفروع المتعددة", "default": False}
        ]
    },
    "systemize_pos": {
        "id": "systemize_pos",
        "name": "Systemize POS & Inventory",
        "arabic_name": "نظام المخازن ونقاط البيع والتجارة",
        "icon": "fa-boxes-stacked",
        "badge_color": "sky",
        "repo_url": "https://github.com/mostafa-donia/inventory_win7_kareem",
        "branch": "main",
        "current_version": "v1.0",
        "updates_allowed": True,
        "default_demo_days": 7,
        "features": [
            {"key": "pos_cashier", "name": "شاشة الكاشير السريع وطباعة الفواتير", "default": True},
            {"key": "barcode_scanner", "name": "قارئ الباركود وطباعة الملصقات", "default": True},
            {"key": "inventory_alerts", "name": "تنبيهات نواقص المخزن والحد الأدنى", "default": True},
            {"key": "purchases", "name": "فواتير المشتريات وحسابات الموردين", "default": True},
            {"key": "sales_invoices", "name": "فواتير المبيعات وضريبة القيمة المضافة", "default": True},
            {"key": "customer_debts", "name": "حسابات وديون العملاء والآجل", "default": True},
            {"key": "whatsapp_receipts", "name": "إرسال الفواتير وسندات القبض عبر واتساب", "default": True},
            {"key": "expenses", "name": "المصروفات النثرية وسندات الصرف", "default": True},
            {"key": "reports", "name": "تقارير الأرباح والمبيعات والجرد", "default": True},
            {"key": "multi_branch", "name": "الفروع والمخازن المتعددة", "default": False}
        ]
    },
    "systemize_clinic": {
        "id": "systemize_clinic",
        "name": "Systemize Clinic OS",
        "arabic_name": "نظام العيادات والمراكز الطبية التخصصية",
        "icon": "fa-stethoscope",
        "badge_color": "violet",
        "repo_url": "https://github.com/mostafa-donia/systemize_clinic",
        "branch": "main",
        "current_version": "v1.0",
        "updates_allowed": True,
        "default_demo_days": 7,
        "features": [
            {"key": "patient_records", "name": "السجلات والملفات الطبية للمرضى", "default": True},
            {"key": "appointments_calendar", "name": "جدول الحجوزات والمواعيد اليومية", "default": True},
            {"key": "prescriptions", "name": "الروشتات الطبية الإلكترونية والجرعات", "default": True},
            {"key": "doctor_commissions", "name": "حساب نسب وعمولات الأطباء", "default": True},
            {"key": "whatsapp_reminders", "name": "تذكير المرضى بمواعيد الكشف آلياً", "default": True},
            {"key": "billing_invoices", "name": "فواتير الكشف والخدمات وسندات القبض", "default": True},
            {"key": "reports", "name": "التقارير المالية والطبية الشاملة", "default": True}
        ]
    }
}


def load_products_data() -> dict:
    """Loads products catalog from JSON file."""
    if not os.path.exists(PRODUCTS_FILE):
        data = {"products": DEFAULT_PRODUCTS}
        save_products_data(data)
        return data

    try:
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "products" not in data or not data["products"]:
                data["products"] = DEFAULT_PRODUCTS
            return data
    except Exception:
        return {"products": DEFAULT_PRODUCTS}


def save_products_data(data: dict):
    """Saves products catalog safely."""
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==========================================
# CLIENTS DATA & REPOSITORY
# ==========================================

def load_clients_data() -> dict:
    """Loads clients data from JSON file with migration to multi-product attributes."""
    if not os.path.exists(CLIENTS_FILE):
        initial_data = {
            "clients": {},
            "default_demo_days": 7,
            "system_announcement": "",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        save_clients_data(initial_data)
        return initial_data

    try:
        with open(CLIENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "clients" not in data:
                data["clients"] = {}

            # Backwards compatibility defaults
            for hwid, c in data["clients"].items():
                if "product_id" not in c:
                    c["product_id"] = "systemize_gym"
                if "allow_updates" not in c:
                    c["allow_updates"] = True
                if "is_paused" not in c:
                    c["is_paused"] = (c.get("status") == "suspended")
                if "pause_message" not in c:
                    c["pause_message"] = c.get("developer_message", "")
            return data
    except Exception:
        return {"clients": {}, "default_demo_days": 7, "system_announcement": ""}


def save_clients_data(data: dict):
    """Saves clients data and syncs with parent sample_central_control.json."""
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(CLIENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Sync with root sample file
    root_sample = os.path.join(PARENT_DIR, "sample_central_control.json")
    try:
        with open(root_sample, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


@app.route("/")
def index():
    """Main Dashboard View."""
    return render_template("dashboard.html")


# ==========================================
# PRODUCTS API ENDPOINTS
# ==========================================

@app.route("/api/products/", methods=["GET", "POST"])
def products_api():
    """Returns all products with computed live stats or creates/updates a product."""
    prod_data = load_products_data()
    products = prod_data.get("products", {})
    clients_data = load_clients_data()
    all_clients = clients_data.get("clients", {})

    if request.method == "POST":
        req = request.get_json() or {}
        prod_id = (req.get("id") or "").strip().lower().replace(" ", "_")
        name = (req.get("name") or "").strip()
        arabic_name = (req.get("arabic_name") or name).strip()
        icon = (req.get("icon") or "fa-cube").strip()
        badge_color = (req.get("badge_color") or "emerald").strip()
        repo_url = (req.get("repo_url") or "").strip()
        branch = (req.get("branch") or "main").strip()
        current_version = (req.get("current_version") or "v1.0").strip()
        updates_allowed = bool(req.get("updates_allowed", True))
        features = req.get("features") or []

        if not prod_id or not name:
            return jsonify({"success": False, "message": "معرف المنتج واسم المنتج مطلوبان."}), 400

        products[prod_id] = {
            "id": prod_id,
            "name": name,
            "arabic_name": arabic_name,
            "icon": icon,
            "badge_color": badge_color,
            "repo_url": repo_url,
            "branch": branch,
            "current_version": current_version,
            "updates_allowed": updates_allowed,
            "features": features,
        }
        save_products_data(prod_data)
        return jsonify({"success": True, "message": f"تم حفظ المنتج '{name}' بنجاح!", "product": products[prod_id]})

    # GET: Compute stats per product
    product_list = []
    for pid, p in products.items():
        p_clients = [c for c in all_clients.values() if c.get("product_id", "systemize_gym") == pid]
        active_count = sum(1 for c in p_clients if c.get("status") == "active" and not c.get("is_paused"))
        paused_count = sum(1 for c in p_clients if c.get("status") == "suspended" or c.get("is_paused"))
        demo_count = sum(1 for c in p_clients if c.get("status") == "demo")
        expired_count = sum(1 for c in p_clients if c.get("status") == "expired")

        product_list.append({
            "id": pid,
            "name": p.get("name", pid),
            "arabic_name": p.get("arabic_name", pid),
            "icon": p.get("icon", "fa-cube"),
            "badge_color": p.get("badge_color", "emerald"),
            "repo_url": p.get("repo_url", ""),
            "branch": p.get("branch", "main"),
            "current_version": p.get("current_version", "v1.0"),
            "updates_allowed": p.get("updates_allowed", True),
            "features": p.get("features", []),
            "stats": {
                "total_clients": len(p_clients),
                "active": active_count,
                "paused": paused_count,
                "demo": demo_count,
                "expired": expired_count,
            }
        })

    return jsonify({"success": True, "products": product_list})


@app.route("/api/products/<product_id>/toggle-updates/", methods=["POST"])
def toggle_product_updates_api(product_id: str):
    """Toggles global update permission for all clients of a specific product."""
    prod_data = load_products_data()
    products = prod_data.get("products", {})
    if product_id not in products:
        return jsonify({"success": False, "message": "المنتج غير موجود."}), 404

    prod = products[product_id]
    current = prod.get("updates_allowed", True)
    req = request.get_json() or {}
    new_allowed = req.get("updates_allowed") if "updates_allowed" in req else not current

    prod["updates_allowed"] = bool(new_allowed)
    save_products_data(prod_data)

    action_text = "السماح بالتحديثات السحابية" if new_allowed else "تعطيل ومنع التحديثات"
    return jsonify({
        "success": True,
        "message": f"تم {action_text} لجميع عملاء '{prod.get('name')}' بنجاح.",
        "updates_allowed": new_allowed,
        "product_id": product_id,
    })


# ==========================================
# CLIENTS API (MULTI-PRODUCT & PAUSING)
# ==========================================

@app.route("/api/clients/", methods=["GET"])
def get_clients_api():
    """Returns all clients filtered by product_id with computed stats and update flags."""
    product_filter = request.args.get("product_id", "").strip().lower()
    data = load_clients_data()
    prod_data = load_products_data()
    products = prod_data.get("products", {})

    clients = data.get("clients", {})
    now = datetime.now(timezone.utc)

    client_list = []
    total_count = 0
    active_count = 0
    demo_count = 0
    suspended_count = 0
    expired_count = 0
    expiring_soon_count = 0

    for hwid, c in clients.items():
        client_prod = c.get("product_id", "systemize_gym")
        if product_filter and product_filter != "all" and client_prod != product_filter:
            continue

        total_count += 1
        status = c.get("status", "active")
        is_paused = bool(c.get("is_paused", status == "suspended"))
        if is_paused:
            status = "suspended"

        exp_str = c.get("valid_until")
        lic_type = c.get("license_type", "monthly")

        # Parse expiry date & calculate remaining days
        remaining_days = None
        is_expired = False
        if exp_str and exp_str != "NONE":
            try:
                exp_dt = datetime.fromisoformat(exp_str)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                diff = (exp_dt - now).total_seconds()
                remaining_days = max(0, int(diff // 86400))
                if diff <= 0:
                    is_expired = True
                    status = "expired"
                elif remaining_days <= 7:
                    expiring_soon_count += 1
            except Exception:
                pass

        if is_paused or status == "suspended":
            suspended_count += 1
        elif is_expired or status == "expired":
            expired_count += 1
        elif status == "demo":
            demo_count += 1
        elif status == "active":
            active_count += 1

        # Check effective updates permission
        prod_obj = products.get(client_prod, {})
        prod_updates = prod_obj.get("updates_allowed", True)
        client_updates = c.get("allow_updates", True)
        effective_updates = bool(prod_updates and client_updates)

        client_list.append({
            "hwid": hwid,
            "product_id": client_prod,
            "product_name": prod_obj.get("name", "Systemize OS"),
            "product_icon": prod_obj.get("icon", "fa-cube"),
            "name": c.get("name", "عميل بدون اسم"),
            "phone": c.get("phone", ""),
            "status": status,
            "is_paused": is_paused,
            "allow_updates": client_updates,
            "effective_updates_allowed": effective_updates,
            "license_type": lic_type,
            "valid_until": exp_str,
            "remaining_days": remaining_days,
            "is_expired": is_expired,
            "features": c.get("features", {}),
            "branches": c.get("branches", []),
            "managed_users": c.get("managed_users", []),
            "developer_message": c.get("developer_message", ""),
            "pause_message": c.get("pause_message", ""),
            "created_at": c.get("created_at", ""),
            "last_seen": c.get("last_seen", ""),
        })

    # Sort: paused / expiring soon first
    client_list.sort(key=lambda x: (not x["is_paused"], x["status"] != "active", x["remaining_days"] or 9999))

    return jsonify({
        "success": True,
        "clients": client_list,
        "product_id": product_filter or "all",
        "stats": {
            "total": total_count,
            "active": active_count,
            "demo": demo_count,
            "suspended": suspended_count,
            "expired": expired_count,
            "expiring_soon": expiring_soon_count,
        },
        "default_demo_days": data.get("default_demo_days", 7),
        "my_hwid": get_hardware_fingerprint(),
    })


@app.route("/api/clients/add/", methods=["POST"])
def add_client_api():
    """Adds a new client to the database under a specific product."""
    req = request.get_json() or {}
    hwid = (req.get("hwid") or "").strip().upper()
    name = (req.get("name") or "").strip()
    phone = (req.get("phone") or "").strip()
    product_id = (req.get("product_id") or "systemize_gym").strip().lower()
    duration = req.get("duration", "30")  # 7, 30, 90, 365, lifetime
    features = req.get("features") or {}
    allow_updates = bool(req.get("allow_updates", True))

    if not hwid or not name:
        return jsonify({"success": False, "message": "اسم العميل وكود الجهاز (HWID) مطلوبان."}), 400

    if not hwid.startswith("HWID-"):
        hwid = f"HWID-{hwid}"

    data = load_clients_data()
    now = datetime.now(timezone.utc)

    if duration == "7":
        lic_type = "demo"
        valid_until = (now + timedelta(days=7)).isoformat()
    elif duration == "30":
        lic_type = "monthly"
        valid_until = (now + timedelta(days=30)).isoformat()
    elif duration == "90":
        lic_type = "quarterly"
        valid_until = (now + timedelta(days=90)).isoformat()
    elif duration == "365":
        lic_type = "yearly"
        valid_until = (now + timedelta(days=365)).isoformat()
    elif duration == "lifetime":
        lic_type = "lifetime"
        valid_until = "NONE"
    else:
        try:
            custom_days = int(duration)
            lic_type = "custom"
            valid_until = (now + timedelta(days=custom_days)).isoformat()
        except Exception:
            lic_type = "monthly"
            valid_until = (now + timedelta(days=30)).isoformat()

    data["clients"][hwid] = {
        "product_id": product_id,
        "name": name,
        "phone": phone,
        "status": "active",
        "is_paused": False,
        "allow_updates": allow_updates,
        "license_type": lic_type,
        "valid_until": valid_until,
        "features": features,
        "branches": req.get("branches") or [],
        "managed_users": req.get("managed_users") or [],
        "developer_message": req.get("developer_message", "شكراً لاشتراككم في نظام Systemize."),
        "pause_message": "",
        "created_at": now.isoformat(),
        "last_seen": None,
    }

    save_clients_data(data)

    token = generate_offline_license_token(
        machine_id=hwid,
        client_name=name,
        license_type=lic_type,
        valid_until_iso=valid_until,
        features=features,
    )

    return jsonify({
        "success": True,
        "message": f"تمت إضافة العميل {name} بنجاح!",
        "token": token,
        "hwid": hwid,
    })


@app.route("/api/clients/<hwid>/pause/", methods=["POST"])
def pause_client_api(hwid: str):
    """
    Subsystem Pause & Freeze Engine:
    Instantly pauses/suspends or unpauses a client.
    When paused, client's live requests or heartbeat immediately lock screen.
    """
    hwid = hwid.strip().upper()
    req = request.get_json() or {}
    action = req.get("action")  # "pause", "resume", or toggle
    custom_msg = req.get("message", "").strip()

    data = load_clients_data()
    if hwid not in data["clients"]:
        return jsonify({"success": False, "message": "العميل غير موجود."}), 404

    client = data["clients"][hwid]
    current_paused = client.get("is_paused", client.get("status") == "suspended")

    if action == "pause":
        new_paused = True
    elif action == "resume":
        new_paused = False
    else:
        new_paused = not current_paused

    client["is_paused"] = new_paused
    client["status"] = "suspended" if new_paused else "active"

    if new_paused:
        default_pause_msg = "تم إيقاف تشغيل هذه النسخة مؤقتاً لعدم السداد. يرجى التواصل مع إدارة النظام لتسوية الحساب وإعادة التفعيل فوراً."
        client["developer_message"] = custom_msg or default_pause_msg
        client["pause_message"] = client["developer_message"]
    else:
        client["developer_message"] = "تم تفعيل وتشغيل حسابكم بنجاح. شكراً لكم."
        client["pause_message"] = ""

    save_clients_data(data)

    action_text = "تجميد وإيقاف" if new_paused else "إعادة تشغيل وتفعيل"
    return jsonify({
        "success": True,
        "message": f"تم {action_text} العميل ({client.get('name')}) بنجاح!",
        "is_paused": new_paused,
        "status": client["status"],
        "developer_message": client["developer_message"],
    })


@app.route("/api/clients/<hwid>/toggle-updates/", methods=["POST"])
def toggle_client_updates_api(hwid: str):
    """Toggles update permission (allow_updates) for a specific client."""
    hwid = hwid.strip().upper()
    req = request.get_json() or {}
    data = load_clients_data()

    if hwid not in data["clients"]:
        return jsonify({"success": False, "message": "العميل غير موجود."}), 404

    client = data["clients"][hwid]
    current = client.get("allow_updates", True)
    new_allowed = req.get("allow_updates") if "allow_updates" in req else not current

    client["allow_updates"] = bool(new_allowed)
    save_clients_data(data)

    txt = "السماح بالتحديثات" if new_allowed else "حظر وإيقاف التحديثات"
    return jsonify({
        "success": True,
        "message": f"تم {txt} للعميل ({client.get('name')}) بنجاح.",
        "allow_updates": new_allowed,
    })


@app.route("/api/clients/<hwid>/extend/", methods=["POST"])
def extend_client_api(hwid: str):
    """Extends license for a client by specified days or lifetime."""
    hwid = hwid.strip().upper()
    req = request.get_json() or {}
    days = req.get("days", 30)  # 30, 90, 365, lifetime

    data = load_clients_data()
    if hwid not in data["clients"]:
        return jsonify({"success": False, "message": "العميل غير موجود."}), 404

    client = data["clients"][hwid]
    now = datetime.now(timezone.utc)

    if str(days) == "lifetime":
        client["valid_until"] = "NONE"
        client["license_type"] = "lifetime"
    else:
        days_num = int(days)
        current_exp = client.get("valid_until")
        base_date = now
        if current_exp and current_exp != "NONE":
            try:
                exp_dt = datetime.fromisoformat(current_exp)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if exp_dt > now:
                    base_date = exp_dt
            except Exception:
                pass

        new_expiry = base_date + timedelta(days=days_num)
        client["valid_until"] = new_expiry.isoformat()
        if days_num <= 35:
            client["license_type"] = "monthly"
        elif days_num <= 100:
            client["license_type"] = "quarterly"
        else:
            client["license_type"] = "yearly"

    client["status"] = "active"
    client["is_paused"] = False
    client["developer_message"] = "تم تجديد الاشتراك بنجاح. شكراً لثقتكم بنا."
    save_clients_data(data)

    token = generate_offline_license_token(
        machine_id=hwid,
        client_name=client.get("name", ""),
        license_type=client.get("license_type", "monthly"),
        valid_until_iso=client.get("valid_until"),
        features=client.get("features"),
    )

    return jsonify({
        "success": True,
        "message": f"تم تمديد اشتراك {client.get('name')} بنجاح!",
        "valid_until": client.get("valid_until"),
        "token": token,
    })


@app.route("/api/clients/<hwid>/update/", methods=["POST"])
def update_client_api(hwid: str):
    """Updates client product, features, duration, name, phone, or status."""
    hwid = hwid.strip().upper()
    req = request.get_json() or {}
    data = load_clients_data()

    if hwid not in data["clients"]:
        return jsonify({"success": False, "message": "العميل غير موجود."}), 404

    client = data["clients"][hwid]
    if "name" in req:
        client["name"] = req["name"].strip()
    if "phone" in req:
        client["phone"] = req["phone"].strip()
    if "product_id" in req:
        client["product_id"] = req["product_id"].strip().lower()
    if "allow_updates" in req:
        client["allow_updates"] = bool(req["allow_updates"])
    if "is_paused" in req:
        client["is_paused"] = bool(req["is_paused"])
        client["status"] = "suspended" if client["is_paused"] else "active"
    if "status" in req and req["status"] in ["active", "suspended", "expired", "demo"]:
        client["status"] = req["status"]
        client["is_paused"] = (req["status"] == "suspended")
    if "developer_message" in req:
        client["developer_message"] = req["developer_message"].strip()
    if "pause_message" in req:
        client["pause_message"] = req["pause_message"].strip()

    # Features update
    if "features" in req and isinstance(req["features"], dict):
        client["features"] = req["features"]

    # Branches & Managed Users update
    if "branches" in req and isinstance(req["branches"], list):
        client["branches"] = req["branches"]
    if "managed_users" in req and isinstance(req["managed_users"], list):
        client["managed_users"] = req["managed_users"]

    # Duration / Valid Until Update
    now = datetime.now(timezone.utc)
    if "valid_until" in req:
        val = req["valid_until"]
        if val == "NONE" or val is None or val == "":
            client["valid_until"] = "NONE"
            client["license_type"] = "lifetime"
        else:
            client["valid_until"] = val
            if "license_type" in req:
                client["license_type"] = req["license_type"]
    elif "duration" in req:
        dur = str(req["duration"]).strip()
        if dur == "lifetime":
            client["valid_until"] = "NONE"
            client["license_type"] = "lifetime"
        elif dur == "7":
            client["valid_until"] = (now + timedelta(days=7)).isoformat()
            client["license_type"] = "demo"
        elif dur == "30":
            client["valid_until"] = (now + timedelta(days=30)).isoformat()
            client["license_type"] = "monthly"
        elif dur == "90":
            client["valid_until"] = (now + timedelta(days=90)).isoformat()
            client["license_type"] = "quarterly"
        elif dur == "365":
            client["valid_until"] = (now + timedelta(days=365)).isoformat()
            client["license_type"] = "yearly"
        else:
            try:
                days_int = int(dur)
                client["valid_until"] = (now + timedelta(days=days_int)).isoformat()
                client["license_type"] = "custom"
            except Exception:
                pass

    save_clients_data(data)

    fresh_token = generate_offline_license_token(
        machine_id=hwid,
        client_name=client.get("name", ""),
        license_type=client.get("license_type", "monthly"),
        valid_until_iso=client.get("valid_until"),
        features=client.get("features"),
    )

    return jsonify({
        "success": True,
        "message": f"تم تحديث بيانات وصلاحيات العميل {client.get('name')} بنجاح!",
        "client": client,
        "token": fresh_token,
    })


@app.route("/api/clients/<hwid>/token/", methods=["GET"])
def get_client_token_api(hwid: str):
    """Generates an offline signed license token for this client."""
    hwid = hwid.strip().upper()
    data = load_clients_data()

    if hwid not in data["clients"]:
        return jsonify({"success": False, "message": "العميل غير موجود."}), 404

    client = data["clients"][hwid]
    token = generate_offline_license_token(
        machine_id=hwid,
        client_name=client.get("name", ""),
        license_type=client.get("license_type", "monthly"),
        valid_until_iso=client.get("valid_until"),
        features=client.get("features"),
    )
    return jsonify({"success": True, "token": token, "client": client})


@app.route("/api/clients/<hwid>/delete/", methods=["DELETE", "POST"])
def delete_client_api(hwid: str):
    """Deletes a client from the control center."""
    hwid = hwid.strip().upper()
    data = load_clients_data()

    if hwid in data["clients"]:
        deleted_name = data["clients"][hwid].get("name", hwid)
        del data["clients"][hwid]
        save_clients_data(data)
        return jsonify({"success": True, "message": f"تم حذف العميل {deleted_name} بنجاح."})

    return jsonify({"success": False, "message": "العميل غير موجود."}), 404


@app.route("/api/clients/<hwid>/branches/", methods=["GET", "POST"])
def client_branches_api(hwid: str):
    """Adds, updates, lists, or deletes branches for a specific client."""
    hwid = hwid.strip().upper()
    data = load_clients_data()
    if hwid not in data["clients"]:
        return jsonify({"success": False, "message": "العميل غير موجود."}), 404

    client = data["clients"][hwid]
    if "branches" not in client or not isinstance(client["branches"], list):
        client["branches"] = []

    if request.method == "GET":
        return jsonify({"success": True, "branches": client["branches"]})

    req = request.get_json() or {}
    action = req.get("action", "save")
    branch_code = (req.get("code") or "").strip().upper()

    if action == "delete":
        client["branches"] = [b for b in client["branches"] if b.get("code") != branch_code]
        save_clients_data(data)
        return jsonify({"success": True, "message": "تم حذف الفرع بنجاح.", "branches": client["branches"]})

    branch_name = (req.get("name") or "").strip()
    if not branch_name or not branch_code:
        return jsonify({"success": False, "message": "اسم الفرع وكود الفرع مطلوبان."}), 400

    existing = next((b for b in client["branches"] if b.get("code") == branch_code), None)
    is_main = bool(req.get("is_main", False))

    if is_main:
        for b in client["branches"]:
            b["is_main"] = False

    if existing:
        existing["name"] = branch_name
        existing["phone"] = req.get("phone", "").strip()
        existing["address"] = req.get("address", "").strip()
        existing["manager_name"] = req.get("manager_name", "").strip()
        existing["is_main"] = is_main
        existing["is_active"] = bool(req.get("is_active", True))
    else:
        client["branches"].append({
            "code": branch_code,
            "name": branch_name,
            "phone": req.get("phone", "").strip(),
            "address": req.get("address", "").strip(),
            "manager_name": req.get("manager_name", "").strip(),
            "is_main": is_main or (len(client["branches"]) == 0),
            "is_active": True,
        })

    save_clients_data(data)
    return jsonify({"success": True, "message": f"تم حفظ الفرع '{branch_name}' بنجاح.", "branches": client["branches"]})


@app.route("/api/clients/<hwid>/users/", methods=["GET", "POST"])
def client_users_api(hwid: str):
    """Adds, updates, changes password, or deletes managed users for a specific client."""
    hwid = hwid.strip().upper()
    data = load_clients_data()
    if hwid not in data["clients"]:
        return jsonify({"success": False, "message": "العميل غير موجود."}), 404

    client = data["clients"][hwid]
    if "managed_users" not in client or not isinstance(client["managed_users"], list):
        client["managed_users"] = []

    if request.method == "GET":
        return jsonify({"success": True, "users": client["managed_users"]})

    req = request.get_json() or {}
    action = req.get("action", "save")
    username = (req.get("username") or "").strip().lower()

    if action == "delete":
        client["managed_users"] = [u for u in client["managed_users"] if u.get("username", "").lower() != username]
        save_clients_data(data)
        return jsonify({"success": True, "message": "تم حذف حساب المستخدم بنجاح.", "users": client["managed_users"]})

    if not username:
        return jsonify({"success": False, "message": "اسم المستخدم مطلوب."}), 400

    password = (req.get("password") or "").strip()
    role = req.get("role", "RECEPTION").strip().upper()
    if role not in ["OWNER", "MANAGER", "RECEPTION"]:
        role = "RECEPTION"

    branch_code = (req.get("branch_code") or "").strip().upper()
    full_name = (req.get("full_name") or "").strip()
    old_username = (req.get("old_username") or "").strip().lower()

    target_idx = None
    for i, u in enumerate(client["managed_users"]):
        u_uname = u.get("username", "").lower()
        if (old_username and u_uname == old_username) or u_uname == username:
            target_idx = i
            break

    user_entry = {
        "username": username,
        "role": role,
        "branch_code": branch_code if role != "OWNER" else "",
        "full_name": full_name or username,
    }
    if password:
        user_entry["password"] = password

    if target_idx is not None:
        if not password and "password" in client["managed_users"][target_idx]:
            user_entry["password"] = client["managed_users"][target_idx]["password"]
        client["managed_users"][target_idx] = user_entry
    else:
        if not password:
            return jsonify({"success": False, "message": "كلمة المرور مطلوبة لإنشاء مستخدم جديد."}), 400
        client["managed_users"].append(user_entry)

    save_clients_data(data)
    return jsonify({
        "success": True,
        "message": f"تم حفظ المستخدم '{username}' وتحديث كلمة المرور والصلاحيات بنجاح.",
        "users": client["managed_users"],
    })


@app.route("/api/license/sync/", methods=["GET", "POST"])
@app.route("/api/clients.json", methods=["GET"])
def live_sync_endpoint():
    """
    Live Remote Sync Endpoint:
    Called automatically by client software installations across all products.
    """
    hwid = request.args.get("hwid", "").strip().upper()
    data = load_clients_data()
    prod_data = load_products_data()
    products = prod_data.get("products", {})

    # If specific HWID requested, return client's live payload
    if hwid and hwid in data.get("clients", {}):
        client = data["clients"][hwid]
        client["last_seen"] = datetime.now(timezone.utc).isoformat()
        save_clients_data(data)

        # Check effective updates permission
        prod_id = client.get("product_id", "systemize_gym")
        prod_obj = products.get(prod_id, {})
        prod_updates = prod_obj.get("updates_allowed", True)
        client_updates = client.get("allow_updates", True)
        effective_updates = bool(prod_updates and client_updates)

        is_paused = bool(client.get("is_paused", client.get("status") == "suspended"))
        effective_status = "suspended" if is_paused else client.get("status", "active")

        resp = dict(client)
        resp["status"] = effective_status
        resp["is_paused"] = is_paused
        resp["updates_allowed"] = effective_updates
        if not effective_updates:
            resp["update_block_reason"] = "تم قفل التحديثات لهذه النسخة بقرار من إدارة النظام السحابية."
        resp["product_info"] = {
            "id": prod_id,
            "name": prod_obj.get("name", "Systemize OS"),
            "current_version": prod_obj.get("current_version", "v2.0"),
        }
        return jsonify(resp)

    # Return full clients map
    return jsonify(data)


# ==========================================
# CRM LEADS & SALES PIPELINE ENDPOINTS
# ==========================================
import crm_service


@app.route("/api/crm/leads/", methods=["GET"])
def get_crm_leads_api():
    """Returns CRM leads, stats, and follow-up alerts scoped by product_id."""
    product_id = request.args.get("product_id", "").strip().lower()
    try:
        data = crm_service.load_crm_data()
        result = crm_service.calculate_followup_stats(data.get("leads", {}), product_id=product_id)
        return jsonify({
            "success": True,
            "leads": result["leads"],
            "stats": result["stats"],
            "templates": data.get("templates", crm_service.DEFAULT_TEMPLATES),
            "product_id": product_id or "all"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/crm/leads/save/", methods=["POST"])
def save_crm_lead_api():
    """Adds or updates a CRM lead with product tagging."""
    req = request.get_json() or {}
    try:
        res = crm_service.add_or_update_lead(req)
        return jsonify({"success": True, "lead_id": res["lead_id"], "lead": res["lead"], "is_new": res["is_new"]})
    except ValueError as ve:
        return jsonify({"success": False, "message": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/crm/leads/followup/", methods=["POST"])
def record_lead_followup_api():
    """Records interaction note and schedules next follow-up."""
    req = request.get_json() or {}
    lead_id = req.get("lead_id")
    note = req.get("note", "").strip()
    next_days = req.get("next_days")
    new_status = req.get("status")

    if not lead_id:
        return jsonify({"success": False, "message": "معرف العميل مطلوب."}), 400

    try:
        days_val = int(next_days) if next_days is not None and str(next_days).isdigit() else None
        res = crm_service.record_followup_call(lead_id, note, days_val, new_status)
        return jsonify({"success": True, "lead": res["lead"]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/crm/leads/delete/", methods=["POST"])
def delete_crm_lead_api():
    """Deletes a lead from CRM."""
    req = request.get_json() or {}
    lead_id = req.get("lead_id")
    if not lead_id:
        return jsonify({"success": False, "message": "معرف العميل مطلوب."}), 400
    success = crm_service.delete_lead(lead_id)
    return jsonify({"success": success})


@app.route("/api/crm/leads/import/", methods=["POST"])
def import_crm_leads_api():
    """
    Imports potential customers (leads) from uploaded file (.xlsx, .csv, .json, .txt)
    or from JSON payload rows.
    """
    product_id = request.form.get("product_id") or "systemize_restaurant"
    default_status = request.form.get("default_status") or "new"
    records = []

    # Check if file uploaded
    if "file" in request.files and request.files["file"].filename:
        f = request.files["file"]
        filename = f.filename.lower()
        try:
            if filename.endswith(".xlsx") or filename.endswith(".xls"):
                import pandas as pd
                df = pd.read_excel(f)
                records = df.fillna("").to_dict(orient="records")
            elif filename.endswith(".csv"):
                import pandas as pd
                try:
                    df = pd.read_csv(f, encoding="utf-8")
                except Exception:
                    f.seek(0)
                    df = pd.read_csv(f, encoding="cp1256")
                records = df.fillna("").to_dict(orient="records")
            elif filename.endswith(".json"):
                records = json.loads(f.read().decode("utf-8"))
                if isinstance(records, dict):
                    records = records.get("leads") or records.get("customers") or [records]
            elif filename.endswith(".txt"):
                content = f.read().decode("utf-8", errors="replace")
                for line in content.splitlines():
                    parts = [p.strip() for p in line.replace(",", "\t").split("\t") if p.strip()]
                    if len(parts) >= 2:
                        records.append({"business_name": parts[0], "phone": parts[1]})
                    elif len(parts) == 1:
                        records.append({"business_name": parts[0], "phone": ""})
        except Exception as e:
            return jsonify({"success": False, "message": f"فشل قراءة الملف: {str(e)}"}), 400
    elif request.is_json:
        data = request.get_json(silent=True) or {}
        records = data.get("records") or data.get("leads") or []
        product_id = data.get("product_id") or product_id
        default_status = data.get("default_status") or default_status

    if not records:
        return jsonify({"success": False, "message": "لم يتم العثور على أي سجلات عملاء صالحة في الملف أو الطلب."}), 400

    result = crm_service.import_leads_bulk(
        records,
        product_id=product_id,
        default_status=default_status
    )
    return jsonify(result)


@app.route("/api/crm/whatsapp/send/", methods=["POST"])
def send_crm_whatsapp_api():
    """Sends WhatsApp message to lead via Desktop Automation or web link."""
    req = request.get_json() or {}
    lead_id = req.get("lead_id")
    message = req.get("message", "").strip()
    auto_desktop = bool(req.get("auto_desktop", False))

    if not lead_id or not message:
        return jsonify({"success": False, "message": "معرف العميل ونص الرسالة مطلوبان."}), 400

    try:
        res = crm_service.send_whatsapp_to_lead(lead_id, message, auto_desktop=auto_desktop)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/crm/whatsapp/bulk/", methods=["POST"])
def bulk_crm_whatsapp_api():
    """Starts background automated WhatsApp campaign to multiple leads."""
    req = request.get_json() or {}
    lead_ids = req.get("lead_ids", [])
    message = req.get("message", "").strip()
    delay = int(req.get("delay", 4))

    if not lead_ids or not message:
        return jsonify({"success": False, "message": "يرجى تحديد العملاء ونص الرسالة."}), 400

    started, msg = crm_service.start_bulk_whatsapp_campaign(lead_ids, message, delay)
    return jsonify({"success": started, "message": msg})


@app.route("/api/crm/whatsapp/status/", methods=["GET"])
def get_bulk_whatsapp_status_api():
    """Returns status of ongoing WhatsApp bulk queue."""
    return jsonify({"success": True, "status": crm_service.get_bulk_queue_status()})


@app.route("/api/crm/templates/", methods=["GET", "POST"])
def crm_templates_api():
    """Gets or updates WhatsApp message templates."""
    data = crm_service.load_crm_data()
    if request.method == "POST":
        req = request.get_json() or {}
        new_templates = req.get("templates")
        if isinstance(new_templates, list):
            data["templates"] = new_templates
            crm_service.save_crm_data(data)
            return jsonify({"success": True, "templates": data["templates"]})
        return jsonify({"success": False, "message": "بيانات القوالب غير صالحة."}), 400

    return jsonify({"success": True, "templates": data.get("templates", crm_service.DEFAULT_TEMPLATES)})


if __name__ == "__main__":
    import socket
    import threading
    import time
    import webbrowser

    default_port = int(os.environ.get("PORT", 9000))
    port = default_port

    for test_port in range(default_port, default_port + 20):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.4)
                if s.connect_ex(("127.0.0.1", test_port)) != 0:
                    port = test_port
                    break
        except Exception:
            port = test_port
            break

    url = f"http://127.0.0.1:{port}"

    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    print("\n" + "=" * 64)
    print("  SYSTEMIZE MULTI-PRODUCT COMMAND & CONTROL CENTER")
    print(f"  Dashboard Live at: {url}")
    print("=" * 64 + "\n")

    app.run(host="0.0.0.0", port=port, debug=False)
