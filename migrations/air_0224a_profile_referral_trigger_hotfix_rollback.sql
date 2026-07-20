-- =============================================================
-- Rollback: AIR-0224A — Production Profile Referral Trigger Hotfix
--
-- HONEST LIMITATION, stated up front: this rollback can precisely restore
-- the 3 dropped trigger *attachments* (their exact CREATE TRIGGER
-- statements, from migrations/air_0205/0206/0207, which still define the
-- underlying functions — this migration never touched those). It CANNOT
-- precisely restore whatever handle_new_user() body was live before this
-- migration ran, because that body was never directly observed (no SQL
-- Editor / pg_proc access was available when this hotfix was written — see
-- worknote/AIR-0224A.md). Re-installing a KNOWN-BROKEN function on purpose
-- would be actively harmful, not a safe rollback, so this script
-- deliberately does NOT attempt it. If the handle_new_user() fix itself
-- needs to be reverted for some reason, that requires manually sourcing
-- the exact prior definition (e.g. from a pg_dump backup/PITR snapshot
-- taken before this migration), not this file.
--
-- What this DOES roll back cleanly:
--   1. Re-creates the 3 orphaned triggers on public.profiles (restores
--      the exact prior state — including the bug, since these triggers
--      were the ones broken. Only do this if you specifically need to
--      revert to the OLD broken-UPDATE state for some diagnostic reason;
--      there is no normal reason to want this back.)
--   2. Does NOT revert the handle_new_user() fix (see above).
--   3. Does NOT revert the 4 AIR-0224 test accounts' referred_by backfill
--      (reverting real, now-correct data to NULL serves no purpose — if
--      truly needed, the commented block at the bottom does it).
-- =============================================================

BEGIN;

-- ─────────────────────────────────────────────
-- Restore the 3 dropped triggers, verbatim from their original migrations.
-- ─────────────────────────────────────────────

-- From migrations/air_0205_referral_notifications.sql
DROP TRIGGER IF EXISTS trigger_referral_join ON public.profiles;
CREATE TRIGGER trigger_referral_join
    AFTER UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_referral_join();

-- From migrations/air_0206_habit_loop.sql
DROP TRIGGER IF EXISTS trigger_user_activity_referral ON public.profiles;
CREATE TRIGGER trigger_user_activity_referral
    AFTER UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_user_activity();

-- From migrations/air_0207_analytics.sql
DROP TRIGGER IF EXISTS trigger_analytics_referral_join ON public.profiles;
CREATE TRIGGER trigger_analytics_referral_join
    AFTER UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_backend_analytics();

DO $$
DECLARE v_count INT;
BEGIN
    SELECT count(*) INTO v_count
    FROM information_schema.triggers
    WHERE event_object_schema = 'public' AND event_object_table = 'profiles'
      AND trigger_name IN ('trigger_referral_join', 'trigger_user_activity_referral', 'trigger_analytics_referral_join');
    IF v_count <> 3 THEN
        RAISE EXCEPTION 'Rollback FAILED: expected 3 restored triggers, found %. (If handle_referral_join/handle_user_activity/handle_backend_analytics no longer exist as functions, this rollback cannot succeed — check whether a later migration dropped them.)', v_count;
    END IF;
    RAISE NOTICE 'AIR-0224A rollback: 3 orphaned triggers restored (profiles UPDATE will break again — this is a revert to the KNOWN-BROKEN prior state, only do this deliberately).';
END $$;

COMMIT;

-- =============================================================
-- OPTIONAL — only if you specifically want to revert the 4 test accounts'
-- referred_by back to NULL (not part of the main rollback above; there is
-- no normal reason to want this):
-- =============================================================
-- UPDATE public.profiles SET referred_by = NULL WHERE email IN (
--     'e2e-user-a@airqa.test', 'e2e-user-b@airqa.test', 'e2e-user-c@airqa.test'
-- );
