import os
import sys
import json
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify, send_file

# Add web_face to Python path to import licensing crypto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, os.path.join(PARENT_DIR, "web_face"))

from apps.core.licensing.crypto import (
    generate_offline_license_token,
    verify_offline_license_token,
)
from apps.core.licensing.hwid import get_hardware_fingerprint

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"), static_folder=os.path.join(BASE_DIR, "static"))
DATA_FILE = os.path.join(BASE_DIR, "clients.json")


def load_clients_data() -> dict:
    """Loads clients data from JSON file with initial seed if empty."""
    if not os.path.exists(DATA_FILE):
        initial_data = {
            "clients": {},
            "default_demo_days": 7,
            "system_announcement": "",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        save_clients_data(initial_data)
        return initial_data

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "clients" not in data:
                data["clients"] = {}
            return data
    except Exception:
        return {"clients": {}, "default_demo_days": 7, "system_announcement": ""}


def save_clients_data(data: dict):
    """Saves clients data and syncs with parent sample_central_control.json."""
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
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


@app.route("/api/clients/", methods=["GET"])
def get_clients_api():
    """Returns all clients with computed stats."""
    data = load_clients_data()
    clients = data.get("clients", {})
    now = datetime.now(timezone.utc)

    client_list = []
    total_count = len(clients)
    active_count = 0
    demo_count = 0
    suspended_count = 0
    expired_count = 0
    expiring_soon_count = 0

    for hwid, c in clients.items():
        status = c.get("status", "active")
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

        if status == "active" and not is_expired:
            active_count += 1
        elif status == "demo":
            demo_count += 1
        elif status == "suspended":
            suspended_count += 1
        elif status == "expired" or is_expired:
            expired_count += 1

        client_list.append({
            "hwid": hwid,
            "name": c.get("name", "عميل بدون اسم"),
            "phone": c.get("phone", ""),
            "status": status,
            "license_type": lic_type,
            "valid_until": exp_str,
            "remaining_days": remaining_days,
            "is_expired": is_expired,
            "features": c.get("features", {
                "face_recognition": True,
                "whatsapp": True,
                "telegram": True,
                "bar": True,
                "payroll": True,
            }),
            "developer_message": c.get("developer_message", ""),
            "created_at": c.get("created_at", ""),
            "last_seen": c.get("last_seen", ""),
        })

    # Sort: Expiring soon and active first
    client_list.sort(key=lambda x: (x["status"] != "active", x["remaining_days"] or 9999))

    return jsonify({
        "success": True,
        "clients": client_list,
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
    """Adds a new client to the database."""
    req = request.get_json() or {}
    hwid = (req.get("hwid") or "").strip().upper()
    name = (req.get("name") or "").strip()
    phone = (req.get("phone") or "").strip()
    duration = req.get("duration", "30")  # 7, 30, 90, 365, lifetime
    features = req.get("features") or {
        "face_recognition": True,
        "whatsapp": True,
        "telegram": True,
        "bar": True,
        "payroll": True,
    }

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
        "name": name,
        "phone": phone,
        "status": "active",
        "license_type": lic_type,
        "valid_until": valid_until,
        "features": features,
        "developer_message": req.get("developer_message", "شكراً لاشتراككم في نظام HULK GYM."),
        "created_at": now.isoformat(),
        "last_seen": None,
    }

    save_clients_data(data)

    # Also generate initial token
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
        # If client is already active and future, extend from valid_until; else from now
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


@app.route("/api/clients/<hwid>/toggle-status/", methods=["POST"])
def toggle_status_api(hwid: str):
    """Toggles client status between active and suspended."""
    hwid = hwid.strip().upper()
    req = request.get_json() or {}
    data = load_clients_data()

    if hwid not in data["clients"]:
        return jsonify({"success": False, "message": "العميل غير موجود."}), 404

    client = data["clients"][hwid]
    current = client.get("status", "active")
    new_status = "suspended" if current == "active" else "active"
    client["status"] = new_status

    if new_status == "suspended":
        msg = req.get("message") or "تم إيقاف تشغيل هذه النسخة مؤقتاً لعدم السداد. يرجى التواصل مع المطور لتسوية الحساب."
        client["developer_message"] = msg
    else:
        client["developer_message"] = "تم تفعيل حسابكم بنجاح. شكراً لكم."

    save_clients_data(data)
    action_text = "إيقاف / تعليق" if new_status == "suspended" else "إعادة تفعيل"
    return jsonify({
        "success": True,
        "message": f"تم {action_text} ترخيص {client.get('name')} بنجاح.",
        "new_status": new_status,
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


@app.route("/api/clients/<hwid>/update/", methods=["POST"])
def update_client_api(hwid: str):
    """Updates client features, name, or phone."""
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
    if "features" in req and isinstance(req["features"], dict):
        client["features"] = req["features"]
    if "developer_message" in req:
        client["developer_message"] = req["developer_message"].strip()

    save_clients_data(data)
    return jsonify({"success": True, "message": "تم تحديث بيانات العميل بنجاح."})


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


@app.route("/api/license/sync/", methods=["GET", "POST"])
@app.route("/api/clients.json", methods=["GET"])
def live_sync_endpoint():
    """
    Live Remote Sync Endpoint:
    Called by client gym systems automatically over the internet.
    """
    hwid = request.args.get("hwid", "").strip().upper()
    data = load_clients_data()

    # If specific HWID requested, update last_seen and return client's config
    if hwid and hwid in data.get("clients", {}):
        client = data["clients"][hwid]
        client["last_seen"] = datetime.now(timezone.utc).isoformat()
        save_clients_data(data)
        return jsonify(client)

    # Otherwise return full clients map
    return jsonify(data)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9000))
    print(f"\n🚀 HULK GYM DEVELOPER CONTROL CENTER RUNNING ON: http://127.0.0.1:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
