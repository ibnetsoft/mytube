-- =============================================================
-- Migration: AIR-0230 topics_queue.benchmark_analysis column
--
-- Adds a single nullable JSONB column so a category's most recent
-- COMPLETED topic_benchmark_analyze result (public.remote_hermes_queue,
-- see migrations/air_0230_hermes_worker_central_protocol.sql) can ride
-- along on the topics generated for that category, all the way through
-- claim_topic() into the desktop app's project_settings, and finally into
-- app/services/scene_planner.py's benchmark_analysis prompt section (see
-- docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md §2c).
--
-- Denormalized copy, not a foreign key to remote_hermes_queue.id: a
-- category's benchmark analysis informs MANY topics generated across
-- multiple bulk-generation runs, and a topic must keep working (readable,
-- claimable) even if the remote_hermes_queue row it originated from is
-- later cleaned up/expired. This mirrors topics_queue's own existing
-- denormalization pattern (e.g. category_name_vi/en/th columns already
-- copy category data at generation/translation time rather than joining).
--
-- SAFETY: This file is a DRAFT for staging review, matching the same
-- convention as air_0227d_worker_central_protocol.sql and
-- air_0230_hermes_worker_central_protocol.sql. Do NOT run against the
-- production database without staging verification first. The single
-- statement here (ALTER TABLE ADD COLUMN IF NOT EXISTS) is non-destructive
-- and does not touch any existing row's data.
-- =============================================================

ALTER TABLE public.topics_queue
    ADD COLUMN IF NOT EXISTS benchmark_analysis JSONB;
