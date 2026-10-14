# HULK GYM — External Integration Contracts Specification

**Document Version:** 1.0.0  
**Effective Date:** 2026-10-10  

---

## 1. ESP32 Fingerprint Terminal Integration Contract

### 1.1. Protocol & Architecture Rules
- **Server:** ESP32 microcontroller running HTTP WebServer on local gym network.
- **Client:** On-premise Python/Django web application.
- **Base URL:** `http://<esp_ip>:<esp_port>` (Default: `http://192.168.1.254:80`).
- **Endpoint Structure:** Strict root paths. **Do NOT prefix with `/api/`**.
- **Transport Security & Privacy:** Minimal payload containing only authorization keys (`member_id`, `fingerprint_id`, `allowed`). Never transmit personal names, phone numbers, or monetary amounts in synchronization requests.

### 1.2. Root Endpoints Specification

#### A. Health Check: `GET /status`
- **Timeout:** 5.0 seconds (up to 2 retries on connection error).
- **Request:** Empty body.
- **Expected Success Response:**
  ```json
  {
    "success": true,
    "device": "HULK_GYM",
    "wifi": "connected",
    "fingerprint": true,
    "members": 25
  }
  ```
- **Validation Rules:**
  - `success` must be strictly `true`.
  - `device` must be strictly `"HULK_GYM"`.
  - If any condition fails, the web server reports device offline/unverified.

#### B. Full Authorization Database Push: `POST /members`
- **Timeout:** 5.0 seconds (up to 2 retries on connection error).
- **Trigger:** On server boot, member creation, payment renewal, status change, or manual sync click.
- **Request Payload:**
  ```json
  {
    "members": {
      "MEM-00001": { "fingerprint_id": 7, "allowed": true },
      "MEM-00002": { "fingerprint_id": 12, "allowed": false }
    }
  }
  ```
- **Client Constraints:**
  - Maximum 1,000 member records.
  - Omit members whose `fingerprint_id` is null or not registered.
  - `fingerprint_id` must be an integer in range `1` to `1000`.
  - `allowed` must be a strict boolean.
- **Expected Success Response:**
  ```json
  {
    "success": true,
    "members": 2
  }
  ```

#### C. Biometric Enrollment: `POST /enroll`
- **Timeout:** 90.0 seconds.
- **Automatic Retries:** **0 (Disabled)** — Retrying an in-progress hardware sensor capture risks corrupting the optical buffer.
- **Request Payload:**
  ```json
  {
    "member_id": "MEM-00003"
  }
  ```
- **Expected Success Response:**
  ```json
  {
    "success": true,
    "member_id": "MEM-00003",
    "fingerprint_id": 13
  }
  ```
- **Expected Failure Response:**
  ```json
  {
    "success": false,
    "member_id": "MEM-00003",
    "error": "enrollment_failed"
  }
  ```

#### D. Enrollment Cancellation: `POST /cancel_enroll`
- **Timeout:** 5.0 seconds.
- **Request Payload:** `{ "member_id": "MEM-00003" }`
- **Expected Response:** `{ "success": true, "member_id": "MEM-00003" }`

#### E. Biometric Template Deletion: `DELETE /fingerprint`
- **Timeout:** 5.0 seconds (up to 2 retries).
- **Request Payload:**
  ```json
  {
    "fingerprint_id": 13
  }
  ```
- **Expected Success Response:**
  ```json
  {
    "success": true,
    "fingerprint_id": 13
  }
  ```
- **Post-condition:** The web application clears `fingerprint_id` from the member record **only after** receiving `success: true`, then pushes the updated `/members` database to the terminal.

#### F. Latest Hardware Scan Query: `GET /last_scan`
- **Timeout:** 5.0 seconds.
- **Response:**
  ```json
  {
    "success": true,
    "sequence": 12,
    "fingerprint_id": 17,
    "member_id": "MEM-00001",
    "allowed": true,
    "scan_active": true
  }
  ```

#### G. Display Member on Hardware TFT: `POST /display_member`
- **Request Payload:**
  ```json
  {
    "member_id": "MEM-00001",
    "name": "إياد أحمد",
    "status": "نشط",
    "days_left": 15
  }
  ```

---

## 2. WhatsApp Notification Contract

### 2.1. Operational Model on Local Gym Host
Because WhatsApp Web runs in a local desktop browser (Chrome) on the gym host machine:
1. **Message Preparation & Staging:** Django web application saves formatted messages to `messaging_whatsappmessage` with unique `dedup_key`.
2. **Background Dispatch Worker:** Runs on the designated host machine, pulling messages from the database queue.
3. **Execution Mode:**
   - Default: Quick paste mode (`Ctrl+V`) via Windows clipboard to avoid character dropouts.
   - Fallback: Typing simulation with Arabic virtual key translation.
4. **Anti-Ban Enforcement:**
   - 20 messages per minute maximum.
   - 120 messages per hour maximum.
   - Random jitter delays (0.7s to 2.8s) between operations.

### 2.2. Message Context Variables & Formats

| Template Type | Supported Placeholders | Example Body |
|---|---|---|
| `receipt` | `{name}`, `{invoice_no}`, `{plan}`, `{paid_amount}`, `{remaining_amount}`, `{end_date}` | إيصال سداد هالك جيم\nأهلاً {name}\nتم استلام: {paid_amount} ج\nالمتبقي: {remaining_amount} ج\nتاريخ الانتهاء: {end_date} |
| `reminder_3` | `{name}`, `{end_date}`, `{days_left}` | تنبيه من HULK GYM\nأهلاً {name}\nاشتراكك ينتهي خلال 3 أيام بتاريخ {end_date}. |
| `reminder_1` | `{name}`, `{end_date}` | تنبيه من HULK GYM\nأهلاً {name}\nاشتراكك ينتهي غدًا بتاريخ {end_date}. |
| `expired` | `{name}`, `{end_date}` | تنبيه من HULK GYM\nأهلاً {name}\nاشتراكك انتهى بتاريخ: {end_date}\nنورتنا في أي وقت للتجديد! 💪 |
| `salary_statement`| `{name}`, `{period}`, `{fixed_salary}`, `{bonuses}`, `{deductions}`, `{commissions}`, `{net_salary}` | كشف راتب HULK GYM - شهر {period}\nالموظف: {name}\nالراتب الأساسي: {fixed_salary} ج\nالعمولات: {commissions} ج\nالمكافآت: {bonuses} ج\nالخصومات: {deductions} ج\nصافي المستحق: {net_salary} ج |
| `manager_report` | `{date}`, `{active_count}`, `{today_revenue}`, `{month_revenue}`, `{debt_total}` | تقرير هالك جيم اليومي\nالتاريخ: {date}\nإيراد اليوم: {today_revenue} ج\nإجمالي المتبقي: {debt_total} ج |

---

## 3. Google Contacts Cloud Synchronization Contract

### 3.1. Authentication
- Standard Google OAuth 2.0 Installed Application Flow.
- Scope: `https://www.googleapis.com/auth/contacts`.
- Credentials files: `v1/data/credentials.json` & `v1/data/token.json`.

### 3.2. People API Payload: `people().createContact`
```json
{
  "names": [
    {
      "givenName": "أحمد عبد الهادي HULK"
    }
  ],
  "phoneNumbers": [
    {
      "value": "+201029375779"
    }
  ]
}
```
- Appends gym brand suffix ("HULK") to avoid colliding with personal contacts.
- Isolates Google API calls into background task with exponential backoff on network failures. Failure to reach Google Cloud **never aborts or rolls back** local membership or payment creation.
