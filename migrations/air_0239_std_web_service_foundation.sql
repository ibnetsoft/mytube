-- AIR-0239: STD web service foundation.
--
-- Separate web-only STD workflow tables. These do not replace the desktop
-- SQLite project model, desktop_project_metadata, render queues, or worker
-- protocol. Binary image/video files live in Google Drive; these tables store
-- ownership, scene structure, Drive file references, and review state.

CREATE TABLE IF NOT EXISTS public.std_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_queue_id BIGINT REFERENCES public.topics_queue(id) ON DELETE SET NULL,
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    employee_email TEXT NOT NULL,
    title TEXT NOT NULL,
    category_id BIGINT,
    language TEXT NOT NULL DEFAULT 'ko',
    status TEXT NOT NULL DEFAULT 'claimed',
    assigned_duration_minutes INTEGER,
    estimated_payout NUMERIC,
    script_style TEXT,
    image_style TEXT,
    drive_folder_id TEXT,
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    project_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    progress_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    submitted_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT std_projects_status_check CHECK (
        status IN (
            'claimed',
            'in_progress',
            'assets_submitted',
            'review_requested',
            'approved',
            'revision_requested',
            'rejected',
            'canceled'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_std_projects_topic_queue_id
    ON public.std_projects(topic_queue_id)
    WHERE topic_queue_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_std_projects_employee_status
    ON public.std_projects(employee_email, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_std_projects_payload
    ON public.std_projects USING GIN (project_payload);

CREATE TABLE IF NOT EXISTS public.std_project_scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.std_projects(id) ON DELETE CASCADE,
    scene_number INTEGER NOT NULL,
    scene_title TEXT,
    scene_text TEXT,
    image_prompt TEXT,
    video_prompt TEXT,
    shot_hints JSONB NOT NULL DEFAULT '[]'::jsonb,
    asset_status TEXT NOT NULL DEFAULT 'missing',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, scene_number),
    CONSTRAINT std_project_scenes_asset_status_check CHECK (
        asset_status IN ('missing', 'partial', 'ready', 'needs_review')
    )
);

CREATE INDEX IF NOT EXISTS idx_std_project_scenes_project_order
    ON public.std_project_scenes(project_id, scene_number);

CREATE TABLE IF NOT EXISTS public.std_project_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.std_projects(id) ON DELETE CASCADE,
    scene_id UUID REFERENCES public.std_project_scenes(id) ON DELETE SET NULL,
    scene_number INTEGER,
    asset_type TEXT NOT NULL,
    drive_file_id TEXT NOT NULL,
    drive_folder_id TEXT,
    file_name TEXT NOT NULL,
    mime_type TEXT,
    file_size BIGINT,
    checksum TEXT,
    status TEXT NOT NULL DEFAULT 'uploaded',
    uploaded_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT std_project_assets_type_check CHECK (
        asset_type IN ('image', 'video', 'thumbnail', 'original', 'other')
    ),
    CONSTRAINT std_project_assets_status_check CHECK (
        status IN ('uploaded', 'assigned', 'replaced', 'deleted', 'rejected')
    )
);

CREATE INDEX IF NOT EXISTS idx_std_project_assets_project_scene
    ON public.std_project_assets(project_id, scene_number, asset_type, status);

CREATE INDEX IF NOT EXISTS idx_std_project_assets_drive_file
    ON public.std_project_assets(drive_file_id);

CREATE TABLE IF NOT EXISTS public.std_project_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.std_projects(id) ON DELETE CASCADE,
    submitted_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'review_requested',
    note TEXT,
    review_note TEXT,
    reviewed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT std_project_submissions_status_check CHECK (
        status IN ('review_requested', 'approved', 'revision_requested', 'rejected')
    )
);

CREATE INDEX IF NOT EXISTS idx_std_project_submissions_status
    ON public.std_project_submissions(status, submitted_at DESC);

ALTER TABLE public.std_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.std_project_scenes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.std_project_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.std_project_submissions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "std_projects_service_all" ON public.std_projects;
CREATE POLICY "std_projects_service_all" ON public.std_projects
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "std_project_scenes_service_all" ON public.std_project_scenes;
CREATE POLICY "std_project_scenes_service_all" ON public.std_project_scenes
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "std_project_assets_service_all" ON public.std_project_assets;
CREATE POLICY "std_project_assets_service_all" ON public.std_project_assets
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "std_project_submissions_service_all" ON public.std_project_submissions;
CREATE POLICY "std_project_submissions_service_all" ON public.std_project_submissions
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.std_projects TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.std_project_scenes TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.std_project_assets TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.std_project_submissions TO service_role;
