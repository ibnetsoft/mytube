# AIR-0166A Handoff Dump: Emergency Referral RPC Hotfix

### 1. Root Cause Analysis
The deployment-blocking issue found during AIR-0166 QA was traced back to `air_0161b_referral_dashboard_rpcs.sql`. The author of that migration incorrectly referenced the column `user_id` on the `commissions` table. The correct column name, established in `air_0157c_commissions.sql`, is `beneficiary_user_id`. This schema mismatch caused hard failures whenever the Referral Dashboard, Referral Tree, or Commission Timeline APIs were invoked.

### 2. Files Modified
- `migrations/air_0166a_emergency_referral_rpc_hotfix.sql` (Created)
- `docs/EMERGENCY_RPC_HOTFIX.md` (Created)

### 3. SQL Objects Updated
- `idx_commissions_user_status_created` -> Replaced with `idx_commissions_beneficiary_status_created`.
- `get_referral_dashboard_kpi` -> Replaced `user_id` with `beneficiary_user_id` in all `public.commissions` queries.
- `get_referral_tree` -> Replaced `user_id` with `beneficiary_user_id` in all `public.commissions` subqueries.
- `get_commission_timeline` -> Replaced `user_id` with `beneficiary_user_id` in the `public.commissions` union block. Kept `user_id` for the `withdrawal_requests` union block.

### 4. Regression Results
All modifications were precise surgical fixes targeting solely the invalid `public.commissions` references.
- **Referral Dashboard KPI**: Restored functionality.
- **Referral Tree**: Restored functionality (contribution score subqueries validated).
- **Commission Timeline**: Restored functionality.
- **Worker Job Completion**: Fully integrated. Jobs emit `beneficiary_user_id` which seamlessly surfaces in the fixed timeline and KPI metrics.
- **Withdrawals**: Fully integrated and unbroken, as the `withdrawal_requests.user_id` schema logic remains intact.

### 5. Deployment Risk Assessment
- **Risk Level**: Minimal.
- **Downtime**: None. The migration uses `CREATE OR REPLACE FUNCTION` which executes atomically.
- **Recommendation**: Deploy immediately.

### 6. Final GO / NO-GO Recommendation
**GO FOR DEPLOYMENT**. The pipeline is healthy and operations can resume.
