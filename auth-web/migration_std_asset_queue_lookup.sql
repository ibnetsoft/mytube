-- Queue polling used to de-TOAST and scan every historical asset even when idle.
-- Covers all worker kinds without indexing large snapshots or generated media.
-- Bound lock waits so deployment cannot hold up submissions behind a busy DB.
SET lock_timeout = '5s';
SET statement_timeout = '60s';
CREATE INDEX IF NOT EXISTS idx_std_asset_queue_kind_state_updated
ON public.std_project_assets ((metadata->>'kind'), (metadata->>'state'), updated_at);
