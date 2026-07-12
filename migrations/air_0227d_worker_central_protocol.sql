-- =============================================================
-- Migration: AIR-0227D Worker Central Protocol
-- Extends the existing public.remote_render_queue table (already used in
-- production by the legacy PicadiriRemoteWorker via conditional PostgREST
-- PATCH, see auth-web/supabase_schema.sql:519-540) with lease-protocol
-- columns, and adds new tables for worker identity, token storage, job
-- event audit log, and idempotency keys.
--
-- Deliberately does NOT create a table named `worker_jobs` - that name is
-- already taken by an unrelated table (migrations/air_0164a_worker_jobs.sql,
-- a generic user-facing task-board feature, RLS-gated via auth.uid()). Reusing
-- remote_render_queue instead of a parallel job table keeps exactly one
-- source of truth for render jobs and lets the legacy worker and the new AIR
-- Worker coexist on the same rows (worker_group distinguishes them).
--
-- SAFETY: This file is a DRAFT for staging review. Do NOT run against the
-- production database. No statement here is destructive (ALTER TABLE ADD
-- COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS / CREATE OR REPLACE
-- FUNCTION only) but it must still go through staging verification first,
-- per AIR-0227D's explicit prohibition on unreviewed production migrations.
--
-- EXECUTION NOTE: contains CREATE INDEX CONCURRENTLY statements (to avoid
-- locking the live remote_render_queue table). CONCURRENTLY cannot run
-- inside a transaction block - run this file statement-by-statement (the
-- Supabase SQL editor and plain `psql -f` both do this by default already;
-- do NOT wrap the whole file in an explicit BEGIN/COMMIT).
-- =============================================================

-- -----------------------------------------------------------------
-- 1. Extend remote_render_queue with lease-protocol columns
-- -----------------------------------------------------------------
-- Existing `status` column (TEXT, default 'pending') stays exactly as-is
-- for legacy-worker compatibility - it has no CHECK constraint, so the new
-- 'canceled' value used below is safe to introduce without a constraint
-- migration. Fine-grained AIR Worker state lives in the new `worker_status`
-- column so the legacy worker's blind `?status=eq.pending` claim PATCH and
-- the admin UI's existing status filters never see a status value they
-- don't already understand.
ALTER TABLE public.remote_render_queue
    ADD COLUMN IF NOT EXISTS job_type            TEXT NOT NULL DEFAULT 'render_video',
    ADD COLUMN IF NOT EXISTS priority             INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS worker_status        TEXT,  -- QUEUED|CLAIMED|PREPARING|RENDERING|UPLOADING|COMPLETED|FAILED|CANCELED|ABANDONED, NULL = legacy-claimed row
    ADD COLUMN IF NOT EXISTS worker_group         TEXT,  -- 'air-worker' | 'legacy' | NULL (NULL = claimable by either)
    ADD COLUMN IF NOT EXISTS worker_instance_id   TEXT,
    ADD COLUMN IF NOT EXISTS lease_id             UUID,
    ADD COLUMN IF NOT EXISTS lease_acquired_at    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS lease_expires_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS heartbeat_at          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS attempt_number        INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS result_reference      TEXT,  -- AIR Worker's generic result pointer (e.g. Drive file id); legacy keeps using result_file_id/result_file_name
    ADD COLUMN IF NOT EXISTS error_code            TEXT,
    ADD COLUMN IF NOT EXISTS tenant_id             TEXT;

