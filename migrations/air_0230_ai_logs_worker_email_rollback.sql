-- Rollback for AIR-0230 — ai_logs.worker_email
DROP INDEX IF EXISTS idx_ai_logs_worker_email;
ALTER TABLE public.ai_logs DROP COLUMN IF EXISTS worker_email;
