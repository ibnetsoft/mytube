# AIR-0164 Handoff Dump: Worker Job Backend API

### 1. Summary
Implemented the backend API layer for the Worker Job Center according to the CTO's approved revisions. A new generalized `worker_jobs` table was created to support arbitrary tasks (Translation, Review, Classification) independently of the Referral Commission ledger. The frontend `WorkerJobCenter.tsx` was wired up to perform real data fetching and state mutations (`Start`, `Complete`, `Cancel`), replacing the static mock data.

### 2. Files Changed
- `migrations/air_0164a_worker_jobs.sql` (Created)
- `auth-web/app/api/user/jobs/route.ts` (Created)
- `auth-web/app/api/user/jobs/[jobId]/route.ts` (Created)
- `auth-web/app/api/user/jobs/[jobId]/start/route.ts` (Created)
- `auth-web/app/api/user/jobs/[jobId]/complete/route.ts` (Created)
- `auth-web/app/api/user/jobs/[jobId]/cancel/route.ts` (Created)
- `auth-web/components/worker-dashboard/WorkerJobCenter.tsx` (Modified)
- `auth-web/components/worker-dashboard/TodayJobs.tsx` (Modified)
- `auth-web/components/worker-dashboard/ActiveJobs.tsx` (Modified)

### 3. Migration Created
**`migrations/air_0164a_worker_jobs.sql`**
Introduces the `worker_jobs` table.
- **Keys/Types**: Supports statuses (`AVAILABLE`, `ACTIVE`, `COMPLETED`, `CANCELLED`), `priority` levels, earnings, and progress tracking.
- **Indexes**: Includes individual indexes on `status`, `user_id`, `created_at`, `completed_at`, plus highly optimized composite indexes (`status, created_at`, `user_id, status, created_at`, `user_id, completed_at`) to prevent N+1 queries.
- **RLS**: Row Level Security enabled. Users can view `AVAILABLE` jobs and jobs they own. They can only mutate jobs they own or claim unassigned `AVAILABLE` jobs.

### 4. APIs Implemented
- **`GET /api/user/jobs`**: Aggregates data by querying available jobs and the user's jobs, formatting them into the exact structure expected by the frontend (mapping `snake_case` DB fields to `camelCase` props).
- **`GET /api/user/jobs/[jobId]`**: Returns specific job details, checking RLS ownership.
- **`POST /api/user/jobs/[jobId]/start`**: Claims an available job.
- **`POST /api/user/jobs/[jobId]/complete`**: Marks a job as completed. As per CTO revisions, it **DOES NOT** mint a commission ledger record yet.
- **`POST /api/user/jobs/[jobId]/cancel`**: Resets the job to `AVAILABLE` and removes ownership (`user_id = null`), returning it to the worker pool.

### 5. Race Condition Prevention
The `/start` API uses a safe atomic update pattern:
```typescript
.match({ id: jobId, status: 'AVAILABLE' })
.is('user_id', null)
```
This guarantees that if two workers try to start the same job at the exact same millisecond, only one transaction will match the condition and return success. The other will fail.

### 6. Frontend Integration
`WorkerJobCenter.tsx` was refactored from static mock imports to a dynamic `useEffect` fetch pattern.
- Child components (`TodayJobs`, `ActiveJobs`) were extended to accept `onStart`, `onComplete`, `onCancel`, and `onRefresh` prop callbacks.
- API fetch failures fall back gracefully.
- Component state refreshes automatically upon successful mutation actions.

### 7. Known Limitations & Future Work
- **Commission Minting**: Currently `complete` only updates the `worker_jobs` record. Commission payouts will be handled in a future sprint.
- **Realtime / Queue**: Fetching relies on standard HTTP polling/refresh. Realtime push via Supabase subscriptions is not implemented in this sprint.
- **Seed Data**: No seed data is included in the migration. You must manually insert jobs to test:
  ```sql
  INSERT INTO public.worker_jobs (title, type, priority, status, estimated_earnings, estimated_time) 
  VALUES ('Translate Video 123', 'Translation', 'HIGH', 'AVAILABLE', 2.50, '15m');
  ```
