-- AIR-0129: Add translation status tracking columns to topics_queue
-- These columns track background translation pipeline state set by the admin API.
--
-- HOW TO APPLY
--   1. Open the Supabase dashboard → SQL Editor.
--   2. Paste and run this script.
--   3. Verify with: SELECT column_name FROM information_schema.columns
--                   WHERE table_name = 'topics_queue'
--                   AND column_name IN ('translated_at', 'translation_status');
--
-- PREREQUISITE
--   AIR-0128 migration (air_0128_topics_queue_translation_columns.sql) must already
--   be applied before this migration.
--
-- ROLLBACK
--   ALTER TABLE topics_queue DROP COLUMN IF EXISTS translated_at;
--   ALTER TABLE topics_queue DROP COLUMN IF EXISTS translation_status;

ALTER TABLE topics_queue
    ADD COLUMN IF NOT EXISTS translated_at      TIMESTAMPTZ DEFAULT NULL;

ALTER TABLE topics_queue
    ADD COLUMN IF NOT EXISTS translation_status TEXT        DEFAULT NULL
        CHECK (
            translation_status IS NULL
            OR translation_status IN ('pending', 'running', 'completed', 'failed')
        );
