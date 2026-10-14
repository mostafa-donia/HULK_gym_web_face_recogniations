# HULK GYM — Verified Business Rules Specification

**Document Version:** 1.0.0  
**Effective Date:** 2026-10-10  
**Status:** Canonical Reference for Web System Implementation

---

## 1. Member Lifecycle & Subscription Rules

### 1.1. Status Determination
- A member's subscription status is strictly date-driven:
  $$\text{current\_status} = \begin{cases} \text{"active"} & \text{if } \text{last\_subscription\_end} \ge \text{today} \\ \text{"expired"} & \text{if } \text{last\_subscription\_end} < \text{today} \text{ or missing} \end{cases}$$
- **Single-session plans** ("جلسة واحدة"): Valid for the day of purchase only ($\text{duration\_days} = 1$).
- **Monthly plans** ("شهري شامل - كل يوم" / "شهري حديد - كل يوم"): Default duration is 28 days.
- **Alternate days plans** ("يوم ويوم"): Default duration is 14 days over the month.

### 1.2. Subscription Start Date Chaining
- When renewing an **Active** member:
  $$\text{new\_start\_date} = \text{existing\_end\_date} + 1 \text{ day}$$
  This prevents members from losing paid days when renewing prior to expiration.
- When renewing an **Expired** member:
  $$\text{new\_start\_date} = \text{today}$$
- Custom start dates can be overridden manually by authorized staff when backdating or scheduling future starts.

### 1.3. Pricing, Discounts & Debt Math
- For every subscription operation:
  $$\text{net\_due} = \text{plan\_price} - \text{discount}$$
  $$\text{new\_remaining} = \max(0, \text{net\_due} - \text{paid\_amount})$$
  $$\text{current\_remaining}_{\text{member}} = \text{current\_remaining}_{\text{previous}} + \text{new\_remaining}$$
  $$\text{total\_paid}_{\text{member}} = \text{total\_paid}_{\text{previous}} + \text{paid\_amount}$$
- When paying an outstanding balance ("سداد متبقي"):
  $$\text{current\_remaining}_{\text{member}} = \max(0, \text{current\_remaining}_{\text{previous}} - \text{amount\_paid})$$
  $$\text{total\_paid}_{\text{member}} = \text{total\_paid}_{\text{previous}} + \text{amount\_paid}$$
- All currency calculations must use **2-decimal fixed-point precision** (`Decimal(10, 2)`) to avoid binary floating-point rounding errors.

---

## 2. Hardware Access Control & ESP32 Integration Rules

### 2.1. Authorization Payload
- The Python desktop/web server is the **Master Database**.
- The ESP32 terminal is an **Independent Access Authority** running locally on the gym's Wi-Fi.
- Payloads pushed to `POST /members` must only contain:
  ```json
  {
    "members": {
      "MEM-00001": { "fingerprint_id": 7, "allowed": true },
      "MEM-00002": { "fingerprint_id": 12, "allowed": false }
    }
  }
  ```
- **Strict Data Sanitization:** Under no circumstances should member names, mobile numbers, pricing, or personal notes be sent in the `/members` payload.
- Members without a registered `fingerprint_id` are omitted from the hardware payload to conserve ESP32 RAM and LittleFS storage.
- Maximum capacity supported by the ESP contract: 1,000 active biometric records.

### 2.2. Offline Decision Integrity
- The ESP32 stores `/members.json` in local flash (`LittleFS`).
- If the desktop PC or local web server is turned off, restarted, or disconnected, the ESP32 independently queries its local database upon fingerprint scan and activates the relay/green LED or red LED/buzzer.
- When membership expires, the fingerprint template is **never deleted** from the sensor; its `allowed` status simply flips to `false`.
- Biometric template deletion occurs **only** when a manager explicitly deletes the fingerprint.

---

## 3. Trainer & Employee Payroll Rules (New Core Specification)

### 3.1. Unified Employee Model
- Employees are classified into roles: `Trainer`, `Assistant`, `Manager`.
- Each employee has a configured compensation profile:
  - Fixed Monthly Salary.
  - Eligibility for Private Training Commissions (Trainers only).
  - Bonus and deduction eligibility.

### 3.2. Exact Private-Training Commission Formula
As specified in the Business Rules update, commissions are calculated **strictly** on the private training markup, never on the entire package price:
$$\text{Private Training Markup} = \text{Package Total Price} - \text{Applicable Standard Plan Price}$$
$$\text{Commission-Eligible Amount} = \text{Private Training Markup} - \text{Allocated Private Discount}$$
$$\text{Trainer Commission} = \text{Commission-Eligible Amount} \times \text{Configured Commission Rate}$$

**Canonical Example:**
- Standard Gym Subscription: EGP 400.
- Combined Subscription + Private Package: EGP 600.
- Private Training Markup = $600 - 400 = \text{EGP } 200$.
- Trainer Commission Rate = $50\%$.
- Trainer Commission = $200 \times 0.50 = \text{\bf EGP 100}$ *(NOT EGP 300)*.

### 3.3. Multi-Client & Dynamic Commission Rates
- A trainer may train multiple clients with different negotiated rates (e.g., Client A @ 50%, Client B @ 40%).
- Rates are bound to the `TrainerClientAssignment` contract.
- Changing a rate today must not alter historical commissions calculated and approved in previous payroll cycles.

### 3.4. Mandatory Approval Workflow for Adjustments
- Adjustments (Bonuses, Deductions, Penalties) cannot be applied silently.
- Lifecycle:
  $$\text{Draft} \longrightarrow \text{Pending Approval} \longrightarrow \text{Approved} \mid \text{Rejected}$$
- **Segregation of Duties:** An Assistant or Trainer cannot approve their own bonus or deduction. Only a Manager has approval authority.
- Only adjustments in the `Approved` state for that specific payroll month are aggregated into the payroll calculation.

### 3.5. Monthly Net Payable Salary Formula
$$\text{Net Salary} = \text{Fixed Salary} + \sum \text{Approved Bonuses} + \sum \text{Eligible Commissions} - \sum \text{Approved Deductions}$$

### 3.6. Immutable Payroll Snapshots
- When the Manager clicks **"Approve Payroll"**:
  1. An immutable snapshot record (`PayrollRun` & `PayrollItem`) is created.
  2. The exact breakdown (fixed, commissions itemized by client, approved bonuses, deductions) is serialized.
  3. The approving user ID and UTC timestamp are sealed.
  4. Subsequent changes to settings or commission rates do not alter this snapshot.
  5. Any post-approval correction requires an audited adjustment in the subsequent payroll run.

---

## 4. WhatsApp Automation & Anti-Ban Rules

### 4.1. Rate Limiting Limits
- Maximum 20 messages per minute.
- Maximum 120 messages per hour.
- Enforced via a sliding time window queue.

### 4.2. Staging for Google Contacts Sync
- When a new member registers who has not yet synced to Google Contacts:
  - The WhatsApp receipt is marked with `status = "scheduled"` and deferred by **1 hour** (`send_after = now + 1 hour`).
  - This allows the background Google People API worker to sync the contact to the gym's Google account so the recipient's phone displays the contact name rather than an unknown number.
- For members already synced, receipts are queued as `pending` immediately.

### 4.3. Expiry Reminders Schedule
- 3-day reminder (`reminder_3`): Sent when `days_left == 3`.
- 1-day reminder (`reminder_1`): Sent when `days_left == 1` (skipped for single-session members).
- Expired notification (`expired`): Sent when `status == "expired"` and `end_date < today`.
- Deduplication key: `dedup_key = "{type}:{recipient_type}:{mobile}:{cycle_date}"`.
