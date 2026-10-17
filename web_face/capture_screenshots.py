import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

os.chdir("D:/move/career/gym system/dist/HULK_GYM")
sys.path.insert(0, "D:/move/career/gym system/dist/HULK_GYM")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By

# 1. Prepare output folder
output_dir_1 = r"D:\move\career\gym system\results"
output_dir_2 = r"D:\move\career\gym system\web_face\results"
os.makedirs(output_dir_1, exist_ok=True)
os.makedirs(output_dir_2, exist_ok=True)

# 2. Get admin user and setup session
User = get_user_model()
admin_user = User.objects.filter(is_superuser=True).first()
if not admin_user:
    admin_user = User.objects.first()

print(f"Using user: {admin_user.username}")

session = SessionStore()
session["_auth_user_id"] = str(admin_user.pk)
session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
session["_auth_user_hash"] = admin_user.get_session_auth_hash()
session["settings_page_unlocked"] = True
session["developer_options_unlocked"] = True
session["trainers_page_unlocked"] = True
session["manager_page_unlocked"] = True
session.save()
session_key = session.session_key
print(f"Created session key: {session_key}")

# 3. Setup Edge WebDriver
options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1600,1050")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--hide-scrollbars")
options.add_argument("--log-level=3")

driver = webdriver.Edge(options=options)
driver.set_window_size(1600, 1050)

# Set initial domain to allow setting cookies
driver.get("http://127.0.0.1:8000/ping/")
driver.add_cookie({
    "name": "sessionid",
    "value": session_key,
    "path": "/",
    "domain": "127.0.0.1"
})

PAGES = [
    ("01_dashboard", "http://127.0.0.1:8000/", "الرئيسية"),
    ("02_members_list", "http://127.0.0.1:8000/members/", "قائمة المشتركين"),
    ("03_member_create", "http://127.0.0.1:8000/members/create/", "إضافة مشترك جديد"),
    ("04_member_detail", "http://127.0.0.1:8000/members/244/", "تفاصيل المشترك"),
    ("05_smart_operations", "http://127.0.0.1:8000/members/operations/", "العمليات السريعة وتجديد الاشتراكات"),
    ("06_bar_inventory", "http://127.0.0.1:8000/payments/bar/", "مخزون ومبيعات البار"),
    ("07_payments_list", "http://127.0.0.1:8000/payments/", "المدفوعات وسجل الفواتير"),
    ("08_expenses_list", "http://127.0.0.1:8000/expenses/", "المصروفات"),
    ("09_trainers_management", "http://127.0.0.1:8000/payroll/trainers/", "لوحة المدربين والكباتن"),
    ("10_payroll_runs", "http://127.0.0.1:8000/payroll/runs/", "مسيرات الرواتب"),
    ("11_trainer_assignments", "http://127.0.0.1:8000/payroll/trainer-assignments/", "إسناد المشتركين للمدربين"),
    ("12_private_training", "http://127.0.0.1:8000/payroll/private-training/", "سجلات الحصص البرايفت"),
    ("13_whatsapp_center", "http://127.0.0.1:8000/messaging/", "مركز رسائل الواتساب"),
    ("14_whatsapp_compose", "http://127.0.0.1:8000/messaging/compose/", "إرسال رسالة واتساب"),
    ("15_reports_financial", "http://127.0.0.1:8000/reports/", "التقارير المالية والإحصائيات"),
    ("16_settings", "http://127.0.0.1:8000/settings/", "الإعدادات العامة وتكامل تليجرام"),
    ("17_manager_dashboard", "http://127.0.0.1:8000/manager/", "لوحة تحكم المدير"),
    ("18_face_kiosk", "http://127.0.0.1:8000/face/kiosk/", "شاشة كشك بصمة الوجه"),
    ("19_independent_camera", "http://127.0.0.1:8000/face/camera-window/", "نافذة الكاميرا المستقلة"),
]

try:
    for filename, url, title in PAGES:
        # Re-ensure locks are open in the active session
        session["settings_page_unlocked"] = True
        session["developer_options_unlocked"] = True
        session["trainers_page_unlocked"] = True
        session["manager_page_unlocked"] = True
        session.save()

        print(f"Capturing: {filename} ({title}) -> {url}")
        driver.get(url)
        time.sleep(1.5)  # Wait for charts/DOM rendering

        # Take screenshot
        file_path_1 = os.path.join(output_dir_1, f"{filename}.png")
        file_path_2 = os.path.join(output_dir_2, f"{filename}.png")
        driver.save_screenshot(file_path_1)
        driver.save_screenshot(file_path_2)
        print(f"Saved: {file_path_1}")

    # Also capture mobile view in mobile resolution
    print("Capturing Mobile View...")
    driver.set_window_size(430, 932)
    session["settings_page_unlocked"] = True
    session["manager_page_unlocked"] = True
    session.save()
    driver.get("http://127.0.0.1:8000/mobile/")
    time.sleep(1.5)
    driver.save_screenshot(os.path.join(output_dir_1, "20_manager_mobile.png"))
    driver.save_screenshot(os.path.join(output_dir_2, "20_manager_mobile.png"))

    # Also capture login page (after logout or in incognito style)
    print("Capturing Login Page...")
    driver.set_window_size(1600, 1050)
    driver.delete_all_cookies()
    driver.get("http://127.0.0.1:8000/accounts/login/")
    time.sleep(1)
    driver.save_screenshot(os.path.join(output_dir_1, "21_login_page.png"))
    driver.save_screenshot(os.path.join(output_dir_2, "21_login_page.png"))

    print("\nALL SCREENSHOTS CAPTURED SUCCESSFULLY!")

finally:
    driver.quit()
