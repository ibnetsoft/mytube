-- =============================================================
-- Migration: Worker Signup Preferences
-- =============================================================

ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS preferred_category_ids JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS preferred_category_names JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS preferred_video_length TEXT DEFAULT '';