-- [AIR-0227D-VALIDATION Stage 4 static review] CONCURRENTLY - remote_render_queue
-- is a live production table; a plain CREATE INDEX takes a lock that blocks
-- writes (including the legacy worker's claim PATCH) for the build duration.
-- CONCURRENTLY avoids that at the cost of needing to run outside an explicit
-- transaction block (true by default for both the Supabase SQL editor and
-- psql running this file statement-by-statement - this file does not wrap
-- itself in BEGIN/COMMIT).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_remote_render_queue_claimable
    ON public.remote_render_queue (job_type, status, priority DESC, created_at ASC)
    WHERE status = 'pending';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_remote_render_queue_lease_expiry
    ON public.remote_render_queue (lease_expires_at)
    WHERE status = 'rendering';

-- -----------------------------------------------------------------
-- 2. workers - registry of known worker identities (not per-connection,
--    per logical worker_id; a worker reconnecting gets a new
--    worker_instance_id each run but keeps the same worker_id)
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.workers (
    worker_id           TEXT PRIMARY KEY,
    worker_group         TEXT NOT NULL DEFAULT 'air-worker',
    allowed_job_types    TEXT[] NOT NULL DEFAULT ARRAY['render_video'],
    capabilities         JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_worker_instance_id TEXT,
    last_heartbeat_at    TIMESTAMPTZ,
    registered_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by           TEXT
);

-- -----------------------------------------------------------------
-- 3. worker_tokens - token metadata only. The raw bearer token is never
--    stored; only a salted hash. See docs/AIR_WORKER_CENTRAL_API.md for the
--    verification algorithm (hash lookup + hmac-style constant-time compare
--    is not needed here since we compare hashes, not the raw secret - a
--    plain indexed equality lookup on token_hash is safe because token_hash
--    is itself a high-entropy digest, not the credential).
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.worker_tokens (
    token_id       TEXT PRIMARY KEY,           -- short public identifier, embedded in the issued bearer token so lookup doesn't require scanning all hashes
    worker_id      TEXT NOT NULL REFERENCES public.workers(worker_id) ON DELETE CASCADE,
    token_hash     TEXT NOT NULL,               -- sha256(raw_token), hex
    token_prefix   TEXT NOT NULL,               -- first 8 chars of the raw token, display-only, never enough to forge
    allowed_job_types TEXT[] NOT NULL DEFAULT ARRAY['render_video'],
    capabilities   JSONB NOT NULL DEFAULT '{}'::jsonb,
    worker_group   TEXT NOT NULL DEFAULT 'air-worker',
    issued_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMPTZ,
    revoked_at     TIMESTAMPTZ,
    last_used_at   TIMESTAMPTZ,
    created_by     TEXT
);

CREATE INDEX IF NOT EXISTS idx_worker_tokens_hash ON public.worker_tokens (token_hash);
CREATE INDEX IF NOT EXISTS idx_worker_tokens_worker ON public.worker_tokens (worker_id);

-- -----------------------------------------------------------------
-- 4. worker_job_events - append-only audit log. Never updated, only
--    inserted - this is the trail an operator reads to answer "what
--    happened to job X" without reconstructing it from remote_render_queue's
--    current-state-only columns.
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.worker_job_events (
    id                  BIGSERIAL PRIMARY KEY,
    -- [AIR-0227D-VALIDATION Stage 4 static review] ON DELETE SET NULL, not
    -- CASCADE - this is an audit log; deleting the render-queue row it
    -- describes (e.g. via the admin render-queue DELETE endpoint) must not
    -- also delete the record of what happened to it. job_id is already
    -- nullable for register/heartbeat events, so SET NULL fits the existing
    -- column semantics.
    job_id              UUID REFERENCES public.remote_render_queue(id) ON DELETE SET NULL,
    worker_id           TEXT,
    worker_instance_id  TEXT,
    event_type          TEXT NOT NULL,  -- claim | heartbeat | renew_lease | progress | complete | fail | reject_stale_lease | reject_invalid_transition | idempotent_replay | idempotent_conflict
    from_status         TEXT,
    to_status            TEXT,
    lease_id            UUID,
    detail               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_worker_job_events_job ON public.worker_job_events (job_id, created_at);

-- -----------------------------------------------------------------
-- 5. worker_idempotency_keys - dedup store for complete/fail. A second
--    request with the same (job_id, idempotency_key) but a different
--    payload is a conflict (409), not a silent replay - this is stricter
--    than the AIR-0227C local mock server (worker/dev_central_server), which
--    only ever proved worker-side retry safety and did not enforce
--    payload-match on replay. See docs/AIR_WORKER_CENTRAL_API.md Stage 10.
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.worker_idempotency_keys (
    job_id            UUID NOT NULL REFERENCES public.remote_render_queue(id) ON DELETE CASCADE,
    idempotency_key   TEXT NOT NULL,
    request_hash      TEXT NOT NULL,   -- sha256 of the normalized (endpoint, sorted-payload) tuple
    response_snapshot JSONB NOT NULL,  -- exact response body returned the first time, replayed verbatim on retry
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_id, idempotency_key)
);

-- -----------------------------------------------------------------
-- 5-A. RLS - [AIR-0227D-VALIDATION Stage 4 static review finding] the
-- original draft never actually enabled RLS on these 4 new tables (the
-- AIR-0227C sketch in AIR_WORKER_MIGRATION_PLAN.md documented the intent
-- but the SQL was never written). No policies are added - Supabase's
-- default with RLS enabled and zero policies is deny-all for `anon` and
-- `authenticated`; `service_role` bypasses RLS entirely regardless (it has
-- the BYPASSRLS role attribute), which is exactly what auth-web's server
-- code needs and exactly what nothing else should get. worker_tokens
-- especially must never be client-readable even in aggregate (token_hash
-- is sensitive even though it's not the raw credential).
-- Deliberately NOT touching remote_render_queue's own RLS status here -
-- it has no RLS enabled today (confirmed: absent from
-- auth-web/supabase_schema.sql's list of ENABLE ROW LEVEL SECURITY
-- statements) and the legacy worker's PostgREST-based claim may depend on
-- that; changing it is a separate, higher-risk decision outside this
-- migration's scope (documented as a pre-existing gap, not introduced or
-- fixed here).
ALTER TABLE public.workers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.worker_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.worker_job_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.worker_idempotency_keys ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------
-- 6. Atomic claim RPC - FOR UPDATE SKIP LOCKED, single round trip.
--    Reclaims jobs whose lease has expired (status stays 'rendering' but
--    lease_expires_at is in the past) as well as fresh 'pending' jobs.
-- -----------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_worker_render_job(
    p_worker_id TEXT,
    p_worker_instance_id TEXT,
    p_allowed_job_types TEXT[],
    p_worker_group TEXT,
    p_lease_ttl_seconds INTEGER DEFAULT 300
) RETURNS SETOF public.remote_render_queue AS $$
DECLARE
    v_job_id UUID;
    v_lease_id UUID := gen_random_uuid();
    v_from_status TEXT;
BEGIN
    SELECT id, worker_status INTO v_job_id, v_from_status
    FROM public.remote_render_queue
    WHERE job_type = ANY(p_allowed_job_types)
      AND (worker_group IS NULL OR worker_group = p_worker_group)
      AND (
            status = 'pending'
            OR (status = 'rendering' AND lease_expires_at IS NOT NULL AND lease_expires_at < NOW())
          )
    ORDER BY priority DESC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1;

    IF v_job_id IS NULL THEN
        RETURN;
    END IF;

    UPDATE public.remote_render_queue
    SET status = 'rendering',
        worker_status = 'CLAIMED',
        worker_group = p_worker_group,
        worker_id = p_worker_id,
        worker_instance_id = p_worker_instance_id,
        lease_id = v_lease_id,
        lease_acquired_at = NOW(),
        lease_expires_at = NOW() + make_interval(secs => p_lease_ttl_seconds),
        heartbeat_at = NOW(),
        claimed_at = NOW(),
        attempt_number = attempt_number + 1,
        updated_at = NOW()
    WHERE id = v_job_id;

    INSERT INTO public.worker_job_events (job_id, worker_id, worker_instance_id, event_type, from_status, to_status, lease_id)
    VALUES (v_job_id, p_worker_id, p_worker_instance_id, 'claim', COALESCE(v_from_status, 'QUEUED'), 'CLAIMED', v_lease_id);

    RETURN QUERY SELECT * FROM public.remote_render_queue WHERE id = v_job_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

-- -----------------------------------------------------------------
-- 7. Lease renewal RPC - rejects (returns no row) if the lease_id no
--    longer matches (already reassigned) or has already expired.
-- -----------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.renew_worker_render_job_lease(
    p_job_id UUID,
    p_lease_id UUID,
    p_worker_instance_id TEXT,
    p_lease_ttl_seconds INTEGER DEFAULT 300
) RETURNS SETOF public.remote_render_queue AS $$
BEGIN
    UPDATE public.remote_render_queue
    SET lease_expires_at = NOW() + make_interval(secs => p_lease_ttl_seconds),
        heartbeat_at = NOW(),
        updated_at = NOW()
    WHERE id = p_job_id
      AND lease_id = p_lease_id
      AND worker_instance_id = p_worker_instance_id
      AND status = 'rendering'
      AND lease_expires_at > NOW();

    IF FOUND THEN
        INSERT INTO public.worker_job_events (job_id, worker_instance_id, event_type, lease_id)
        VALUES (p_job_id, p_worker_instance_id, 'renew_lease', p_lease_id);
    END IF;

    RETURN QUERY SELECT * FROM public.remote_render_queue WHERE id = p_job_id AND lease_id = p_lease_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

-- -----------------------------------------------------------------
-- 8. Progress update RPC - lease-gated but not idempotency-gated (progress
--    reports are naturally idempotent - the last write wins - and are not
--    terminal state transitions, so this only enforces lease ownership).
-- -----------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.report_worker_render_job_progress(
    p_job_id UUID,
    p_lease_id UUID,
    p_worker_instance_id TEXT,
    p_worker_status TEXT,
    p_progress INTEGER,
    p_message TEXT
) RETURNS SETOF public.remote_render_queue AS $$
DECLARE
    v_from_status TEXT;
BEGIN
    SELECT worker_status INTO v_from_status FROM public.remote_render_queue
    WHERE id = p_job_id AND lease_id = p_lease_id AND worker_instance_id = p_worker_instance_id;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- Server-owned state transition table (docs/AIR_WORKER_CENTRAL_API.md).
    IF NOT (
        (v_from_status = 'CLAIMED' AND p_worker_status IN ('PREPARING', 'CLAIMED'))
        OR (v_from_status = 'PREPARING' AND p_worker_status IN ('RENDERING', 'PREPARING'))
        OR (v_from_status = 'RENDERING' AND p_worker_status IN ('UPLOADING', 'RENDERING'))
        OR (v_from_status = p_worker_status)
    ) THEN
        INSERT INTO public.worker_job_events (job_id, worker_instance_id, event_type, from_status, to_status, lease_id, detail)
        VALUES (p_job_id, p_worker_instance_id, 'reject_invalid_transition', v_from_status, p_worker_status, p_lease_id, jsonb_build_object('endpoint', 'progress'));
        RETURN; -- empty result set signals 409 to the route handler
    END IF;

    UPDATE public.remote_render_queue
    SET worker_status = p_worker_status,
        progress = p_progress,
        message = p_message,
        heartbeat_at = NOW(),
        updated_at = NOW()
    WHERE id = p_job_id AND lease_id = p_lease_id AND worker_instance_id = p_worker_instance_id;

    IF p_worker_status IS DISTINCT FROM v_from_status THEN
        INSERT INTO public.worker_job_events (job_id, worker_instance_id, event_type, from_status, to_status, lease_id)
        VALUES (p_job_id, p_worker_instance_id, 'progress', v_from_status, p_worker_status, p_lease_id);
    END IF;

    RETURN QUERY SELECT * FROM public.remote_render_queue WHERE id = p_job_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

-- -----------------------------------------------------------------
-- 9. Complete / fail RPC - idempotency-key gated. Distinguishes:
--      a) fresh request -> apply, record idempotency snapshot
--      b) same key, same payload hash -> replay stored response, no-op on data
--      c) same key, different payload hash -> conflict, reject + audit log
--      d) stale lease (lease_id mismatch or already terminal) -> reject + audit log
--    Returns a single JSON object (not SETOF) with an explicit `outcome`
--    field so the route handler doesn't have to infer 409-vs-200 from
--    row-count alone.
-- -----------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.report_worker_render_job_outcome(
    p_job_id UUID,
    p_lease_id UUID,
    p_worker_instance_id TEXT,
    p_worker_id TEXT,
    p_success BOOLEAN,
    p_idempotency_key TEXT,
    p_request_hash TEXT,
    p_result_reference TEXT,
    p_error_code TEXT,
    p_error_message TEXT
) RETURNS JSON AS $$
DECLARE
    v_from_status TEXT;
    v_current_status TEXT;
    v_current_lease UUID;
    v_existing_hash TEXT;
    v_existing_response JSON;
    v_to_status TEXT := CASE WHEN p_success THEN 'COMPLETED' ELSE 'FAILED' END;
    v_response JSON;
