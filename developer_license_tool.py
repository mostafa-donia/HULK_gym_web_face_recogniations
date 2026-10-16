#!/usr/bin/env python3
"""
HULK GYM — Developer Master License Generator & Control Tool
Use this tool on your developer machine to:
1. Generate cryptographically signed offline license keys (HULK-LIC-...) for clients.
2. View this machine's HWID.
3. Generate sample JSON for the Online Central Control Center.
"""
import os
import sys
import json
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add web_face to path to import licensing crypto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(BASE_DIR, "web_face")):
    sys.path.insert(0, os.path.join(BASE_DIR, "web_face"))
else:
    sys.path.insert(0, BASE_DIR)

from apps.core.licensing.hwid import get_hardware_fingerprint
from apps.core.licensing.crypto import (
    generate_offline_license_token,
    verify_offline_license_token,
)


def print_banner():
    print("=" * 65)
    print("  🏋️‍♂️ HULK GYM — DEVELOPER LICENSE & CONTROL MASTER TOOL")
    print("  🔒 Anti-Copy Hardware ID & SaaS License Generator")
    print("=" * 65)


def show_machine_hwid():
    hwid = get_hardware_fingerprint()
    print(f"\n[+] بصمة هاردوير هذا الجهاز الحالي (Current HWID):")
    print(f"    -->  \033[1;32m{hwid}\033[0m")
    print("=" * 65)


def generate_license_interactive():
    print("\n--- [1] إنشاء مفتاح ترخيص جديد لعميل (Generate License Key) ---")
    client_name = input("اسم العميل / الصالة الرياضية: ").strip() or "صالة أبطال كمال الأجسام"
    target_hwid = input("كود جهاز العميل (Target Machine HWID): ").strip()

    if not target_hwid:
        print("❌ خطأ: كود الجهاز مطلوب لربط الترخيص!")
        return

    print("\nاختر نوع ومدة الاشتراك:")
    print("  1) 7 أيام (Demo)")
    print("  2) شهر كامل (30 يوم - SaaS Monthly)")
    print("  3) 3 أشهر (90 يوم - SaaS Quarterly)")
    print("  4) سنة كاملة (365 يوم - SaaS Yearly)")
    print("  5) عدد أيام مخصص (Custom Days)")
    print("  6) شراء مدى الحياة (Lifetime License)")
    choice = input("اختيارك [1-6] (الافتراضي 2): ").strip() or "2"

    now = datetime.now(timezone.utc)
    valid_until = None
    license_type = "monthly"

    if choice == "1":
        license_type = "demo"
        valid_until = (now + timedelta(days=7)).isoformat()
    elif choice == "2":
        license_type = "monthly"
        valid_until = (now + timedelta(days=30)).isoformat()
    elif choice == "3":
        license_type = "monthly"
        valid_until = (now + timedelta(days=90)).isoformat()
    elif choice == "4":
        license_type = "yearly"
        valid_until = (now + timedelta(days=365)).isoformat()
    elif choice == "5":
        days = int(input("أدخل عدد الأيام المصرح بها: ").strip() or "30")
        license_type = "custom"
        valid_until = (now + timedelta(days=days)).isoformat()
    elif choice == "6":
        license_type = "lifetime"
        valid_until = "NONE"

    print("\nتحديد الميزات المفتوحة للعميل:")
    f_face = input("  - بصمة الوجه والكاميرا التلقائية؟ (Y/n): ").strip().lower() != "n"
    f_wa = input("  - رسائل الواتساب والتذكيرات التلقائية؟ (Y/n): ").strip().lower() != "n"
    f_tg = input("  - بوت التليجرام التفاعلي؟ (Y/n): ").strip().lower() != "n"
    f_bar = input("  - مخزون ومبيعات البار والمكملات؟ (Y/n): ").strip().lower() != "n"
    f_pay = input("  - إدارة المدربين ومسيرات الرواتب؟ (Y/n): ").strip().lower() != "n"

    features = {
        "face": f_face,
        "whatsapp": f_wa,
        "telegram": f_tg,
        "bar": f_bar,
        "payroll": f_pay,
    }

    token = generate_offline_license_token(
        machine_id=target_hwid,
        client_name=client_name,
        license_type=license_type,
        valid_until_iso=valid_until,
        features=features,
    )

    print("\n" + "=" * 65)
    print("🎉 تم توليد مفتاح الترخيص المشفر بنجاح!")
    print(f"العميل: {client_name}")
    print(f"كود الجهاز المرتبط: {target_hwid}")
    print(f"نوع الباقة: {license_type}")
    print(f"تاريخ الانتهاء: {valid_until}")
    print("-" * 65)
    print("انسخ الكود التالي وارسله للعميل عبر واتساب:")
    print(f"\n\033[1;36m{token}\033[0m\n")
    print("=" * 65)


def generate_control_center_sample():
    print("\n--- [2] توليد نموذج ملف مركز التحكم السحابي (clients.json) ---")
    sample_hwid = get_hardware_fingerprint()

    data = {
        "clients": {
            sample_hwid: {
                "name": "جيم الأبطال - فرع 1",
                "status": "active",  # active, suspended, disabled, expired
                "license_type": "monthly",
                "valid_until": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                "features": {
                    "face_recognition": True,
                    "whatsapp": True,
                    "telegram": True,
                    "bar": True,
                    "payroll": True,
                },
                "developer_message": "شكراً لاشتراككم في نظام HULK GYM. اشتراككم سارٍ بنجاح.",
            }
        },
        "default_demo_days": 7,
    }

    sample_json = json.dumps(data, ensure_ascii=False, indent=2)
    sample_file = os.path.join(BASE_DIR, "sample_central_control.json")
    with open(sample_file, "w", encoding="utf-8") as f:
        f.write(sample_json)

    print(f"✓ تم حفظ نموذج مركز التحكم في الملف: {sample_file}")
    print("\nمحتوى الملف:")
    print(sample_json)
    print("\n💡 يمكنك رفع هذا الملف إلى GitHub Gist (Secret Gist) كـ Raw URL")
    print("   أو على أي سيرفر مجاني / Supabase / JSONBin، وتعديل حالة العميل من موبايلك!")


def main():
    print_banner()
    while True:
        print("\nالقائمة الرئيسية:")
        print("  1. إنشاء مفتاح ترخيص مشفر لعميل (Offline Key)")
        print("  2. عرض بصمة هاردوير جهازي الحالي (HWID)")
        print("  3. توليد نموذج JSON لمركز التحكم السحابي (Gist/API)")
        print("  4. خروج")
        c = input("\nاختر أمراً [1-4]: ").strip()
        if c == "1":
            generate_license_interactive()
        elif c == "2":
            show_machine_hwid()
        elif c == "3":
            generate_control_center_sample()
        elif c == "4":
            print("\nوداعاً!")
            break
        else:
            print("خيار غير صحيح.")


if __name__ == "__main__":
    main()
