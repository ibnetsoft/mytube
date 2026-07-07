-- AIR-0202: Add 'analyzing' to analysis_status in voice_profiles table

DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'voice_profiles'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%analysis_status%';

    IF constraint_name IS NOT NULL THEN
        EXECUTE 'ALTER TABLE voice_profiles DROP CONSTRAINT ' || constraint_name;
    END IF;
END $$;

ALTER TABLE voice_profiles ADD CONSTRAINT voice_profiles_analysis_status_check 
CHECK (analysis_status IN ('pending', 'analyzing', 'manual', 'analyzed', 'failed', 'needs_review'));
