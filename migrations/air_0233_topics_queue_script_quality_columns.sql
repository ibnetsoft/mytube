-- AIR-0233: Persist Hermes script writing QA artifacts.
--
-- These columns make the generated plan/script inspectable before a user
-- claims the topic, and let admin/learning views audit whether the script
-- passed the story-quality gate.

ALTER TABLE public.topics_queue
    ADD COLUMN IF NOT EXISTS narrative_blueprint JSONB,
    ADD COLUMN IF NOT EXISTS script_quality_report JSONB;

CREATE INDEX IF NOT EXISTS idx_topics_queue_script_quality_report
    ON public.topics_queue USING GIN (script_quality_report)
    WHERE script_quality_report IS NOT NULL;
