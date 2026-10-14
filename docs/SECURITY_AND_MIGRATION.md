# HULK GYM — Security Architecture & Data Migration Specification

**Document Version:** 1.0.0  
**Effective Date:** 2026-10-10  

---

## 1. Security Architecture & Role-Based Access Control (RBAC)

### 1.1. User Roles & Permission Matrix

The application strictly distinguishes between two operational roles:

| Module / Operation | Manager (مدير الصالة) | Assistant (موظف الاستقبال) |
|---|---|---|
| **Member Search & Unified Entry** | Full Access | Full Access |
| **Create Member / Renew Subscription** | Full Access | Full Access |
| **Collect Payments & Outstanding Debt** | Full Access | Full Access |
| **Record Reception Expense (مستلزمات)** | Full Access | Permitted Categories Only |
| **View Individual Member Profile** | Full Access | Full Access |
| **Edit / Delete Member Record** | Full Access | Read-Only / Restricted |
| **Biometric Enrollment / Deletion** | Full Access | Full Access (reception tool) |
| **View Daily Reception Revenue** | Full Access | Current Shift Receipts Only |
| **View Net Profit & Comprehensive Audits** | **FULL ACCESS** | **DENIED (HTTP 403)** |
| **Trainer Profiles & Base Salaries** | **FULL ACCESS** | **DENIED (HTTP 403)** |
| **Private Commission Rates & Contracts** | **FULL ACCESS** | **DENIED (HTTP 403)** |
| **Propose Salary Bonus / Deduction** | Full Access | Propose Draft Only |
| **Approve Salary Adjustments** | **FULL ACCESS** | **DENIED (HTTP 403)** |
| **Calculate & Approve Payroll Runs** | **FULL ACCESS** | **DENIED (HTTP 403)** |
| **Dispatch WhatsApp Salary Statements**| **FULL ACCESS** | **DENIED (HTTP 403)** |
| **Gym Settings, Pricing & Plans** | **FULL ACCESS** | **DENIED (HTTP 403)** |
| **System Backup, Logs & User Accounts**| **FULL ACCESS** | **DENIED (HTTP 403)** |

### 1.2. Server-Side Enforcement (Defense in Depth)
- **Zero Client-Side Trust:** Hiding buttons or UI tabs does **not** constitute security. Every view and API endpoint is protected by explicit server-side role checks (`@role_required('MANAGER')` or Django permission mixins).
- **Password Security:**
  - Deprecate the legacy cleartext PIN `"1234"`.
  - Use PBKDF2 with SHA256 or Argon2 password hashing.
  - Implement brute-force throttling on login endpoints.
- **Session & Network Hardening on Gym LAN:**
  - Secure session cookies with `HttpOnly`, `SameSite=Lax`.
  - Django CSRF tokens on all POST/PUT/DELETE forms.
  - Bind development server to designated static local IP (e.g. `192.168.1.100:8000`) or standard local network interface.

### 1.3. Comprehensive Audit Trail
- All financial overrides, discounts > 10%, member deletions, salary adjustments, and payroll approvals are recorded in `AuditLog` with:
  - User ID and username.
  - Action category and target object reference.
  - Client IP address and timestamp.
  - Before/after JSON difference snapshot.

---

## 2. Legacy Data Migration Plan

### 2.1. Source Data Assets
- Source directory: `d:\move\career\gym system\v1\data\`
- Files to migrate:
  1. `members.json` (231 members, 254 KB)
  2. `payments.json` (84 payment receipts, 46.3 KB)
  3. `expenses.json` (operational expenses)
  4. `settings.json` (plans, prices, payment methods, ESP settings)
  5. `whatsapp_message_bank.json` (message templates)

### 2.2. Migration Execution Principles
1. **Immutable Source:** The legacy JSON files in `v1/data/` will remain read-only and will never be deleted, overwritten, or modified.
2. **Idempotence:** The migration script can be run multiple times safely without creating duplicate members, payments, or subscriptions.
3. **Identifier Preservation:**
   - Legacy member codes (`MEM-00001` through `MEM-00231`) will be preserved as the unique `member_id`.
   - Legacy invoice numbers (`INV-00001` through `INV-00084`) and payment IDs (`PAY-00001`) will be preserved in `Payment`.
4. **Data Normalization & Cleansing:**
   - Egyptian phone numbers will be normalized into standard 11-digit format (`010...`, `011...`, `012...`, `015...`).
   - Dates will be parsed from ISO string (`YYYY-MM-DD` and `YYYY-MM-DD HH:MM`) into timezone-aware datetime objects.
   - Financial floats will be converted into exact `Decimal` objects.

### 2.3. Reconciliation & Verification Gates

The migration script (`python manage.py migrate_legacy_data`) will automatically execute reconciliation checks and print a verification report:

```text
============================================================
           HULK GYM DATA MIGRATION RECONCILIATION
============================================================
Source: v1/data/members.json
Target: PostgreSQL / SQLite (members_member)
- Source Member Count: 231
- Migrated Member Count: 231
- Discrepancy: 0 (MATCH)

Source: v1/data/payments.json
Target: PostgreSQL / SQLite (payments_payment)
- Source Payment Count: 84
- Migrated Payment Count: 84
- Source Total Collected: EGP 22,870.00
- Migrated Total Collected: EGP 22,870.00
- Discrepancy: EGP 0.00 (MATCH)

Biometric Templates:
- Members with Fingerprint ID: 8
- Migrated with Fingerprint ID: 8
- Discrepancy: 0 (MATCH)
============================================================
MIGRATION INTEGRITY: 100% VERIFIED
============================================================
```
