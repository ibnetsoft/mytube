-- AIR-0242: Route topic repair/follow-up Hermes jobs back to the worker that
-- originally generated the prepared topic.
--
-- This keeps multi-PC AIRWorker installs deterministic: if worker01 prepared a
-- topic, an admin repair job targets worker01 while it is online. Operators can
-- clear/override target_worker_id later if they intentionally want reassignment.

ALTER TABLE public.remote_hermes_queue
    ADD COLUMN IF NOT EXISTS target_worker_id TEXT;

ALTER TABLE public.topics_queue
    ADD COLUMN IF NOT EXISTS generated_by_worker_id TEXT,
    ADD COLUMN IF NOT EXISTS generated_by_worker_instance_id TEXT,
    ADD COLUMN IF NOT EXISTS generated_by_worker_job_id UUID,
    ADD COLUMN IF NOT EXISTS generated_by_worker_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_remote_hermes_queue_target_worker_claimable
    ON public.remote_hermes_queue (target_worker_id, job_type, status, priority DESC, created_at ASC)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_topics_queue_generated_by_worker
    ON public.topics_queue (generated_by_worker_id)
    WHERE generated_by_worker_id IS NOT NULL;

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
    v_target_worker_id TEXT;
BEGIN
    SELECT id, worker_status, target_worker_id INTO v_job_id, v_from_status, v_target_worker_id
    FROM public.remote_hermes_queue
    WHERE job_type = ANY(p_allowed_job_types)
      AND (worker_group IS NULL OR worker_group = p_worker_group)
      AND (target_worker_id IS NULL OR target_worker_id = p_worker_id)
      AND (
            status = 'pending'
            OR (status = 'rendering' AND lease_expires_at IS NOT NULL AND lease_expires_at < NOW())
          )
    ORDER BY
        CASE WHEN target_worker_id = p_worker_id THEN 0 ELSE 1 END,
        priority DESC,
        created_at ASC
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

    INSERT INTO public.hermes_job_events (job_id, worker_id, worker_instance_id, event_type, from_status, to_status, lease_id, detail)
    VALUES (
        v_job_id,
        p_worker_id,
        p_worker_instance_id,
        'claim',
        COALESCE(v_from_status, 'QUEUED'),
        'CLAIMED',
        v_lease_id,
        jsonb_build_object(
            'target_worker_id', v_target_worker_id,
            'target_worker_id_matched', v_target_worker_id IS NOT NULL AND v_target_worker_id = p_worker_id
        )
    );

    RETURN QUERY SELECT * FROM public.remote_hermes_queue WHERE id = v_job_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

REVOKE ALL ON FUNCTION public.claim_worker_hermes_job(TEXT, TEXT, TEXT[], TEXT, INTEGER) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_worker_hermes_job(TEXT, TEXT, TEXT[], TEXT, INTEGER) TO service_role;
