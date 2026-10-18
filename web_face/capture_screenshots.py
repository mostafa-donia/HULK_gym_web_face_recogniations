import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = r"D:\move\career\gym system\dist\Systemize"
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from apps.members.models import Member
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By

# 1. Output directories
output_dirs = [
    r"D:\move\career\gym system\results",
    r"D:\move\career\gym system\presentation\assets",
    r"D:\move\career\gym system\web_face\results",
]
for d in output_dirs:
    os.makedirs(d, exist_ok=True)

# 2. Get superuser or first user
User = get_user_model()
admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
print(f"[*] Authenticating session for user: {admin_user.username}")

session = SessionStore()
session["_auth_user_id"] = str(admin_user.pk)
session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
session["_auth_user_hash"] = admin_user.get_session_auth_hash()
session["settings_page_unlocked"] = True
session["developer_options_unlocked"] = True
session["trainers_page_unlocked"] = True
session["retention_page_unlocked"] = True
session["manager_page_unlocked"] = True
session.save()
session_key = session.session_key
print(f"[*] Session key generated: {session_key}")

# 3. Dynamic member detail URL
sample_member = Member.objects.first()
member_pk = sample_member.pk if sample_member else 1

# 4. Pages list
PAGES = [
    ("01_dashboard", "http://127.0.0.1:8000/", "الرئيسية (لوحة التحكم مع الـ 6 أزرار الضخمة)"),
    ("02_members_list", "http://127.0.0.1:8000/members/", "قائمة المشتركين"),
    ("03_member_create", "http://127.0.0.1:8000/members/create/", "إضافة مشترك جديد"),
    ("04_member_detail", f"http://127.0.0.1:8000/members/{member_pk}/", "ملف المشترك الشخصي"),
    ("05_smart_operations", "http://127.0.0.1:8000/members/operations/", "العمليات الذكية والتجديدات"),
    ("06_bar_inventory", "http://127.0.0.1:8000/payments/bar/", "مخزون ومبيعات البار"),
    ("07_payments_list", "http://127.0.0.1:8000/payments/", "سجل المدفوعات والفواتير"),
    ("08_expenses_list", "http://127.0.0.1:8000/expenses/", "سجل المصروفات"),
    ("09_trainers_management", "http://127.0.0.1:8000/payroll/trainers/", "لوحة المدربين والكباتن"),
    ("10_payroll_runs", "http://127.0.0.1:8000/payroll/runs/", "مسيرات الرواتب"),
    ("11_trainer_assignments", "http://127.0.0.1:8000/payroll/trainer-assignments/", "إسناد المتدربين للكباتن"),
    ("12_private_training", "http://127.0.0.1:8000/payroll/private-training/", "جلسات التدريب الخاص PT"),
    ("13_whatsapp_center", "http://127.0.0.1:8000/messaging/", "مركز رسائل الواتساب الآلي"),
    ("14_whatsapp_compose", "http://127.0.0.1:8000/messaging/compose/", "إنشاء رسالة واتساب مخصصة"),
    ("15_reports_financial", "http://127.0.0.1:8000/reports/", "التقرير المالي وحركة الخزينة"),
    ("16_settings", "http://127.0.0.1:8000/settings/", "الإعدادات العامة والترخيص"),
    ("17_manager_dashboard", "http://127.0.0.1:8000/manager/", "لوحة المدير التنفيذي"),
    ("18_face_kiosk", "http://127.0.0.1:8000/face/kiosk/", "شاشة كشك بصمة الوجه الفورية"),
    ("19_independent_camera", "http://127.0.0.1:8000/face/camera-window/", "نافذة الكاميرا المستقلة"),
    ("22_member_retention", "http://127.0.0.1:8000/reports/retention/", "تقرير حركة الأعضاء ونسبة الاستبقاء"),
]

# 5. Initialize Edge Headless Browser
options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1600,1050")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--hide-scrollbars")
options.add_argument("--log-level=3")

driver = webdriver.Edge(options=options)
driver.set_window_size(1600, 1050)

def save_to_all(filename):
    for d in output_dirs:
        p = os.path.join(d, f"{filename}.png")
        driver.save_screenshot(p)
    print(f"  [SAVED] {filename}.png -> {len(output_dirs)} folders")

try:
    print("[*] Setting initial session cookie...")
    driver.get("http://127.0.0.1:8000/ping/")
    driver.add_cookie({
        "name": "sessionid",
        "value": session_key,
        "path": "/",
        "domain": "127.0.0.1"
    })

    for filename, url, title in PAGES:
        # Re-ensure locks remain open
        session["settings_page_unlocked"] = True
        session["developer_options_unlocked"] = True
        session["trainers_page_unlocked"] = True
        session["retention_page_unlocked"] = True
        session["manager_page_unlocked"] = True
        session.save()

        print(f"[*] Capturing: {filename} ({title})")
        driver.get(url)
        time.sleep(1.8)  # Allow fonts, charts and DOM animations to settle
        save_to_all(filename)

    # Capture Mobile Dashboard View (Portrait)
    print("[*] Capturing 20_manager_mobile (Mobile Device Mode)...")
    driver.set_window_size(430, 932)
    session["settings_page_unlocked"] = True
    session["manager_page_unlocked"] = True
    session.save()
    driver.get("http://127.0.0.1:8000/mobile/")
    time.sleep(1.8)
    save_to_all("20_manager_mobile")

    # Capture Login Page (Clean Unauthenticated)
    print("[*] Capturing 21_login_page (Clean Login Screen)...")
    driver.set_window_size(1600, 1050)
    driver.delete_all_cookies()
    driver.get("http://127.0.0.1:8000/accounts/login/")
    time.sleep(1.5)
    save_to_all("21_login_page")

    print("\n[V] ALL SCREENSHOTS SUCCESSFULLY UPDATED WITH NEW BRANDING AND DESIGN!")

finally:
    driver.quit()
