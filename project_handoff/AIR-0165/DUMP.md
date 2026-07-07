# AIR-0165 Handoff Dump: Job Completion Reward Pipeline

### 1. Summary
Connected the Worker Job completion flow to the existing commission ledger. When a worker completes a job, a PENDING commission record is now safely created via a PostgreSQL RPC function ensuring full atomicity and protection against duplicate records.

### 2. Files Changed
- `migrations/air_0165a_worker_commission_support.sql` (Created)
- `auth-web/app/api/user/jobs/[jobId]/complete/route.ts` (Modified)

### 3. Migration Details
**`air_0165a_worker_commission_support.sql`**
- **Constraint Modification**: Safely dropped and recreated the `commissions_referral_level_check` constraint to allow `referral_level = 0`, signifying a direct earning by a worker.
- **Unique Partial Index**: Added `CREATE UNIQUE INDEX idx_commissions_unique_job ON public.commissions(source_id) WHERE source_type = 'JOB'` to strictly enforce idempotency.
- **RPC Creation**: Created `complete_worker_job_and_mint_commission(p_job_id, p_user_id)` which:
  - Enforces `auth.uid() = p_user_id` inside the database.
  - Places a `FOR UPDATE` lock on the `worker_jobs` row to block concurrent claims.
  - Updates the job status to `COMPLETED` and `progress = 100`.
  - Inserts the commission row directly with `source_type = 'JOB'` and `status = 'PENDING'`.

### 4. RPC Behavior
If the worker tries to complete the job twice, the RPC detects `v_job.status = 'COMPLETED'` and immediately returns a graceful success response (`Job already completed`) without attempting to insert a second commission. If another worker tries to complete a job they do not own, it raises an exception (`Forbidden: Not your job`).

### 5. Idempotency Protection
- The RPC performs a pre-flight status check (`IF v_job.status = 'COMPLETED'`).
- In extreme race conditions, the partial unique index on the `commissions` table physically prevents duplicate insertions, forcing the transaction to gracefully roll back and abort the entire duplicate operation.

### 6. Security Validation
- The frontend API (`complete/route.ts`) relies exclusively on the server-side `session.user.id`. Client inputs for `userId` or `estimated_earnings` are entirely ignored.
- The RPC pulls the reward amount dynamically from the locked row `v_job.estimated_earnings`.
- The database enforces RLS for the `commissions` table naturally.

### 7. QA Checklist Result
- [x] Active job completion creates one PENDING commission.
- [x] `referral_level = 0`, `source_type = JOB`, `amount = estimated_earnings`.
- [x] Second completion attempt returns success gracefully but does not duplicate.
- [x] Unowned job completion throws exception.
- [x] Amount extracted from DB, not client payload.
- [x] Existing withdrawal flow logic inherently sees PENDING status correctly.

### 8. Known Limitations
- The `complete` action currently only mints the direct worker's reward (`referral_level = 0`). Upline / referral propagation rules for worker jobs are not included in this sprint.
- The UI relies on standard fetches; real-time toast updates via sockets are out of scope.
