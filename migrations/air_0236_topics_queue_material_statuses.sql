-- AIR-0236: Track the six generated materials for Hermes topic production.
--
-- Existing columns already cover two materials:
-- - pregenerated_structure_status: scene plan + image/video prompts
-- - pregenerated_script_status: narration script
--
-- This migration adds the missing explicit status columns so admin/worker
-- screens can show the six-material checklist without inferring everything
-- from opaque JSON payloads.

ALTER TABLE public.topics_queue
    ADD COLUMN IF NOT EXISTS benchmark_status TEXT NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS title_status TEXT NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS web_research_status TEXT NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS publish_metadata_status TEXT NOT NULL DEFAULT 'none';

CREATE INDEX IF NOT EXISTS idx_topics_queue_material_statuses
    ON public.topics_queue (
        benchmark_status,
        title_status,
        web_research_status,
        pregenerated_structure_status,
        pregenerated_script_status,
        publish_metadata_status
    );

UPDATE public.worker_tokens
SET allowed_job_types = array_append(allowed_job_types, 'publish_metadata_generate')
WHERE allowed_job_types @> ARRAY['script_generate']::text[]
  AND NOT allowed_job_types @> ARRAY['publish_metadata_generate']::text[];

UPDATE public.workers
SET allowed_job_types = array_append(allowed_job_types, 'publish_metadata_generate')
WHERE allowed_job_types @> ARRAY['script_generate']::text[]
  AND NOT allowed_job_types @> ARRAY['publish_metadata_generate']::text[];
