-- Rollback for migrations/air_0227d_worker_central_protocol.sql
-- Drops only what that migration added. Does not touch remote_render_queue
-- rows or any pre-existing columns/tables (worker_jobs, workers referenced
-- by other features, etc. are untouched - workers/worker_tokens/
-- worker_job_events/worker_idempotency_keys are wholly new tables from this
-- migration, safe to drop outright).

DROP FUNCTION IF EXISTS public.report_worker_render_job_outcome(UUID, UUID, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS public.report_worker_render_job_progress(UUID, UUID, TEXT, TEXT, INTEGER, TEXT);
DROP FUNCTION IF EXISTS public.renew_worker_render_job_lease(UUID, UUID, TEXT, INTEGER);
DROP FUNCTION IF EXISTS public.claim_worker_render_job(TEXT, TEXT, TEXT[], TEXT, INTEGER);

DROP TABLE IF EXISTS public.worker_idempotency_keys;
DROP TABLE IF EXISTS public.worker_job_events;
DROP TABLE IF EXISTS public.worker_tokens;
DROP TABLE IF EXISTS public.workers;

-- CONCURRENTLY mirrors the CREATE INDEX CONCURRENTLY used in the forward
-- migration - avoids locking remote_render_queue (a live production table)
-- during index removal too.
DROP INDEX CONCURRENTLY IF EXISTS public.idx_remote_render_queue_lease_expiry;
DROP INDEX CONCURRENTLY IF EXISTS public.idx_remote_render_queue_claimable;

ALTER TABLE public.remote_render_queue
    DROP COLUMN IF EXISTS tenant_id,
    DROP COLUMN IF EXISTS error_code,
    DROP COLUMN IF EXISTS result_reference,
    DROP COLUMN IF EXISTS attempt_number,
    DROP COLUMN IF EXISTS heartbeat_at,
    DROP COLUMN IF EXISTS lease_expires_at,
    DROP COLUMN IF EXISTS lease_acquired_at,
    DROP COLUMN IF EXISTS lease_id,
    DROP COLUMN IF EXISTS worker_instance_id,
    DROP COLUMN IF EXISTS worker_group,
    DROP COLUMN IF EXISTS worker_status,
    DROP COLUMN IF EXISTS priority,
    DROP COLUMN IF EXISTS job_type;
