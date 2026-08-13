-- Migration: AIR-0231 topics_queue generated title review columns
--
-- Hermes Autopilot now separates the plain production topic from upload-ready
-- YouTube title candidates. Keep the selected title and the scored candidate
-- list on the queue row when this migration is applied. Older deployments still
-- receive the same data inside benchmark_analysis.title_generation.

ALTER TABLE public.topics_queue
    ADD COLUMN IF NOT EXISTS generated_title TEXT,
    ADD COLUMN IF NOT EXISTS title_candidates JSONB;

CREATE INDEX IF NOT EXISTS idx_topics_queue_generated_title
    ON public.topics_queue (generated_title)
    WHERE generated_title IS NOT NULL;
