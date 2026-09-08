-- Scene media now lives in Supabase Storage first. Drive remains an optional
-- fallback, so a Storage-backed asset legitimately has no Drive file id.
ALTER TABLE public.std_project_assets
    ALTER COLUMN drive_file_id DROP NOT NULL;
