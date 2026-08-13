-- AIR-0235: keep remote render jobs serial by default.
--
-- The previous claim_worker_render_job() implementation allowed every online
-- render worker in the same worker_group to claim one pending row, so the
-- dashboard could show many jobs in "rendering" at once. This replacement adds
-- a server-side concurrency gate. auth-web passes p_max_concurrent_jobs from
-- AIRWORKER_MAX_CONCURRENT_RENDER_JOBS, defaulting to 1.

CREATE OR REPLACE FUNCTION public.claim_worker_render_job(
    p_worker_id TEXT,
    p_worker_instance_id TEXT,
    p_allowed_job_types TEXT[],
    p_worker_group TEXT,
    p_lease_ttl_seconds INTEGER DEFAULT 300,
    p_max_concurrent_jobs INTEGER DEFAULT 1
) RETURNS SETOF public.remote_render_queue AS $$
DECLARE
    v_job_id UUID;
    v_lease_id UUID := gen_random_uuid();
    v_from_status TEXT;
    v_active_count INTEGER := 0;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('claim_worker_render_job:' || COALESCE(p_worker_group, 'default')));

    IF COALESCE(p_max_concurrent_jobs, 1) > 0 THEN
        SELECT COUNT(*) INTO v_active_count
        FROM public.remote_render_queue
        WHERE status = 'rendering'
          AND job_type = ANY(p_allowed_job_types)
          AND (worker_group IS NULL OR worker_group = p_worker_group)
          AND (
                lease_expires_at > NOW()
                OR (
                    lease_expires_at IS NULL
                    AND COALESCE(heartbeat_at, updated_at, claimed_at) > NOW() - INTERVAL '30 minutes'
                )
              );

        IF v_active_count >= p_max_concurrent_jobs THEN
            RETURN;
        END IF;
    END IF;

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

    INSERT INTO public.worker_job_events (job_id, worker_id, worker_instance_id, event_type, from_status, to_status, lease_id, detail)
    VALUES (
        v_job_id,
        p_worker_id,
        p_worker_instance_id,
        'claim',
        COALESCE(v_from_status, 'QUEUED'),
        'CLAIMED',
        v_lease_id,
        jsonb_build_object('max_concurrent_jobs', p_max_concurrent_jobs)
    );

    RETURN QUERY SELECT * FROM public.remote_render_queue WHERE id = v_job_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

REVOKE ALL ON FUNCTION public.claim_worker_render_job(TEXT, TEXT, TEXT[], TEXT, INTEGER, INTEGER) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_worker_render_job(TEXT, TEXT, TEXT[], TEXT, INTEGER, INTEGER) TO service_role;
