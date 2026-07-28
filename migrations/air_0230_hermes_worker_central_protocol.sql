-- =============================================================
-- Migration: AIR-0230 Hermes Worker Central Protocol
--
-- Adds a FULLY SEPARATE central job-queue/lease protocol for Hermes/topic_*
-- jobs (topic_research, topic_benchmark_analyze, ...), mirroring
-- migrations/air_0227d_worker_central_protocol.sql's render-job protocol
-- (same lease/claim/progress/complete/fail shape, same idempotency and
-- audit-log conventions) but WITHOUT touching that file or its tables at
-- all.
--
-- WHY A SEPARATE TABLE INSTEAD OF REUSING remote_render_queue (decision
-- recorded in docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md):
-- remote_render_queue.project_id is NOT NULL (every render job belongs to
-- a project). topic_research/topic_benchmark_analyze jobs are
-- category/keyword-based and have no project - forcing them into that
-- table would mean relaxing a constraint on a table the legacy
-- PicadiriRemoteWorker already depends on in production. A parallel table
-- avoids that risk entirely at the cost of duplicating the lease/claim RPC
-- shape once (same pattern, proven by air_0227d_worker_central_protocol.sql).
--
-- REUSES (not duplicated) from air_0227d_worker_central_protocol.sql:
--   - public.workers / public.worker_tokens - worker identity and token
--     verification have nothing render-specific about them
--     (allowed_job_types is already a TEXT[], designed to hold any job_type
--     string). A worker/token provisioned for Hermes jobs just gets
--     allowed_job_types = ARRAY['topic_research','topic_benchmark_analyze']
--     instead of ARRAY['render_video',...] - no schema change needed there.
-- NOT REUSED (deliberately duplicated, one level, for full isolation):
--   - worker_job_events / worker_idempotency_keys have a hard FK to
--     remote_render_queue(id) - a hermes job_id (a different table's UUID)
--     can never satisfy that FK, so hermes gets its own
--     hermes_job_events / hermes_idempotency_keys instead of ALTERing
--     the render migration's tables to loosen that FK.
--
-- SAFETY: This file is a DRAFT for staging review, matching
-- air_0227d_worker_central_protocol.sql's own convention. Do NOT run
-- against the production database without the same staging verification
-- pass that migration requires. No statement here is destructive (ALTER
-- TABLE ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS / CREATE OR
-- REPLACE FUNCTION only) - it does not touch remote_render_queue or any
-- of the four tables air_0227d_worker_central_protocol.sql introduces.
-- =============================================================

-- -----------------------------------------------------------------
-- 1. remote_hermes_queue - the Hermes/topic_* equivalent of
--    remote_render_queue. project_id is intentionally absent; category_id
--    is nullable (a topic_benchmark_analyze job's payload carries the
--    literal keyword/language/video_type values already - see
--    docs/AIR_WORKER_JOB_PROTOCOL.md §5a - so category_id here is metadata
--    for filtering/audit, not something the worker needs to resolve itself).
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.remote_hermes_queue (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type            TEXT NOT NULL,              -- 'topic_research' | 'topic_benchmark_analyze' | ... (free-form, no CHECK - same convention as remote_render_queue.status)
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,  -- job_type-specific fields, see AIR_WORKER_JOB_PROTOCOL.md §5/§5a
    status              TEXT NOT NULL DEFAULT 'pending',      -- 'pending' | 'rendering' | 'completed' | 'failed' | 'canceled' (reuses remote_render_queue's status vocabulary so both queues share one mental model, even though 'rendering' reads oddly for a research job)
    worker_status       TEXT,                        -- QUEUED|CLAIMED|PREPARING|RENDERING|UPLOADING|COMPLETED|FAILED|CANCELED|ABANDONED
    priority            INTEGER NOT NULL DEFAULT 0,
    worker_group        TEXT,                        -- 'air-worker' | NULL (NULL = claimable by any group, mirrors remote_render_queue)
    worker_id           TEXT,
    worker_instance_id  TEXT,
    lease_id            UUID,
    lease_acquired_at   TIMESTAMPTZ,
    lease_expires_at    TIMESTAMPTZ,
    heartbeat_at        TIMESTAMPTZ,
    attempt_number      INTEGER NOT NULL DEFAULT 0,
    progress            INTEGER DEFAULT 0,
    message             TEXT,
    result_reference    TEXT,                        -- pointer to where the full result lives (e.g. local RESULTS_DIR path on the worker PC, until/unless a blob-storage step is added)
    result_payload       JSONB,                       -- [AIR-0230] inline result snapshot - topic_benchmark_analyze's output is only a few KB (candidates + analysis + success_strategies), so it is stored directly here rather than requiring a second fetch
    error_code          TEXT,
    error_message       TEXT,
    tenant_id           TEXT,
    category_id         TEXT,                        -- nullable on purpose - see header note; this is exactly the project_id-NOT-NULL problem remote_render_queue has, avoided here
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_remote_hermes_queue_claimable
    ON public.remote_hermes_queue (job_type, status, priority DESC, created_at ASC)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_remote_hermes_queue_lease_expiry
    ON public.remote_hermes_queue (lease_expires_at)
    WHERE status = 'rendering';

-- -----------------------------------------------------------------
-- 2. hermes_job_events - append-only audit log, mirrors worker_job_events
--    but FK'd to remote_hermes_queue instead (see header note on why this
--    can't just reuse worker_job_events).
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.hermes_job_events (
    id                  BIGSERIAL PRIMARY KEY,
    job_id              UUID REFERENCES public.remote_hermes_queue(id) ON DELETE SET NULL,
    worker_id           TEXT,
    worker_instance_id  TEXT,
    event_type          TEXT NOT NULL,  -- claim | heartbeat | renew_lease | progress | complete | fail | reject_stale_lease | reject_invalid_transition | idempotent_replay | idempotent_conflict
    from_status         TEXT,
    to_status            TEXT,
    lease_id            UUID,
    detail               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hermes_job_events_job ON public.hermes_job_events (job_id, created_at);

-- -----------------------------------------------------------------
-- 3. hermes_idempotency_keys - dedup store for complete/fail, mirrors
--    worker_idempotency_keys but FK'd to remote_hermes_queue.
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.hermes_idempotency_keys (
    job_id            UUID NOT NULL REFERENCES public.remote_hermes_queue(id) ON DELETE CASCADE,
    idempotency_key   TEXT NOT NULL,
    request_hash      TEXT NOT NULL,
    response_snapshot JSONB NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_id, idempotency_key)
);

-- -----------------------------------------------------------------
-- 3-A. RLS - same convention as air_0227d_worker_central_protocol.sql: no
-- policies added, deny-all for anon/authenticated by default once RLS is
-- enabled, service_role bypasses RLS regardless (BYPASSRLS).
-- -----------------------------------------------------------------
ALTER TABLE public.remote_hermes_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hermes_job_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hermes_idempotency_keys ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------
-- 4. Atomic claim RPC - identical shape to claim_worker_render_job, just
--    targeting remote_hermes_queue.
-- -----------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_worker_hermes_job(
    p_worker_id TEXT,
    p_worker_instance_id TEXT,
    p_allowed_job_types TEXT[],
    p_worker_group TEXT,
    p_lease_ttl_seconds INTEGER DEFAULT 300
) RETURNS SETOF public.remote_hermes_queue AS $$
DECLARE
    v_job_id UUID;
    v_lease_id UUID := gen_random_uuid();
    v_from_status TEXT;
BEGIN
    SELECT id, worker_status INTO v_job_id, v_from_status
    FROM public.remote_hermes_queue
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

    UPDATE public.remote_hermes_queue
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

    INSERT INTO public.hermes_job_events (job_id, worker_id, worker_instance_id, event_type, from_status, to_status, lease_id)
    VALUES (v_job_id, p_worker_id, p_worker_instance_id, 'claim', COALESCE(v_from_status, 'QUEUED'), 'CLAIMED', v_lease_id);

    RETURN QUERY SELECT * FROM public.remote_hermes_queue WHERE id = v_job_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

-- -----------------------------------------------------------------
-- 5. Lease renewal RPC
-- -----------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.renew_worker_hermes_job_lease(
    p_job_id UUID,
    p_lease_id UUID,
    p_worker_instance_id TEXT,
    p_lease_ttl_seconds INTEGER DEFAULT 300
) RETURNS SETOF public.remote_hermes_queue AS $$
BEGIN
    UPDATE public.remote_hermes_queue
    SET lease_expires_at = NOW() + make_interval(secs => p_lease_ttl_seconds),
        heartbeat_at = NOW(),
        updated_at = NOW()
    WHERE id = p_job_id
      AND lease_id = p_lease_id
      AND worker_instance_id = p_worker_instance_id
      AND status = 'rendering'
      AND lease_expires_at > NOW();

    IF FOUND THEN
        INSERT INTO public.hermes_job_events (job_id, worker_instance_id, event_type, lease_id)
        VALUES (p_job_id, p_worker_instance_id, 'renew_lease', p_lease_id);
    END IF;

    RETURN QUERY SELECT * FROM public.remote_hermes_queue WHERE id = p_job_id AND lease_id = p_lease_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

-- -----------------------------------------------------------------
-- 6. Progress update RPC
-- -----------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.report_worker_hermes_job_progress(
    p_job_id UUID,
    p_lease_id UUID,
    p_worker_instance_id TEXT,
    p_worker_status TEXT,
    p_progress INTEGER,
    p_message TEXT
) RETURNS SETOF public.remote_hermes_queue AS $$
DECLARE
    v_from_status TEXT;
BEGIN
    SELECT worker_status INTO v_from_status FROM public.remote_hermes_queue
    WHERE id = p_job_id AND lease_id = p_lease_id AND worker_instance_id = p_worker_instance_id;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF NOT (
        (v_from_status = 'CLAIMED' AND p_worker_status IN ('PREPARING', 'CLAIMED'))
        OR (v_from_status = 'PREPARING' AND p_worker_status IN ('RENDERING', 'PREPARING'))
        OR (v_from_status = 'RENDERING' AND p_worker_status IN ('UPLOADING', 'RENDERING'))
        OR (v_from_status = p_worker_status)
    ) THEN
        INSERT INTO public.hermes_job_events (job_id, worker_instance_id, event_type, from_status, to_status, lease_id, detail)
        VALUES (p_job_id, p_worker_instance_id, 'reject_invalid_transition', v_from_status, p_worker_status, p_lease_id, jsonb_build_object('endpoint', 'progress'));
        RETURN; -- empty result set signals 409 to the route handler
    END IF;

    UPDATE public.remote_hermes_queue
    SET worker_status = p_worker_status,
        progress = p_progress,
        message = p_message,
        heartbeat_at = NOW(),
        updated_at = NOW()
    WHERE id = p_job_id AND lease_id = p_lease_id AND worker_instance_id = p_worker_instance_id;

    IF p_worker_status IS DISTINCT FROM v_from_status THEN
        INSERT INTO public.hermes_job_events (job_id, worker_instance_id, event_type, from_status, to_status, lease_id)
        VALUES (p_job_id, p_worker_instance_id, 'progress', v_from_status, p_worker_status, p_lease_id);
    END IF;

    RETURN QUERY SELECT * FROM public.remote_hermes_queue WHERE id = p_job_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

-- -----------------------------------------------------------------
-- 7. Complete / fail RPC - same idempotency-key gating as
--    report_worker_render_job_outcome, plus an extra p_result_payload
--    param [AIR-0230] so topic_benchmark_analyze's compact analysis JSON
--    can be stored inline instead of needing a separate blob-fetch step.
-- -----------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.report_worker_hermes_job_outcome(
    p_job_id UUID,
    p_lease_id UUID,
    p_worker_instance_id TEXT,
    p_worker_id TEXT,
    p_success BOOLEAN,
    p_idempotency_key TEXT,
    p_request_hash TEXT,
    p_result_reference TEXT,
    p_result_payload JSONB,
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
    FROM public.hermes_idempotency_keys
    WHERE job_id = p_job_id AND idempotency_key = p_idempotency_key;

    IF FOUND THEN
        IF v_existing_hash = p_request_hash THEN
            INSERT INTO public.hermes_job_events (job_id, worker_id, worker_instance_id, event_type, lease_id, detail)
            VALUES (p_job_id, p_worker_id, p_worker_instance_id, 'idempotent_replay', p_lease_id, jsonb_build_object('idempotency_key', p_idempotency_key));
            RETURN v_existing_response;
        ELSE
            INSERT INTO public.hermes_job_events (job_id, worker_id, worker_instance_id, event_type, lease_id, detail)
            VALUES (p_job_id, p_worker_id, p_worker_instance_id, 'idempotent_conflict', p_lease_id, jsonb_build_object('idempotency_key', p_idempotency_key));
            RETURN json_build_object('outcome', 'conflict', 'http_status', 409, 'detail', 'idempotency key reused with a different payload');
        END IF;
    END IF;

    SELECT status, worker_status, lease_id INTO v_current_status, v_from_status, v_current_lease
    FROM public.remote_hermes_queue WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND OR v_current_lease IS DISTINCT FROM p_lease_id OR v_current_status NOT IN ('rendering') THEN
        INSERT INTO public.hermes_job_events (job_id, worker_id, worker_instance_id, event_type, lease_id, detail)
        VALUES (p_job_id, p_worker_id, p_worker_instance_id, 'reject_stale_lease', p_lease_id, jsonb_build_object('current_status', v_current_status, 'current_lease', v_current_lease));
        RETURN json_build_object('outcome', 'stale_lease', 'http_status', 409, 'detail', 'job is not in leased state', 'current_status', v_current_status);
    END IF;

    UPDATE public.remote_hermes_queue
    SET status = CASE WHEN p_success THEN 'completed' ELSE 'failed' END,
        worker_status = v_to_status,
        result_reference = COALESCE(p_result_reference, result_reference),
        result_payload = COALESCE(p_result_payload, result_payload),
        error_code = p_error_code,
        error_message = COALESCE(p_error_message, error_message),
        completed_at = NOW(),
        updated_at = NOW()
    WHERE id = p_job_id;

    INSERT INTO public.hermes_job_events (job_id, worker_id, worker_instance_id, event_type, from_status, to_status, lease_id, detail)
    VALUES (p_job_id, p_worker_id, p_worker_instance_id, CASE WHEN p_success THEN 'complete' ELSE 'fail' END, v_from_status, v_to_status, p_lease_id,
            jsonb_build_object('result_reference', p_result_reference, 'error_code', p_error_code));

    v_response := json_build_object('outcome', 'ok', 'http_status', 200, 'job_id', p_job_id, 'status', v_to_status, 'idempotent_replay', false);

    INSERT INTO public.hermes_idempotency_keys (job_id, idempotency_key, request_hash, response_snapshot)
    VALUES (p_job_id, p_idempotency_key, p_request_hash, v_response);

    RETURN v_response;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

-- -----------------------------------------------------------------
-- 8. Execute permissions - same rationale as air_0227d_worker_central_protocol.sql
-- §10: revoke the default PUBLIC grant first, then allow only service_role.
-- -----------------------------------------------------------------
REVOKE ALL ON FUNCTION public.claim_worker_hermes_job(TEXT, TEXT, TEXT[], TEXT, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.renew_worker_hermes_job_lease(UUID, UUID, TEXT, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.report_worker_hermes_job_progress(UUID, UUID, TEXT, TEXT, INTEGER, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.report_worker_hermes_job_outcome(UUID, UUID, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, JSONB, TEXT, TEXT) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.claim_worker_hermes_job(TEXT, TEXT, TEXT[], TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.renew_worker_hermes_job_lease(UUID, UUID, TEXT, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.report_worker_hermes_job_progress(UUID, UUID, TEXT, TEXT, INTEGER, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.report_worker_hermes_job_outcome(UUID, UUID, TEXT, TEXT, BOOLEAN, TEXT, TEXT, TEXT, JSONB, TEXT, TEXT) TO service_role;
