-- AIR-0128: Add translation columns to topics_queue
-- Purpose : Persist AI-translated topic and category name fields so that
--           worker UI language changes no longer trigger runtime AI calls.
-- Target  : Supabase production DB (ibnetsoft/mytube)
-- Author  : AIR Studio / AIR-0128
-- Date    : 2026-07-04
--
-- HOW TO APPLY
-- ------------
-- 1. Open Supabase Dashboard -> SQL Editor
--    URL: https://app.supabase.com/project/<ref>/sql
-- 2. Paste the entire contents of this file and click "Run".
-- 3. Verify with:
--    SELECT column_name, data_type
--    FROM information_schema.columns
--    WHERE table_name = 'topics_queue'
--      AND column_name IN (
--        'topic_vi','topic_en','topic_th',
--        'category_name_vi','category_name_en','category_name_th'
--      );
-- 4. Expected: 6 rows returned, all with data_type = 'text'.
--
-- ROLLBACK
-- --------
-- ALTER TABLE topics_queue DROP COLUMN IF EXISTS topic_vi;
-- ALTER TABLE topics_queue DROP COLUMN IF EXISTS topic_en;
-- ALTER TABLE topics_queue DROP COLUMN IF EXISTS topic_th;
-- ALTER TABLE topics_queue DROP COLUMN IF EXISTS category_name_vi;
-- ALTER TABLE topics_queue DROP COLUMN IF EXISTS category_name_en;
-- ALTER TABLE topics_queue DROP COLUMN IF EXISTS category_name_th;
--
-- NOTES
-- -----
-- - All columns are nullable TEXT (DEFAULT NULL).
--   NULL means "not yet translated"; empty string means "translation attempted but empty".
-- - Columns are reset to NULL when an admin edits the topic text (auth-web PUT handler).
-- - Backfill existing rows with: scripts/backfill_topic_translations.py
-- - The application code is defensive: if these columns are absent the API
--   silently falls back to runtime AI translation (no downtime during migration window).

ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS topic_vi           TEXT DEFAULT NULL;
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS topic_en           TEXT DEFAULT NULL;
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS topic_th           TEXT DEFAULT NULL;
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS category_name_vi   TEXT DEFAULT NULL;
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS category_name_en   TEXT DEFAULT NULL;
ALTER TABLE topics_queue ADD COLUMN IF NOT EXISTS category_name_th   TEXT DEFAULT NULL;
