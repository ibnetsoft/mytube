-- =============================================================
-- AIR-0224A — Read-only diagnostic (run this FIRST, before the hotfix,
-- to confirm the root cause exactly rather than trusting the
-- codebase-archaeology hypothesis alone). Nothing here writes anything.
--
-- This environment has no SQL Editor / pg_proc access, so this file exists
-- to be run by whoever does (CTO) — paste the results back if you want
-- independent confirmation before applying the hotfix. The hotfix migration
-- itself (air_0224a_profile_referral_trigger_hotfix.sql) is written to be
-- correct regardless of the exact answer here (DROP TRIGGER IF EXISTS and
-- CREATE OR REPLACE FUNCTION are both safe no-ops-or-complete-overwrites),
-- so running this diagnostic is optional confirmation, not a hard blocker.
-- =============================================================

-- 1. Which of the 3 suspected broken triggers are actually installed on profiles?
SELECT trigger_name, event_manipulation, action_timing, action_statement
FROM information_schema.triggers
WHERE event_object_schema = 'public' AND event_object_table = 'profiles'
ORDER BY trigger_name;
-- Expected culprits (per worknote/AIR-0224A.md): trigger_referral_join,
-- trigger_user_activity_referral, trigger_analytics_referral_join.

-- 2. What does the live handle_new_user() actually contain?
SELECT pg_get_functiondef(oid) AS live_source
FROM pg_proc
WHERE proname = 'handle_new_user' AND pronamespace = 'public'::regnamespace;
-- Compare against auth-web/supabase_schema.sql:28-102 (correct) vs
-- MIGRATION.sql:16-23 (old, broken, ignores referred_by_id) — see which
-- one this actually matches.

-- 3. What does the live handle_referral_join() / handle_user_activity() /
--    handle_backend_analytics() actually reference? (confirms the
--    referrer_id dereference is really in there before dropping anything)
SELECT proname, pg_get_functiondef(oid) AS live_source
FROM pg_proc
WHERE proname IN ('handle_referral_join', 'handle_user_activity', 'handle_backend_analytics')
  AND pronamespace = 'public'::regnamespace;

-- 4. Trigger on auth.users — confirm it points at handle_new_user (should be unaffected either way)
SELECT trigger_name, event_object_schema, event_object_table, action_statement
FROM information_schema.triggers
WHERE trigger_name = 'on_auth_user_created';
