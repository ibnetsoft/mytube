-- AIR-0248: keep repeated STD renders on one project as immutable versions.
-- Existing queue rows remain valid; new rows receive metadata.render_version.

CREATE INDEX IF NOT EXISTS idx_remote_render_queue_std_project_history
    ON public.remote_render_queue ((metadata ->> 'std_web_project_id'), created_at DESC)
    WHERE metadata ? 'std_web_project_id';

CREATE UNIQUE INDEX IF NOT EXISTS idx_remote_render_queue_std_project_version
    ON public.remote_render_queue (
        (metadata ->> 'std_web_project_id'),
        (metadata ->> 'render_version')
    )
    WHERE metadata ? 'std_web_project_id'
      AND metadata ? 'render_version';

CREATE INDEX IF NOT EXISTS idx_std_project_submissions_project_history
    ON public.std_project_submissions (project_id, submitted_at DESC);
