-- 학습형 제작 시스템 중앙 저장 테이블
-- Supabase SQL Editor에서 실행하세요.

CREATE TABLE IF NOT EXISTS public.project_learning_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_key TEXT NOT NULL UNIQUE,
    local_event_id BIGINT NOT NULL,
    local_project_id BIGINT NOT NULL,
    project_sync_id TEXT,
    user_id UUID NULL REFERENCES auth.users(id) ON DELETE SET NULL,
    employee_email TEXT,
    project_name TEXT,
    project_topic TEXT,
    event_type TEXT NOT NULL,
    stage TEXT,
    source TEXT DEFAULT 'system',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    local_created_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_learning_events_user_created
ON public.project_learning_events(user_id, local_created_at DESC);

CREATE INDEX IF NOT EXISTS idx_project_learning_events_type_stage
ON public.project_learning_events(event_type, stage);

CREATE INDEX IF NOT EXISTS idx_project_learning_events_project
ON public.project_learning_events(project_sync_id, local_project_id);

CREATE TABLE IF NOT EXISTS public.project_learning_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_key TEXT NOT NULL UNIQUE,
    local_snapshot_id BIGINT NOT NULL,
    local_project_id BIGINT NOT NULL,
    project_sync_id TEXT,
    user_id UUID NULL REFERENCES auth.users(id) ON DELETE SET NULL,
    employee_email TEXT,
    project_name TEXT,
    project_topic TEXT,
    snapshot_type TEXT NOT NULL,
    reference JSONB NOT NULL DEFAULT '{}'::jsonb,
    style JSONB NOT NULL DEFAULT '{}'::jsonb,
    script JSONB NOT NULL DEFAULT '{}'::jsonb,
    thumbnail JSONB NOT NULL DEFAULT '{}'::jsonb,
    tts JSONB NOT NULL DEFAULT '{}'::jsonb,
    video JSONB NOT NULL DEFAULT '{}'::jsonb,
    qa JSONB NOT NULL DEFAULT '{}'::jsonb,
    upload JSONB NOT NULL DEFAULT '{}'::jsonb,
    local_created_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_learning_snapshots_user_created
ON public.project_learning_snapshots(user_id, local_created_at DESC);

CREATE INDEX IF NOT EXISTS idx_project_learning_snapshots_project_type
ON public.project_learning_snapshots(project_sync_id, local_project_id, snapshot_type);

ALTER TABLE public.project_learning_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.project_learning_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "project_learning_events_self_read" ON public.project_learning_events;
CREATE POLICY "project_learning_events_self_read" ON public.project_learning_events
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "project_learning_snapshots_self_read" ON public.project_learning_snapshots;
CREATE POLICY "project_learning_snapshots_self_read" ON public.project_learning_snapshots
    FOR SELECT USING (auth.uid() = user_id);
