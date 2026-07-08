# Referral Admin QA & Deployment Guide

This document covers the QA testing scenarios and deployment steps required for the newly implemented Admin Referral Management system.

## 1. Prerequisites (Deployment)

Because Supabase REST APIs do not natively support SQL aggregations like `SUM()` and `GROUP BY`, the Admin Dashboard and the optimized User Dashboard require the following PostgreSQL RPC functions to be deployed in the Supabase instance.

**Action Required:**
Execute the SQL script located at `docs/supabase_rpc_referral_admin.sql` in the Supabase SQL Editor.

This script creates:
1. `get_referral_user_kpi(uid)`: Returns aggregated commission statistics (pending, approved, withdrawn) for a specific user to power the User Dashboard and the Admin Tree view.
2. `get_admin_global_referral_stats()`: Returns global metrics to power the Admin Dashboard summary cards.

## 2. QA Test Scenarios

### A. Access Control (Security)
- [ ] **Non-Admin Access:** Attempt to access `/admin/referrals` using a standard user account.
  - *Expected:* HTTP 403 Forbidden page or redirect.
- [ ] **Admin Access:** Login with a configured superadmin email (e.g. `ibnetsoft@gmail.com`).
  - *Expected:* The Admin menu appears in the left sidebar under Settings/Logs, and the page loads successfully.
- [ ] **API Security:** Directly call `GET /api/admin/referrals/stats` without auth cookies or with a non-admin token.
  - *Expected:* HTTP 403 Forbidden JSON response.

### B. Global Dashboard Statistics
- [ ] **KPI Cards Verification:** Check the 4 cards at the top of the Admin page.
  - *Pending Withdrawals:* Should match the sum of pending `commission_type = 'WITHDRAWAL'` tokens.
  - *Total Paid Withdrawals:* Should match the sum of completed/paid withdrawals.
  - *Pending/Approved Commissions:* Should accurately reflect non-withdrawal commissions across all users.
  - *Note:* If the RPC is not deployed, the frontend will show `0.00` and the API will return a warning or error.

### C. Member Search
- [ ] **Search by Email/Name:** Type part of a known user's email or name and hit Search (or Enter).
  - *Expected:* Relevant users populate the Results list.
- [ ] **Search by Referral Code:** Type an exact referral code (e.g., `REF-A1B2C3D4`).
  - *Expected:* The exact match is returned.
- [ ] **Search by User ID (UUID):** Paste an exact UUID string.
  - *Expected:* Only the matching UUID is returned.

### D. User Tree & Detail Panel
- [ ] **Select a User:** Click on a user from the Search Results.
  - *Expected:* The right panel loads their details, including Tree Size, Approved Commissions, and Withdrawn amounts.
- [ ] **Tree Rendering:** Ensure the tree hierarchy displays `L1` (direct referrals) and `L2` (indirect referrals) correctly.
  - *Note:* The API utilizes safe array chunking (chunks of 300) to prevent URL length limits when fetching Level 2 members for users with massive downlines.

### E. Withdrawal Management & Audit Logging
- [ ] **List Withdrawals:** Switch to the "Withdrawals" tab.
  - *Expected:* Withdrawals populate the table. Verify the "Metadata/Wallet" column accurately displays extracted JSON from the Supabase record.
- [ ] **Approve a Withdrawal:** Click the green "Approve" button on a Pending withdrawal.
  - *Expected:* A confirmation prompt appears. Upon acceptance, the status changes to `COMPLETED` and the KPI numbers update.
- [ ] **Reject a Withdrawal:** Click the red "Reject" button.
  - *Expected:* The status changes to `REJECTED`.
- [ ] **Audit Trail Validation:** Since no explicit `audit_logs` table exists, verify that the `metadata` JSON column of the `referral_commissions` row now contains an `audit_trail` array showing the admin's email, timestamp, and action taken.

### F. Performance on Large Datasets
- [ ] **User Dashboard Load Time:** Verify the User Dashboard no longer iterates over thousands of commission rows in Python. It should hit the `get_referral_user_kpi` RPC and respond instantly.
- [ ] **Tree API Performance:** Verify the `GET /api/user/referrals/tree` API uses chunking correctly and doesn't trigger an N+1 query loop for massive L1 datasets.
