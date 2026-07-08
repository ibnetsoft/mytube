# AIR-0203 Handoff Dump: Fraud Detection & Risk Monitoring

### 1. Detection Rules & Triggers
A Hybrid architecture was implemented to balance real-time safety with performance:
- **Lightweight DB Triggers** (Real-time on insert):
  - `check_withdrawal_abuse`: Fires on new `REQUESTED` withdrawals.
    - Flags `CRITICAL` if amount > 5000 USD.
    - Flags `HIGH` if amount > 1000 USD.
    - Flags `CRITICAL` if frequency > 3 times within 24 hours.
  - `check_job_abuse`: Fires when a job is marked `COMPLETED`.
    - Flags `CRITICAL` if the worker has completed > 50 jobs in a 1-hour window.
- **Heavy RPC Scan** (On-Demand):
  - `admin_scan_referral_trees(admin_id)`: Analyzes the referral tree structure.
    - Flags `HIGH` if a referrer has gained > 50 direct recruits in a 24-hour window (Referral Spike).

### 2. Risk Scoring & Deduplication
- **Risk Score ENUM**: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- **Deduplication Strategy**: A functional unique index (`idx_risk_flags_dedup`) combined with `ON CONFLICT DO NOTHING` prevents overwhelming the `risk_flags` table. It ensures that a specific user can only trigger a specific `risk_type` once per hour (`date_trunc('hour', created_at)`).
- **Details Schema**: Stored as JSONB containing standardized fields: `trigger`, `value`, `threshold`, and `window`.

### 3. API & Admin Integration
- **GET /api/admin/risk-flags**: Exposes active flags. Uses custom local sorting to rank `CRITICAL` > `HIGH` > `MEDIUM` > `LOW`.
- **POST /api/admin/risk-flags/[id]/resolve**: Allows admins to mark flags as `is_resolved = true`, removing them from the active queue.
- **Dashboard UI (`/admin/dashboard`)**: Integrates real-time querying to display active risk metrics. If any `CRITICAL` risks are detected, a pulsing red alert banner immediately warns the administrator.
- **Monitoring UI (`/admin/risks`)**: Dedicated page rendering the risk table with specific color-coding (Red for CRITICAL, Orange for HIGH, etc.) and quick-action "Mark Resolved" buttons.

### 4. QA Summary
- The triggers execute strictly on their targeted tables (`withdrawal_requests`, `worker_jobs`) without employing heavy joins, preserving standard operational latency.
- The Admin UI correctly parses the ENUM weights and highlights critical flags at the top of the interface.
- Out-of-scope boundaries were respected: No auto-bans or withdrawal blockages were implemented; this remains purely a Detection & Monitoring layer.