BEGIN
    SELECT request_hash, response_snapshot INTO v_existing_hash, v_existing_response
    FROM public.worker_idempotency_keys
    WHERE job_id = p_job_id AND idempotency_key = p_idempotency_key;

    IF FOUND THEN
        IF v_existing_hash = p_request_hash THEN
            INSERT INTO public.worker_job_events (job_id, worker_id, worker_instance_id, event_type, lease_id, detail)
            VALUES (p_job_id, p_worker_id, p_worker_instance_id, 'idempotent_replay', p_lease_id, jsonb_build_object('idempotency_key', p_idempotency_key));
            RETURN v_existing_response;
        ELSE
            INSERT INTO public.worker_job_events (job_id, worker_id, worker_instance_id, event_type, lease_id, detail)
            VALUES (p_job_id, p_worker_id, p_worker_instance_id, 'idempotent_conflict', p_lease_id, jsonb_build_object('idempotency_key', p_idempotency_key));
            RETURN json_build_object('outcome', 'conflict', 'http_status', 409, 'detail', 'idempotency key reused with a different payload');
        END IF;
    END IF;

    SELECT status, worker_status, lease_id INTO v_current_status, v_from_status, v_current_lease
    FROM public.remote_render_queue WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND OR v_current_lease IS DISTINCT FROM p_lease_id OR v_current_status NOT IN ('rendering') THEN
        INSERT INTO public.worker_job_events (job_id, worker_id, worker_instance_id, event_type, lease_id, detail)
        VALUES (p_job_id, p_worker_id, p_worker_instance_id, 'reject_stale_lease', p_lease_id, jsonb_build_object('current_status', v_current_status, 'current_lease', v_current_lease));
        RETURN json_build_object('outcome', 'stale_lease', 'http_status', 409, 'detail', 'job is not in leased state', 'current_status', v_current_status);
    END IF;

    UPDATE public.remote_render_queue
    SET status = CASE WHEN p_success THEN 'completed' ELSE 'failed' END,
        worker_status = v_to_status,
        result_reference = COALESCE(p_result_reference, result_reference),
        result_file_id = COALESCE(p_result_reference, result_file_id),
        error_code = p_error_code,
        error_message = COALESCE(p_error_message, error_message),
        completed_at = NOW(),
        updated_at = NOW()
    WHERE id = p_job_id;

    INSERT INTO public.worker_job_events (job_id, worker_id, worker_instance_id, event_type, from_status, to_status, lease_id, detail)
    VALUES (p_job_id, p_worker_id, p_worker_instance_id, CASE WHEN p_success THEN 'complete' ELSE 'fail' END, v_from_status, v_to_status, p_lease_id,
            jsonb_build_object('result_reference', p_result_reference, 'error_code', p_error_code));

    v_response := json_build_object('outcome', 'ok', 'http_status', 200, 'job_id', p_job_id, 'status', v_to_status, 'idempotent_replay', false);

    INSERT INTO public.worker_idempotency_keys (job_id, idempotency_key, request_hash, response_snapshot)
    VALUES (p_job_id, p_idempotency_key, p_request_hash, v_response);

    RETURN v_response;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

