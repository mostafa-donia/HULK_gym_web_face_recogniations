# HULK GYM — Legacy System Comprehensive Audit

**Audit Date:** 2026-10-10  
**Scope:** Complete Codebase (`v1/app.py`, `v1/esp_client.py`, `v1/whatsapp_sender.py`, `v5 esp/last/last.ino`, `v1/data/*.json`, `v1/tests/`)  
**Auditor:** Senior Software Architect & Engineering Team

---

## 1. Executive Summary & Purpose

The legacy **HULK GYM** system is an on-premise desktop management system written in Python 3.11 with PySide6 (`v1/app.py`, 9,373 lines of code). It manages member subscriptions, payments, receivables, expenses, WhatsApp notifications, Google Contacts cloud synchronization, and local network integration with an ESP32 microcontroller paired with an R307 optical fingerprint reader for access control.

The goal of this audit is to reverse engineer all existing business logic, inventory every screen and automated process, identify architectural limitations and vulnerabilities, and specify how the legacy system will be transformed into an on-premise web application (Django + SQLite/PostgreSQL + HTMX/vanilla JS) accessible across mobile phones, tablets, and laptops on the local gym network.

---

## 2. Inventory of Components & Source Code

| Component / File | Size / Lines | Technology / Dependencies | Primary Responsibility |
|---|---|---|---|
| `v1/app.py` | 419.9 KB / 9,373 lines | PySide6, Python stdlib | Main desktop UI, `Store` central engine, JSON I/O, dialogs, background threads. |
| `v1/esp_client.py` | 12.7 KB / 297 lines | `urllib` (zero external dependencies) | HTTP client contract for ESP32 fingerprint terminal. |
| `v1/whatsapp_sender.py` | 22.7 KB / 638 lines | `pyautogui`, `pygetwindow`, `pyperclip`, `Pillow`, `win32clipboard` | WhatsApp Web UI automation, anti-ban rate limiter, virtual keyboard typing. |
| `v5 esp/last/last.ino` | 60.8 KB / 3,194 lines | C++, Arduino, ESP32, LittleFS, TFT_eSPI, Adafruit_Fingerprint | Firmware for ESP32 terminal, R307 sensor, TFT display, DFPlayer sound, local offline access control. |
| `v1/data/members.json` | 254 KB / 7,942 lines | JSON | Master database of 231 members, subscription histories, balances, fingerprint IDs. |
| `v1/data/payments.json` | 46.3 KB | JSON | 84 transaction invoices (new, renewal, remaining payments). |
| `v1/data/expenses.json` | 2 bytes (empty array) | JSON | Operational expense records. |
| `v1/data/settings.json` | 1.8 KB | JSON | Plans, prices, manager mobile, dashboard password, ESP config, WhatsApp send mode. |
| `v1/data/member_permission.json` | 5.8 KB | JSON | Real-time map (`member_id: bool`) pushed to ESP32 for access authorization. |
| `v1/data/whatsapp_messages.json` | 90 bytes (active queue) | JSON | Active WhatsApp queue; backed up monthly to archive JSON files. |
| `v1/data/whatsapp_message_bank.json` | 12.8 KB | JSON | Randomized message variations per category to prevent WhatsApp spam bans. |
| `v1/data/credentials.json` & `token.json` | ~1.1 KB | Google OAuth 2.0 | Google People API credentials for syncing contacts to gym Google account. |

---

## 3. Inventory of Legacy Screens & User Actions

The legacy desktop UI is organized into stacked views within `MainWindow` (`v1/app.py:7971`):

### 3.1. Dashboard (`DashboardPage`, line 4579)
- **KPI Metrics:** Total active members, expired members, today's collected revenue, memberships expiring within 3 days.
- **Quick Action Buttons:**
  - "اشتراك جديد" (New Subscription) -> opens `AddSubscriptionPage`.
  - "تجديد اشتراك" (Renew Subscription) -> opens `UnifiedEntryPage` in renewal mode.
  - "تسجيل دخول / حضور" (Entry / Reception) -> opens `UnifiedEntryPage`.
  - "إضافة مصروف" (Add Expense) -> opens `AddExpensePage`.
- **Hardware & Queue Badges:** Real-time indicator of ESP32 connectivity and pending WhatsApp messages.

### 3.2. Unified Entry & Check-In (`UnifiedEntryPage`, line 4331)
- **Primary Function:** Fast reception search by member name, mobile phone number, or scanned barcode.
- **Auto-Completer:** Populates matching candidates dynamically.
- **Multi-candidate Modal:** If multiple members share the same phone number (e.g., family members), allows the receptionist to select the exact member.
- **Access Status Alert:** Displays green/red banner with membership end date, remaining debt, and days left.
- **Contextual Actions:** Buttons for direct Renewal, Debt Payment ("سداد متبقي"), or View Profile.

