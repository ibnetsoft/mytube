-- =============================================================
-- PRODUCTION-ONLY index procedure for AIR-0227D Worker Central Protocol
-- =============================================================
-- Why this is a separate file, not part of air_0227d_worker_central_protocol.sql:
--
-- CREATE INDEX CONCURRENTLY cannot run inside a transaction block. The main
-- migration file is a single script meant to be applied as one atomic unit
-- (tables/columns/functions/RLS/grants) and this session could not confirm
-- whether the tool that will eventually apply it in production (Supabase
-- SQL editor pasting the whole file, a migration runner, psql -f) wraps
-- the whole thing in an implicit transaction. Rather than assume it
-- doesn't (and risk a CONCURRENTLY statement failing with "cannot run
-- inside a transaction block" mid-migration), the main file uses plain
-- CREATE INDEX - safe everywhere, and fine for staging where
-- remote_render_queue is a small/fresh clone (a brief write-lock during
-- index build is a non-issue there).
--
-- Production is different: remote_render_queue is live and actively
-- written by the legacy PicadiriRemoteWorker's claim PATCH. A plain
-- CREATE INDEX there blocks writes to the table for the build's duration -
-- on a table with meaningful production row counts, this could visibly
-- stall the legacy render pipeline. Run THIS file instead, in production,
-- AFTER the main migration has been applied there (the main migration's
-- plain CREATE INDEX IF NOT EXISTS statements are idempotent no-ops if
-- these already exist under the same name - but the intended production
-- flow is: apply main migration WITHOUT its two index statements having
-- run yet is not possible since they're unconditional in that file, so in
-- practice: apply the main migration as-is in staging only; for
-- production, apply every statement in the main migration file EXCEPT the
-- two CREATE INDEX IF NOT EXISTS ones, then run this file separately).
--
-- REQUIRED: run each statement below on its own, NOT wrapped in BEGIN/COMMIT,
-- NOT pasted together with any other migration statements. If your SQL
-- client has an "autocommit" or "one statement at a time" mode, use it.
--
-- FAILURE MODE TO KNOW ABOUT: if a CREATE INDEX CONCURRENTLY run is
-- interrupted (client disconnects, statement times out, server restarts),
-- Postgres does NOT clean up after itself - it leaves an INVALID index
-- behind (visible in \d on the table, or
-- `SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;`).
-- An invalid index is silently ignored by the query planner but still
-- takes disk space and slows down writes to the table it's on - it will
-- NOT retry itself. Recovery: `DROP INDEX CONCURRENTLY IF EXISTS
-- <index_name>;` (also non-transactional, also can't be interrupted
-- safely) then re-run the CREATE INDEX CONCURRENTLY statement. Check for
-- invalid indexes after running this file, before considering it done.
-- =============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_remote_render_queue_claimable
    ON public.remote_render_queue (job_type, status, priority DESC, created_at ASC)
    WHERE status = 'pending';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_remote_render_queue_lease_expiry
    ON public.remote_render_queue (lease_expires_at)
    WHERE status = 'rendering';

-- Post-run check - both rows should be empty. If not, see the failure-mode
-- note above before doing anything else.
SELECT indexrelid::regclass AS invalid_index
FROM pg_index
WHERE NOT indisvalid
  AND indrelid = 'public.remote_render_queue'::regclass;
