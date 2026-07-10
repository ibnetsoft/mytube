-- Rollback for air_0226_profiles_pin_code_password_length.sql
-- Restores pin_code to VARCHAR(4). Only safe if no value longer than
-- 4 characters has been written since the forward migration ran (any
-- longer value will fail this ALTER with a "value too long" error —
-- check with the query below before rolling back).

-- SELECT id, pin_code FROM public.profiles WHERE length(pin_code) > 4;

BEGIN;

ALTER TABLE public.profiles
    ALTER COLUMN pin_code TYPE VARCHAR(4);

COMMIT;