### 3.3. Members Directory (`MembersTablePage`, line 2565)
- **Filters:** All (الكل), Active (نشط), Expired (منتهي), With Fingerprint (مسجل بصمة), Without Fingerprint (بدون بصمة).
- **Search:** Case-insensitive, Arabic diacritic-tolerant search across Name, Mobile, and Member ID (`MEM-XXXXX`).
- **Data Table:** ID, Name, Mobile, Plan, Start Date, End Date, Remaining Debt, Total Paid, Fingerprint ID, Actions.
- **Row Actions:** Edit member, View Details, Add Follow-up Note, Delete Member.
- **Exporting:** Exports table directly to PDF or printable view.

### 3.4. Member Profile Details (`MemberDetailsPage`, line 3167 & `MemberDetailsDialog`, line 6419)
- **Profile Summary:** ID, Name, Mobile, Gender, Status badge, Total Paid, Outstanding Balance.
- **Subscriptions History:** Complete audit trail of every past plan, dates, paid amounts, invoice IDs.
- **Payments History:** Itemized receipts and payment methods.
- **Fingerprint Operations:**
  - "تسجيل البصمة" (Enroll): Triggers background thread `ESPOperationThread` to execute `POST /enroll`.
  - "حذف البصمة" (Delete): Prompts confirmation, executes `DELETE /fingerprint`, clears local ID upon ESP success, triggers full database push.
  - "مزامنة الصلاحيات" (Sync): Pushes member authorization state to ESP.

### 3.5. Subscription Creation & Renewal (`AddSubscriptionPage`, line 3484 & `AddSubscriptionDialog`, line 5461)
- **Plan Selection:** Dynamic dropdown populated from `settings.json` (e.g., "جلسة واحدة", "شهري شامل - كل يوم", "شهري حديد - يوم ويوم").
- **Automatic Date Calculation:**
  - Start Date: defaults to today (or day after previous subscription expiration if renewing an active member).
  - End Date: auto-calculated using plan's `duration_days` (e.g., 28 days for monthly).
- **Financial Breakdown:**
  - Base plan price.
  - Discount amount (خصم).
  - Net due amount.
  - Paid amount (المدفوع).
  - Remaining balance (المتبقي) auto-calculated: `Remaining = Net Due - Paid`.
- **Payment Method:** Dropdown (نقدي, انستاباي, فودافون كاش, تحويل بنكي, بطاقة بنكية).
- **Triggers:**
  - Saves record to `members.json` and `payments.json`.
  - Automatically queues receipt WhatsApp message.
  - Automatically queues contact to `google_contacts_pending.json`.
  - Re-generates `member_permission.json` and initiates background push to ESP32.

### 3.6. Debt Settlement (`RemainingPaymentPage`, line 3916 & `RemainingPaymentDialog`, line 6210)
- **Function:** Collecting outstanding balances from members with `current_remaining > 0`.
- **Inputs:** Amount paid now, payment method, notes.
- **Calculations:** Subtracts paid sum from member's `current_remaining`, appends to `total_paid`, logs payment with `operation_type: "remaining"`.
- **Triggers:** Queues WhatsApp payment receipt, triggers Google sync if needed.

### 3.7. Expenses Management (`AddExpensePage`, line 4173 & `AddExpenseDialog`, line 6342)
- **Fields:** Amount, Category (إيجار, معدات, فاتورة كهرباء, صيانة, مستلزمات, أخرى), Description, Date.
- **Storage:** Persisted to `data/expenses.json`.

### 3.8. Financial Audit & Management (`ManagerPage`, line 2766)
- **Date Range Filter:** Daily, monthly, or custom date picker.
- **Calculations:**
  - Total Revenues = Sum of payments within range.
  - Total Expenses = Sum of expenses within range.
  - Net Profit (صافي الربح) = Revenues - Expenses.
  - Breakdown by payment method (Cash vs. InstaPay vs. Vodafone Cash).
  - Outstanding receivables summary across all members.

### 3.9. WhatsApp Queue & Bank (`WhatsAppPage`, line 6828)
- **Tabs:** Pending (معلق), Scheduled (مجدول), Sent (مرسل), Failed (فشل).
- **Actions:** Send Now, Resend Selected, Edit Message, Clear Queue, Open Message Bank.
- **Message Bank Editor:** Allows editing message variations with placeholders (`{name}`, `{end_date}`, `{paid_amount}`, `{remaining_amount}`).

### 3.10. ESP32 Terminal Control (`FingerprintDevicePage`, line 7808)
- **Hardware Status:** Ping / `GET /status` check with Wi-Fi state, fingerprint sensor ready flag, member count.
- **Sync Actions:** Manual "مزامنة كاملة" (Full Sync) -> calls `POST /members` with minimal payload.
- **Diagnostics:** Test two-member push, toggle authorization for `MEM-00001`.

