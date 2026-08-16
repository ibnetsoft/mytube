-- AIR-0241: Persistent benchmark channel pool for Hermes RSS discovery.
--
-- Hermes keeps a local JSON state cache for offline continuity, but the
-- long-lived channel pool must survive worker PC changes. The worker upserts
-- auto-discovered and manually curated channel IDs here, then reads them before
-- each category benchmark run.

CREATE TABLE IF NOT EXISTS public.benchmark_channel_pool (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_name TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_title TEXT,
    source TEXT NOT NULL DEFAULT 'auto'
        CHECK (source IN ('auto', 'manual', 'local_sync', 'import')),
    discovery_query TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT benchmark_channel_pool_category_channel_unique UNIQUE (category_name, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_channel_pool_category_active
    ON public.benchmark_channel_pool (category_name, active, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_benchmark_channel_pool_channel
    ON public.benchmark_channel_pool (channel_id);

CREATE INDEX IF NOT EXISTS idx_benchmark_channel_pool_metrics
    ON public.benchmark_channel_pool USING GIN (metrics);

ALTER TABLE public.benchmark_channel_pool ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "benchmark_channel_pool_service_all" ON public.benchmark_channel_pool;
CREATE POLICY "benchmark_channel_pool_service_all" ON public.benchmark_channel_pool
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.benchmark_channel_pool TO service_role;
