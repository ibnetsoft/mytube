-- AIR-0132: Add preferred_language column to profiles table
-- Purpose: Store per-user UI display language preference
-- NOTE: preferred_languages (TEXT[], plural) is content/topic language preference — DO NOT modify
-- This column (preferred_language, singular) is for UI display language only
--
-- Allowed values: 'ko', 'en', 'vi', 'th'
-- Default: NULL (browser detection applied on first login)
--
-- Apply manually via Supabase SQL Editor after Product Owner approval.
-- DO NOT run this automatically.

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS preferred_language TEXT DEFAULT NULL
  CHECK (preferred_language IN ('ko', 'en', 'vi', 'th'));

COMMENT ON COLUMN public.profiles.preferred_language IS
  'UI display language preference (ko/en/vi/th). NULL = not yet set, browser detection applies on first login.';