### 3.11. Settings (`SettingsPage`, line 4705)
- **Protection:** Password-protected via `PasswordDialog` (PIN `1234`).
- **Configurable Items:** Subscription plans (name, price, duration), payment methods, expense categories, manager mobile, dashboard password, daily report schedule, Google account credentials upload, ESP32 IP & Port.

---

## 4. End-to-End Operational Traces

### Trace 1: New Member Registration & Payment
```text
User Submits AddSubscriptionForm
  │
  ├──> 1. Store generates next Member ID ("MEM-00232") & Payment ID ("PAY-00085")
  ├──> 2. Member record created: status='active', current_paid=X, current_remaining=Y
  ├──> 3. Payment record written to payments.json (invoice_no="INV-00085")
  ├──> 4. Receipt message generated and added to whatsapp_messages.json
  │       (if phone not synced, status='scheduled' for +1 hour delay)
  ├──> 5. Contact {name, mobile} appended to google_contacts_pending.json
  ├──> 6. GoogleContactsQueueFlushThread triggered (background thread)
  ├──> 7. member_permission.json updated ("MEM-00232": true)
  └──> 8. ESPOperationThread triggered:
            - Validates minimal payload ({MEM-00232: {fingerprint_id: null, allowed: true}})
            - Note: members without fingerprint_id are filtered out from POST /members
```

### Trace 2: Fingerprint Enrollment
```text
User clicks "تسجيل البصمة" on MemberDetailsPage
  │
  ├──> 1. Dialog asks user to confirm enrollment for Member ID
  ├──> 2. App checks ESP status (GET /status)
  ├──> 3. Spawns ESPOperationThread -> POST /enroll { "member_id": "MEM-00232" } (timeout=90s)
  ├──> 4. ESP32 enters R307 enrollment loop:
  │       - Finger placed -> captured -> removed -> placed again -> template created
  │       - ESP assigns fingerprint_id (e.g., 9)
  │       - ESP returns { "success": true, "member_id": "MEM-00232", "fingerprint_id": 9 }
  ├──> 5. Desktop app validates fingerprint_id (integer 1-1000)
  ├──> 6. Desktop app updates member record in members.json: fingerprint_id = 9
  └──> 7. App immediately pushes full authorization database:
            POST /members { "members": { "MEM-00232": { "fingerprint_id": 9, "allowed": true }, ... } }
```

### Trace 3: Physical Fingerprint Scan & Check-in
```text
Member places finger on R307 sensor at Gym Door
  │
  ├──> 1. ESP32 searches R307 template library (local hardware match, score >= 50)
  ├──> 2. ESP32 checks its local /members LittleFS database for matched fingerprint_id
  ├──> 3. Decision MADE LOCALLY:
  │       - If allowed == true:
  │           - Green LED ON
  │           - DFPlayer plays Track 2 (or Track 4/5 if expiring in 2 or 1 days)
  │           - TFT displays "مرحباً بك" + days remaining
  │       - If allowed == false:
  │           - Red LED ON
  │           - DFPlayer plays Track 3 (Denied)
  │           - TFT displays "الاشتراك منتهي"
  └──> 4. ESP32 stores event in memory (/last_scan endpoint)
          Desktop PC polls or receives heartbeat and updates UnifiedEntry screen if active.
```

---

## 5. Architectural Risks, Limitations & Legacy Vulnerabilities

1. **Massive Monolithic File (`app.py`, 9,373 lines):**
   - Business logic, JSON storage, GUI layout, CSS styling, and threading are tangled in one file.
   - Any unhandled exception can freeze the entire desktop process.
2. **Flat JSON File Concurrency & Corruption:**
   - JSON files are written via `json.dump()`.
   - Concurrent writes or system power loss can corrupt files (missing file locking).
3. **Fragile WhatsApp Automation (`whatsapp_sender.py`):**
   - Relies on PyAutoGUI screen coordinates (e.g. `(300, 198)`), window title matching, clipboard hijacking, and mouse simulation.
   - Any user mouse movement or Chrome window shift fails the operation.
4. **Cleartext Passwords & Tokens:**
   - `settings.json` stores the dashboard password in cleartext (`"dashboard_password": "1234"`).
   - Google tokens are stored unencrypted in `data/token.json`.
5. **No Role Separation:**
   - Single password (`1234`) gives unrestricted access to financial reports, settings, and member data. No separate Assistant role exists.
6. **No Trainer Commission or Employee Payroll Structure:**
   - Existing system has no trainer entities, commission rules, bonuses, deductions, or salary slips.
