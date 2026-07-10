-- =============================================================
-- Migration: AIR-0226 — profiles.pin_code VARCHAR(4) -> VARCHAR(72)
--
-- ROOT CAUSE: pin_code is the actual credential checked at login
-- (auth-web/app/api/desktop-login/route.ts, desktop-change-password/
-- route.ts), but the column is VARCHAR(4) — a genuine 4-digit PIN
-- field, not a password field. The signup screen and the new desktop
-- "change password" feature (templates/pages/settings.html) both
-- collect and validate an 8+ character complex password (upper/lower/
-- digit/special), which can never fit in 4 characters. Every real
-- change-password attempt with a compliant password fails with:
--   22001 value too long for type character varying(4)
-- Confirmed live via a synthetic test account before writing this fix.
--
-- Existing 4-digit values (e.g. the '1234' default) are untouched and
-- remain valid — this only widens the column so it can also hold a
-- full password. 72 matches common bcrypt/complex-password practical
-- max length conventions; pin_code is stored as plain text here (no
-- hashing), consistent with its existing handling in desktop-login.
--
-- Safe to re-run: ALTER COLUMN ... TYPE is idempotent in effect (a
-- second run against an already-VARCHAR(72) column is a no-op change).
-- =============================================================

BEGIN;

ALTER TABLE public.profiles
    ALTER COLUMN pin_code TYPE VARCHAR(72);

DO $$
DECLARE
    v_max_length INTEGER;
BEGIN
    SELECT character_maximum_length INTO v_max_length
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'profiles' AND column_name = 'pin_code';

    IF v_max_length IS DISTINCT FROM 72 THEN
        RAISE EXCEPTION 'AIR-0226 check FAILED: pin_code max length is % (expected 72)', v_max_length;
    END IF;

    RAISE NOTICE 'AIR-0226: pin_code is now VARCHAR(72).';
END $$;

COMMIT;
