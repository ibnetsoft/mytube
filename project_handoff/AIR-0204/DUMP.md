# AIR-0204 Handoff Dump: Automated Risk Response System

### 1. Risk State Model
Separated the transient operational blocks from historical risk metrics:
- **`user_risk_state` Table**: Tracks three specific variables per user:
  - `risk_level` (ENUM): The historical maximum risk ever achieved by the user.
  - `is_under_review` (BOOLEAN): A flag indicating if the account currently requires admin attention.
  - `withdrawal_blocked` (BOOLEAN): An operational guard that literally blocks financial outflows.

### 2. Escalation Logic
- The `trigger_new_risk_flag` (attached to `AFTER INSERT ON risk_flags`) drives the state machine.
- It dynamically assigns boolean states (`v_under_review`, `v_blocked`) based on whether the incoming score is HIGH or CRITICAL.
- **Strict Escalation**: It updates `risk_level` using PostgreSQL's `GREATEST(v_existing.risk_level, NEW.score)`. Because ENUMs in Postgres compare ordinally, `CRITICAL` > `HIGH` > `MEDIUM` > `LOW`.
- Existing block states are explicitly preserved (`withdrawal_blocked = v_existing.withdrawal_blocked OR v_blocked`), preventing a new `LOW` risk flag from accidentally overwriting a pre-existing `CRITICAL` restriction.

### 3. Override Behavior & Audit Logging
- **Override Function**: `admin_override_user_risk(admin_id, target_user, reason)` RPC manually forces `is_under_review = false` and `withdrawal_blocked = false`.
- **Policy Enforcement**: By design, it completely ignores `risk_level`, leaving the user permanently branded with their historical maximum risk.
- **Audit Logging**: Inserts an unforgeable record into `admin_audit_logs`. The `new_state` and `previous_state` clearly capture the explicit `override_type: 'MANUAL_RELEASE'`, tracking exactly which admin authorized the release, along with their text justification.

### 4. Guard Implementation
- Refactored `public.request_withdrawal` to include a strict top-level check.
- Used `COALESCE(v_risk_state.withdrawal_blocked, false) = true` to gracefully handle the case where a user has no `user_risk_state` record (defaulting them to a safe/unblocked state).
- The original core logic regarding balance locking and double-spend prevention remains completely untouched.

### 5. QA Summary
- Fully compliant with CTO directives: Risk levels are strictly escalating, overrides are fully audited and cannot reset historical risk levels, and no core treasury flow was compromised or overwritten.
- Next steps involve adding a UI button in the Admin panel to hit the newly created `/api/admin/users/[id]/risk-override` API endpoint.
