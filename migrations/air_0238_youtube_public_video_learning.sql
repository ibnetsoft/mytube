-- AIR-0238: public YouTube video monitoring and learning snapshots.

CREATE TABLE IF NOT EXISTS public.youtube_video_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_key TEXT NOT NULL UNIQUE,
    publishing_request_id UUID REFERENCES public.publishing_requests(id) ON DELETE SET NULL,
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    local_project_id INTEGER,
    video_id TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    hours_since_public INTEGER NOT NULL,
    views BIGINT NOT NULL DEFAULT 0,
    likes BIGINT NOT NULL DEFAULT 0,
    comments BIGINT NOT NULL DEFAULT 0,
    duration_seconds INTEGER,
    score JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_youtube_video_metrics_video_time
    ON public.youtube_video_metrics (video_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_youtube_video_metrics_project_time
    ON public.youtube_video_metrics (local_project_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_youtube_video_metrics_score
    ON public.youtube_video_metrics USING GIN (score);

CREATE TABLE IF NOT EXISTS public.video_learning_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_key TEXT NOT NULL UNIQUE,
    publishing_request_id UUID REFERENCES public.publishing_requests(id) ON DELETE SET NULL,
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    local_project_id INTEGER,
    video_id TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    hours_since_public INTEGER NOT NULL,
    performance_score NUMERIC,
    outcome_label TEXT NOT NULL DEFAULT 'unknown',
    learning_summary TEXT,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    generation_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_video_learning_snapshots_outcome
    ON public.video_learning_snapshots (outcome_label, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_video_learning_snapshots_project_time
    ON public.video_learning_snapshots (local_project_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_video_learning_snapshots_context
    ON public.video_learning_snapshots USING GIN (generation_context);

ALTER TABLE public.youtube_video_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.video_learning_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "youtube_video_metrics_service_all" ON public.youtube_video_metrics;
CREATE POLICY "youtube_video_metrics_service_all" ON public.youtube_video_metrics
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "video_learning_snapshots_service_all" ON public.video_learning_snapshots;
CREATE POLICY "video_learning_snapshots_service_all" ON public.video_learning_snapshots
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.youtube_video_metrics TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.video_learning_snapshots TO service_role;
