-- AIR-0232: Category-level feedback memory for Hermes content generation.
--
-- Stores compact automatic/manual evaluations of generated titles, plans,
-- and scripts. The worker reads recent rows back as "learning memory" for
-- the next title-generation cycle. Raw YouTube audit payloads stay on the
-- worker disk; this table intentionally stores only compact, reviewable
-- signals.

CREATE TABLE IF NOT EXISTS public.content_generation_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_queue_id TEXT,
    category_id TEXT,
    category_name TEXT,
    source_job_id UUID REFERENCES public.remote_hermes_queue(id) ON DELETE SET NULL,
    feedback_source TEXT NOT NULL DEFAULT 'auto'
        CHECK (feedback_source IN ('auto', 'manual', 'performance')),
    outcome_quality TEXT NOT NULL DEFAULT 'unknown'
        CHECK (outcome_quality IN ('excellent', 'good', 'neutral', 'poor', 'rejected', 'unknown')),
    generated_title TEXT,
    production_topic TEXT,
    title_score NUMERIC(5,2),
    script_score NUMERIC(5,2),
    reviewer_email TEXT,
    reviewer_note TEXT,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    title_generation JSONB NOT NULL DEFAULT '{}'::jsonb,
    benchmark_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    evaluation JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_content_generation_feedback_category_created
    ON public.content_generation_feedback (category_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_content_generation_feedback_quality_created
    ON public.content_generation_feedback (outcome_quality, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_content_generation_feedback_topic_source
    ON public.content_generation_feedback (topic_queue_id, feedback_source);

ALTER TABLE public.content_generation_feedback ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "content_generation_feedback_service_all" ON public.content_generation_feedback;
CREATE POLICY "content_generation_feedback_service_all" ON public.content_generation_feedback
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.content_generation_feedback TO service_role;
