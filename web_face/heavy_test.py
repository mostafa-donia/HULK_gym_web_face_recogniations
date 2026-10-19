import os
import sys
import time

# Ensure proper utf-8 console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.test import Client
from django.core.management import call_command
from apps.accounts.models import User
from apps.members.models import Member, Plan, Subscription, CheckInEvent
from apps.payments.models import Payment, PaymentMethod, PaymentOperationType, BarProduct, BarSale
from apps.expenses.models import Expense, ExpenseCategory
from apps.core.models import Branch, GymProfile, SystemLicense

passed_tests = 0
failed_tests = 0

def test_case(name, condition, error_detail=""):
    global passed_tests, failed_tests
    if condition:
        print(f"  [PASS] {name}")
        passed_tests += 1
    else:
        print(f"  [FAIL] {name} -> {error_detail}")
        failed_tests += 1

def main():
    global passed_tests, failed_tests
    start_time = time.time()
    print("=" * 70)
    print("   SYSTEMIZE GYM OS - HEAVY AUTOMATED VERIFICATION SUITE")
    print("=" * 70)

    # 1. System Check
    print("\n[Step 1/6] Running Django System Framework Checks...")
    try:
        call_command("check")
        test_case("Django Core System Checks", True)
    except Exception as e:
        test_case("Django Core System Checks", False, str(e))

    # 2. Database & Data Models
    print("\n[Step 2/6] Verifying Database Records & Seed Data...")
    branches_count = Branch.objects.count()
    test_case(f"Branch records exist (Found: {branches_count})", branches_count >= 1)

    members_count = Member.objects.count()
    test_case(f"Member records exist (Found: {members_count})", members_count >= 1)

    plans_count = Plan.objects.count()
    test_case(f"Subscription Plans exist (Found: {plans_count})", plans_count >= 1)

    profile = GymProfile.get_solo()
    test_case(f"Gym Profile exists ({profile.gym_name})", bool(profile.gym_name))

    lic = SystemLicense.objects.first()
    test_case(f"License exists (Status: {lic.status if lic else 'None'})", lic is not None)

    # 3. Unauthenticated Access & Anonymous User Behavior
    print("\n[Step 3/6] Testing Anonymous / Login Security...")
    client = Client()

    res = client.get("/accounts/login/")
    test_case("Login page loads with status 200", res.status_code == 200)
    test_case("Login page contains Systemize branding", "Systemize" in res.content.decode("utf-8", errors="ignore"))
    # Verify no template variable crash for anonymous user
    test_case("No crash on branch_name for anonymous user", "VariableDoesNotExist" not in res.content.decode("utf-8", errors="ignore"))

    res = client.get("/", follow=False)
    test_case("Dashboard redirects unauthenticated user to login", res.status_code == 302 and "/accounts/login/" in res.url)

    # 4. Demo User Authentication & Full Route Coverage
    print("\n[Step 4/7] Testing Authenticated Demo User (demo / 1234)...")
    login_success = client.login(username="demo", password="1234")
    test_case("Demo user authentication succeeds", login_success)

    # Unlock manager and settings zones in session to test inner views
    session = client.session
    session["manager_page_unlocked"] = True
    session["settings_page_unlocked"] = True
    session.save()

    demo_urls = [
        ("Dashboard (/) ", "/"),
        ("Mobile Dashboard (/mobile/)", "/mobile/"),
        ("Manager Dashboard (/manager/)", "/manager/"),
        ("Member List (/members/)", "/members/"),
        ("Member List Active Filter (/members/?status=active)", "/members/?status=active"),
        ("Member List Expired Filter (/members/?status=expired)", "/members/?status=expired"),
        ("Smart Operations (/members/operations/)", "/members/operations/"),
        ("Member Create Form (/members/create/)", "/members/create/"),
        ("Face Kiosk (/face/kiosk/)", "/face/kiosk/"),
        ("Independent Camera Window (/face/camera-window/)", "/face/camera-window/"),
        ("Payments List (/payments/)", "/payments/"),
        ("Bar POS (/payments/bar/)", "/payments/bar/"),
        ("Expenses List (/expenses/)", "/expenses/"),
        ("Trainers Index (/payroll/trainers/)", "/payroll/trainers/"),
        ("Employees List (/payroll/employees/)", "/payroll/employees/"),
        ("Payroll Runs (/payroll/runs/)", "/payroll/runs/"),
        ("Trainer Assignments (/payroll/trainer-assignments/)", "/payroll/trainer-assignments/"),
        ("WhatsApp Queue (/messaging/)", "/messaging/"),
        ("WhatsApp Compose (/messaging/compose/)", "/messaging/compose/"),
        ("WhatsApp Message Bank (/messaging/message-bank/)", "/messaging/message-bank/"),
        ("Financial Report (/reports/)", "/reports/"),
        ("Member Retention Report (/reports/retention/)", "/reports/retention/"),
        ("Settings Page (/settings/)", "/settings/"),
    ]

    for label, url in demo_urls:
        try:
            r = client.get(url)
            test_case(f"Route: {label} -> {r.status_code}", r.status_code == 200, f"Got status {r.status_code}")
        except Exception as e:
            test_case(f"Route: {label}", False, str(e))

    # Test dynamic routes with actual IDs
    first_member = Member.objects.first()
    if first_member:
        try:
            r = client.get(f"/members/{first_member.id}/")
            test_case(f"Member Detail (/members/{first_member.id}/) -> {r.status_code}", r.status_code == 200)
            r = client.get(f"/members/{first_member.id}/edit/")
            test_case(f"Member Edit (/members/{first_member.id}/edit/) -> {r.status_code}", r.status_code == 200)
        except Exception as e:
            test_case("Member Detail/Edit", False, str(e))

    first_payment = Payment.objects.first()
    if first_payment:
        try:
            r = client.get(f"/payments/{first_payment.id}/")
            test_case(f"Payment Detail (/payments/{first_payment.id}/) -> {r.status_code}", r.status_code == 200)
        except Exception as e:
            test_case("Payment Detail", False, str(e))

    # Test Branch Switcher
    try:
        r = client.get("/accounts/switch-branch/all/", follow=True)
        test_case("Switch branch to 'All' succeeds", r.status_code == 200)
        first_branch = Branch.objects.first()
        if first_branch:
            r = client.get(f"/accounts/switch-branch/{first_branch.id}/", follow=True)
            test_case(f"Switch branch to '{first_branch.name}' succeeds", r.status_code == 200)
    except Exception as e:
        test_case("Branch Switcher", False, str(e))

    # 5. Admin Authentication (admin / 1234)
    print("\n[Step 5/7] Testing Authenticated Admin Superuser (admin / 1234)...")
    admin_client = Client()
    admin_login = admin_client.login(username="admin", password="1234")
    if not admin_login:
        admin_login = admin_client.login(username="admin", password="admin123456")
    test_case("Admin superuser authentication succeeds", admin_login)
    r = admin_client.get("/")
    test_case("Admin access to Dashboard -> 200", r.status_code == 200)
    r = admin_client.get("/settings/")
    test_case("Admin access to Settings Gate -> 200", r.status_code == 200)
    s = admin_client.session
    s["settings_page_unlocked"] = True
    s.save()
    r = admin_client.get("/settings/")
    test_case("Admin access to Unlocked Settings Template -> 200", r.status_code == 200)
    r = admin_client.get("/admin/")
    test_case("Admin access to Django Admin (/admin/) -> 200 or 302", r.status_code in [200, 302])

    # 6. APIs and JSON Endpoints
    print("\n[Step 6/7] Testing Core APIs & AJAX Endpoints...")
    try:
        r = client.get("/quick-search/?q=ا")
        test_case("Quick Search API returns 200", r.status_code == 200)
    except Exception as e:
        test_case("Quick Search API", False, str(e))

    try:
        r = client.get("/license/status/")
        test_case("License Status API returns 200", r.status_code == 200)
        test_case("License Status is JSON", "application/json" in r.headers.get("Content-Type", ""))
    except Exception as e:
        test_case("License Status API", False, str(e))

    try:
        r = client.get("/face/recent-checkins/")
        test_case("Recent Checkins API returns 200", r.status_code == 200)
    except Exception as e:
        test_case("Recent Checkins API", False, str(e))

    # 7. Operational CRUD & Data Integrity Verification
    print("\n[Step 7/7] Verifying Data Integrity with Temporary Transaction...")
    try:
        # Clean up any leftover test member
        Member.objects.filter(member_id__startswith="M-TEST-").delete()

        # Create a test member
        test_branch = Branch.objects.first()
        test_mid = f"M-TEST-{int(time.time())}"
        m = Member.objects.create(
            branch=test_branch,
            member_id=test_mid,
            name="Test Auto Member",
            mobile="01099999999",
            current_status="active"
        )
        test_case("Member creation transaction", m.id is not None)

        # Create a check-in event
        ci = CheckInEvent.objects.create(
            branch=test_branch,
            member=m,
            method="face",
            confidence=0.95,
            status_snapshot="active",
            days_left_snapshot=30
        )
        test_case("Check-in event creation transaction", ci.id is not None)

        # Create a bar sale
        p = BarProduct.objects.first()
        if p:
            bs = BarSale.objects.create(
                sale_id=f"SALE-TEST-{int(time.time())}",
                product=p,
                branch=test_branch,
                quantity=1,
                unit_price=p.price,
                total_price=p.price,
                payment_method="نقدي",
                is_paid=True
            )
            test_case("Bar sale transaction with branch", bs.id is not None and bs.branch == test_branch)
            branch_filtered_sales = BarSale.objects.filter(branch=test_branch)
            test_case("Bar sale branch isolation query", branch_filtered_sales.filter(id=bs.id).exists())
            bs.delete()

        # Clean up test records
        ci.delete()
        m.delete()
        test_case("Clean rollback of test records", True)
    except Exception as e:
        test_case("Data Integrity Verification", False, str(e))

    elapsed = round(time.time() - start_time, 2)
    print("\n" + "=" * 70)
    print(f"   HEAVY TEST SUITE COMPLETED IN {elapsed}s")
    print(f"   PASSED: {passed_tests} | FAILED: {failed_tests}")
    print("=" * 70)

    if failed_tests > 0:
        print("\n[X] Some tests FAILED. Please review the output above.")
        sys.exit(1)
    else:
        print("\n[V] ALL TESTS PASSED WITH 100% SUCCESS RATE!")
        sys.exit(0)

if __name__ == "__main__":
    main()
