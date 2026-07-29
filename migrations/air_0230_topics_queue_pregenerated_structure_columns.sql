-- =============================================================
-- Migration: AIR-0230 §2d topics_queue pre-baked scene structure columns
--
-- Adds the two columns the "pre-bake buffer" pipeline needs:
-- - pregenerated_structure JSONB: the scene_planner_service.plan_scenes()
--   output for this topic, written by
--   auth-web/app/api/internal/worker/jobs/[jobId]/complete/route.ts's
--   sync-back step when a script_plan_generate job (worker/hermes_worker.py
--   on branch feat/air-0230-topic-benchmark-analyze, see
--   docs/AIR_WORKER_JOB_PROTOCOL.md §5b) completes for this row.
-- - pregenerated_structure_status TEXT: 'none' (default, nothing queued)
--   | 'queued' (job enqueued, not done yet) | 'ready' (structure available)
--   | 'failed'. app/routers/gemini.py::generate_script_structure_api()
--   checks this via project_settings.pregenerated_structure_status (copied
--   there by claim_topic(), app/routers/user_topics.py) to skip the live AI
--   call entirely when a pre-baked structure is already ready.
--
-- Deliberately does NOT add a script-text-pregenerated column - see
-- docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md §2d for why
-- full-script pre-baking is a separate, not-yet-started decision (the
-- generation logic currently only exists as stateful client JS in
-- templates/pages/script_gen.html).
--
-- SAFETY: DRAFT for staging review, same convention as every other
-- AIR-0230/air_0227d migration in this directory. Do NOT run against
-- production without staging verification first. Both statements are
-- non-destructive (ADD COLUMN IF NOT EXISTS).
-- =============================================================

ALTER TABLE public.topics_queue
    ADD COLUMN IF NOT EXISTS pregenerated_structure JSONB,
    ADD COLUMN IF NOT EXISTS pregenerated_structure_status TEXT NOT NULL DEFAULT 'none';
