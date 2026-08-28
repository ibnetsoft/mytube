-- AIR-0243: Music prompt missions for STD web contributors.
-- Stores worker/admin-generated music prompts and user-uploaded audio submissions.

CREATE TABLE IF NOT EXISTS public.music_prompt_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    target_market TEXT NOT NULL DEFAULT 'th',
    genre TEXT NOT NULL DEFAULT 'lofi',
    mood TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    negative_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    duration_target_seconds INTEGER NOT NULL DEFAULT 180,
    reward_usdt NUMERIC(12, 4) NOT NULL DEFAULT 0,
    max_submissions INTEGER NOT NULL DEFAULT 1,
    accepted_submissions_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by_worker_id TEXT,
    created_by_worker_job_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT music_prompt_tasks_status_check CHECK (status IN ('open', 'paused', 'closed')),
    CONSTRAINT music_prompt_tasks_duration_check CHECK (duration_target_seconds BETWEEN 30 AND 900),
    CONSTRAINT music_prompt_tasks_max_submissions_check CHECK (max_submissions > 0)
);

CREATE INDEX IF NOT EXISTS idx_music_prompt_tasks_open
    ON public.music_prompt_tasks(status, target_market, created_at DESC);

CREATE TABLE IF NOT EXISTS public.music_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES public.music_prompt_tasks(id) ON DELETE CASCADE,
    submitted_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    submitted_email TEXT NOT NULL,
    drive_file_id TEXT NOT NULL,
    drive_folder_id TEXT,
    file_name TEXT NOT NULL,
    mime_type TEXT,
    file_size BIGINT,
    tool_name TEXT NOT NULL DEFAULT '',
    prompt_used TEXT NOT NULL DEFAULT '',
    lyrics TEXT NOT NULL DEFAULT '',
    license_confirmed BOOLEAN NOT NULL DEFAULT false,
    originality_confirmed BOOLEAN NOT NULL DEFAULT false,
    commercial_use_confirmed BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'submitted',
    reward_usdt NUMERIC(12, 4) NOT NULL DEFAULT 0,
    review_note TEXT,
    reviewed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT music_submissions_status_check CHECK (
        status IN ('submitted', 'approved', 'revision_requested', 'rejected')
    )
);

CREATE INDEX IF NOT EXISTS idx_music_submissions_task_status
    ON public.music_submissions(task_id, status, submitted_at DESC);

CREATE INDEX IF NOT EXISTS idx_music_submissions_submitter
    ON public.music_submissions(submitted_email, submitted_at DESC);

ALTER TABLE public.music_prompt_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.music_submissions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "music_prompt_tasks_service_all" ON public.music_prompt_tasks;
CREATE POLICY "music_prompt_tasks_service_all" ON public.music_prompt_tasks
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "music_submissions_service_all" ON public.music_submissions;
CREATE POLICY "music_submissions_service_all" ON public.music_submissions
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.music_prompt_tasks TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.music_submissions TO service_role;