-- -----------------------------------------------------------------
-- 10. Execute permissions - [AIR-0227D-VALIDATION Stage 4 static review
-- finding] Postgres grants EXECUTE on newly created functions to PUBLIC by
-- default, which in Supabase means `anon` and `authenticated` could call
-- these RPCs directly (e.g. supabase.rpc('claim_worker_render_job', ...)
-- from a browser with just an anon key) and completely bypass Worker Token
-- auth - SECURITY DEFINER alone does not prevent this, it only controls
-- whose privileges the function body runs with once called. Revoke first,
-- then grant only to service_role (the role auth-web's server-side client
-- executes as when using SUPABASE_SERVICE_ROLE_KEY).
REVOKE ALL ON FUNCTION public.claim_worker_render_job(TEXT, TEXT, TEXT[], TEXT, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.renew_worker_render_job_lease(UUID, UUID, TEXT, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.report_worker_render_job_progress(UUID, UUID, TEXT, TEXT, INTEGER, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.report_worker_render_job_outcome(UUID, UUID, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, TEXT) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.claim_worker_render_job(TEXT, TEXT, TEXT[], TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.renew_worker_render_job_lease(UUID, UUID, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.report_worker_render_job_progress(UUID, UUID, TEXT, TEXT, INTEGER, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.report_worker_render_job_outcome(UUID, UUID, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, TEXT, TEXT) TO service_role;
