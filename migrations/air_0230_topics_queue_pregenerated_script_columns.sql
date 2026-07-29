-- =============================================================
-- Migration: AIR-0230 §2d topics_queue pre-baked narration script columns
--
-- Companion to air_0230_topics_queue_pregenerated_structure_columns.sql -
-- adds the columns for the full narration text (script_generate job_type,
-- worker/hermes_worker.py on branch feat/air-0230-topic-benchmark-analyze,
-- see docs/AIR_WORKER_JOB_PROTOCOL.md §5c):
-- - pregenerated_script TEXT: the final concatenated narration text.
-- - pregenerated_script_status TEXT: 'none' (default) | 'queued' | 'ready'
--   | 'failed', mirroring pregenerated_structure_status's convention.
--
-- Per user decision, this is now the ONLY path for STD claimed-topic
-- projects - app/routers/gemini.py's live-generation fallback for both
-- structure and script has been removed for that project type (manually
-- created / PRO projects, which have no topic_queue_id, are unaffected and
-- keep using live generation as before, since there is nothing to
-- pre-bake for them).
--
-- SAFETY: DRAFT for staging review, same convention as every other
-- AIR-0230 migration. Do NOT run against production without staging
-- verification first. Non-destructive (ADD COLUMN IF NOT EXISTS).
-- =============================================================

ALTER TABLE public.topics_queue
    ADD COLUMN IF NOT EXISTS pregenerated_script TEXT,
    ADD COLUMN IF NOT EXISTS pregenerated_script_status TEXT NOT NULL DEFAULT 'none';
