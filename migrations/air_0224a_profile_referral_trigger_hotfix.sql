-- =============================================================
-- Migration: AIR-0224A — Production Profile Referral Trigger Hotfix
--
-- ROOT CAUSE (confirmed via codebase archaeology, see
-- worknote/AIR-0224A.md for full evidence and file:line citations):
--
-- Bug 1 — profiles UPDATE fails with:
--   42703 record "new" has no field "referrer_id"
-- Cause: three orphaned "Gen 3" triggers, all AFTER UPDATE ON
-- public.profiles, all committed together in one batch (commit b2e8a0ee,
-- 2026-07-07) as part of a never-launched admin/risk/habit/analytics
-- feature stack that has zero application callers (confirmed in
-- CONSOLIDATION_PLAN.md's earlier audit). Each one unconditionally
-- dereferences NEW.referrer_id / OLD.referrer_id before any business logic
-- runs, and profiles.referrer_id has never existed (the real column is
-- referred_by, auth-web/supabase_schema.sql:18) — so ANY UPDATE to
-- profiles fires whichever of these is installed and crashes immediately,
-- regardless of which columns were actually being changed:
--   - trigger_referral_join          -> handle_referral_join()          (migrations/air_0205_referral_notifications.sql)
--   - trigger_user_activity_referral -> handle_user_activity()          (migrations/air_0206_habit_loop.sql)
--   - trigger_analytics_referral_join -> handle_backend_analytics()     (migrations/air_0207_analytics.sql)
--
-- Bug 2 — profiles.referred_by stays NULL even though
-- user_metadata.referred_by_id was sent correctly at signup (verified:
-- AIR-0224's test account creation confirmed the metadata WAS stored
-- correctly on auth.users, but profiles.referred_by came out NULL).
-- Cause: the AFTER INSERT ON auth.users trigger on_auth_user_created calls
-- public.handle_new_user() — a function name that exists in TWO places in
-- this repo's history: the correct, current version in
-- auth-web/supabase_schema.sql:28-102 (added by AIR-0122, 2026-07-03,
-- reads raw_user_meta_data->>'referred_by_id' and sets referred_by), and a
-- much older, trivial version in the legacy root-level MIGRATION.sql:16-23
-- (predates AIR-0122 by 5 months, "Picadiri Studio"-branded bootstrap
-- script, ignores raw_user_meta_data entirely). Because CREATE OR REPLACE
-- FUNCTION overwrites by name+signature regardless of which file it came
-- from, if MIGRATION.sql's block was ever (re-)run against production
-- after supabase_schema.sql's version was deployed, it would silently
-- replace the correct function with the broken one — the currently-live
-- trigger attachment (on_auth_user_created) wouldn't need to change at all
-- for this to happen. This migration re-asserts the known-correct version
-- unconditionally, which fixes this regardless of the exact mechanism.
--
-- SCOPE: only the 3 broken profiles-UPDATE trigger *attachments* are
-- dropped (not the underlying shared functions, which may still be
-- legitimately attached to other Gen 2/3 orphaned tables like worker_jobs/
-- commissions — touching those is out of AIR-0224A's scope). Only
-- handle_new_user() is reasserted. Only the 4 known AIR-0224 E2E test
-- accounts get a referred_by backfill (NOT a blanket fix for every
-- profiles row with NULL referred_by — NULL is a legitimate state for a
-- real organic user with no referrer, and rewriting arbitrary production
-- rows is explicitly out of scope for a "minimal hotfix").
--
-- Existing policy on invalid/unmatched referrer values, confirmed
-- unchanged by this migration (documenting per AIR-0224A's own
-- instruction, not deciding fresh): handle_new_user() SILENTLY IGNORES an
-- invalid or non-matching referred_by_id/referral_code — it does not
-- reject the signup. An unparseable UUID is caught (EXCEPTION WHEN
-- invalid_text_representation) and treated as NULL; a well-formed UUID
-- with no matching profile row leaves referrer_profile unset (all fields
-- NULL), so referred_by is inserted as NULL. The signup itself always
-- proceeds either way. This is existing, unmodified behavior — see
-- app/routers/auth.py's SEPARATE, earlier check
-- (validate_referral_code()) for the one path that DOES reject a signup,
-- which only applies to the referral_code text-entry flow, not the
-- referred_by_id (Default Sponsor) flow this trigger handles.
--
-- Safe to re-run (every statement is idempotent: DROP TRIGGER IF EXISTS,
-- CREATE OR REPLACE FUNCTION, UPDATE ... WHERE with an idempotent target
-- value).
-- =============================================================

BEGIN;

-- ─────────────────────────────────────────────
-- Part 1 — drop the 3 broken orphaned triggers on public.profiles
-- ─────────────────────────────────────────────
DROP TRIGGER IF EXISTS trigger_referral_join ON public.profiles;
DROP TRIGGER IF EXISTS trigger_user_activity_referral ON public.profiles;
DROP TRIGGER IF EXISTS trigger_analytics_referral_join ON public.profiles;

-- ─────────────────────────────────────────────
-- Part 2 — re-assert the correct handle_new_user(), verbatim from
-- auth-web/supabase_schema.sql:28-102 (the AIR-0122 version).
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    raw_preferred_languages TEXT[];
    clean_preferred_languages TEXT[];
    raw_referral_code TEXT;
    raw_referred_by_id UUID;
    generated_referral_code TEXT;
    referrer_profile public.profiles%ROWTYPE;
    normalized_country TEXT;
BEGIN
    SELECT ARRAY(
        SELECT DISTINCT lang
        FROM jsonb_array_elements_text(COALESCE(NEW.raw_user_meta_data->'preferred_languages', '["ko"]'::jsonb)) AS lang
        WHERE lang IN ('ko', 'en', 'ja')
    ) INTO raw_preferred_languages;

    clean_preferred_languages := COALESCE(NULLIF(raw_preferred_languages, ARRAY[]::TEXT[]), ARRAY['ko'::TEXT]);
    raw_referral_code := upper(trim(COALESCE(NEW.raw_user_meta_data->>'referral_code', NEW.raw_user_meta_data->>'referred_by_code', '')));

    BEGIN
        raw_referred_by_id := (NEW.raw_user_meta_data->>'referred_by_id')::UUID;
    EXCEPTION WHEN invalid_text_representation THEN
        raw_referred_by_id := NULL;
    END;

    normalized_country := upper(left(regexp_replace(COALESCE(NEW.raw_user_meta_data->>'country_code', NEW.raw_user_meta_data->>'nationality', 'KR'), '[^A-Za-z]', '', 'g'), 2));
    IF normalized_country = '' THEN
        normalized_country := 'KR';
    END IF;

    IF raw_referral_code <> '' THEN
        SELECT * INTO referrer_profile
        FROM public.profiles
        WHERE upper(referral_code) = raw_referral_code
        LIMIT 1;
    ELSIF raw_referred_by_id IS NOT NULL THEN
        SELECT * INTO referrer_profile
        FROM public.profiles
        WHERE id = raw_referred_by_id
        LIMIT 1;
    END IF;

    LOOP
        generated_referral_code := upper(substr(md5(random()::text || clock_timestamp()::text || NEW.id::text), 1, 8));
        EXIT WHEN NOT EXISTS (SELECT 1 FROM public.profiles WHERE referral_code = generated_referral_code);
    END LOOP;

    INSERT INTO public.profiles (
        id, email, preferred_languages, referral_code, referred_by,
        referral_depth, country_code, referral_country, commission_rate
    )
    VALUES (
        NEW.id,
        NEW.email,
        clean_preferred_languages,
        generated_referral_code,
        referrer_profile.id,
        COALESCE(referrer_profile.referral_depth + 1, 0),
        normalized_country,
        COALESCE(referrer_profile.referral_country, referrer_profile.country_code, normalized_country),
        0
    )
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        preferred_languages = COALESCE(public.profiles.preferred_languages, EXCLUDED.preferred_languages),
        referral_code = COALESCE(public.profiles.referral_code, EXCLUDED.referral_code),
        referred_by = COALESCE(public.profiles.referred_by, EXCLUDED.referred_by),
        referral_depth = COALESCE(public.profiles.referral_depth, EXCLUDED.referral_depth),
        country_code = COALESCE(public.profiles.country_code, EXCLUDED.country_code),
        referral_country = COALESCE(public.profiles.referral_country, EXCLUDED.referral_country),
        commission_rate = COALESCE(public.profiles.commission_rate, EXCLUDED.commission_rate);
    RETURN NEW;
END;
$$;

-- Confirm the trigger attachment on auth.users still points at this
-- function (it should already — CREATE OR REPLACE doesn't change the
-- trigger, only the function body — but re-asserting costs nothing and
-- guards against the trigger having been dropped separately).
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ─────────────────────────────────────────────
-- Part 3 — backfill referred_by for the 4 known AIR-0224 E2E test accounts
-- ONLY (created 2026-07-09, see AIR-0224_QA.md §5 for their ids). Scoped by
-- email, not a blanket profiles fix.
-- ─────────────────────────────────────────────
UPDATE public.profiles
SET referred_by = (SELECT id FROM public.profiles WHERE email = 'e2e-default-sponsor@airqa.test')
WHERE email = 'e2e-user-a@airqa.test' AND referred_by IS NULL;

UPDATE public.profiles
SET referred_by = (SELECT id FROM public.profiles WHERE email = 'e2e-user-a@airqa.test')
WHERE email = 'e2e-user-b@airqa.test' AND referred_by IS NULL;

UPDATE public.profiles
SET referred_by = (SELECT id FROM public.profiles WHERE email = 'e2e-user-b@airqa.test')
WHERE email = 'e2e-user-c@airqa.test' AND referred_by IS NULL;

-- ─────────────────────────────────────────────
-- Part 4 — self-verification (aborts + auto-rolls-back the whole
-- transaction on any failure, same pattern as prior AIR-0221 apply scripts)
-- ─────────────────────────────────────────────
DO $$
DECLARE
    v_trigger_count INT;
    v_func_def TEXT;
    v_ds_id UUID;
    v_a_referred_by UUID;
    v_b_referred_by UUID;
    v_c_referred_by UUID;
BEGIN
    -- 4a. The 3 broken triggers are gone
    SELECT count(*) INTO v_trigger_count
    FROM information_schema.triggers
    WHERE event_object_schema = 'public' AND event_object_table = 'profiles'
      AND trigger_name IN ('trigger_referral_join', 'trigger_user_activity_referral', 'trigger_analytics_referral_join');
    IF v_trigger_count <> 0 THEN
        RAISE EXCEPTION 'AIR-0224A check FAILED (4a): % broken trigger(s) on profiles still present', v_trigger_count;
    END IF;

    -- 4b. handle_new_user() now contains the referred_by_id fallback logic
    SELECT pg_get_functiondef(oid) INTO v_func_def
    FROM pg_proc WHERE proname = 'handle_new_user' AND pronamespace = 'public'::regnamespace;
    IF v_func_def IS NULL OR v_func_def NOT LIKE '%referred_by_id%' THEN
        RAISE EXCEPTION 'AIR-0224A check FAILED (4b): handle_new_user() does not contain referred_by_id logic after CREATE OR REPLACE';
    END IF;

    -- 4c. The 4 test accounts' referred_by chain is now correct
    SELECT id INTO v_ds_id FROM public.profiles WHERE email = 'e2e-default-sponsor@airqa.test';
    SELECT referred_by INTO v_a_referred_by FROM public.profiles WHERE email = 'e2e-user-a@airqa.test';
    SELECT referred_by INTO v_b_referred_by FROM public.profiles WHERE email = 'e2e-user-b@airqa.test';
    SELECT referred_by INTO v_c_referred_by FROM public.profiles WHERE email = 'e2e-user-c@airqa.test';

    IF v_a_referred_by IS DISTINCT FROM v_ds_id THEN
        RAISE EXCEPTION 'AIR-0224A check FAILED (4c): User A.referred_by (%) does not equal Default Sponsor id (%)', v_a_referred_by, v_ds_id;
    END IF;
    IF v_b_referred_by IS DISTINCT FROM (SELECT id FROM public.profiles WHERE email = 'e2e-user-a@airqa.test') THEN
        RAISE EXCEPTION 'AIR-0224A check FAILED (4c): User B.referred_by does not equal User A id';
    END IF;
    IF v_c_referred_by IS DISTINCT FROM (SELECT id FROM public.profiles WHERE email = 'e2e-user-b@airqa.test') THEN
        RAISE EXCEPTION 'AIR-0224A check FAILED (4c): User C.referred_by does not equal User B id';
    END IF;

    RAISE NOTICE 'AIR-0224A: all checks passed — broken triggers removed, handle_new_user() corrected, E2E test chain backfilled (DS <- A <- B <- C).';
END $$;

COMMIT;
