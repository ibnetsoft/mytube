-- Rollback for air_0227_backfill_null_referral_codes.sql
-- Resets referral_code back to NULL for exactly the 3 rows confirmed
-- (live, immediately before the forward migration ran) to have had
-- referral_code IS NULL. Only safe if these accounts haven't since
-- shared their new referral_code with anyone (rolling back would
-- silently break a link already handed out).

BEGIN;

UPDATE public.profiles SET referral_code = NULL
WHERE id IN (
    'ba2f2a43-c6ea-4fe2-a6a3-0f861d93afc6', -- ejsh0519@naver.com
    'ed262e34-7343-48bb-ae57-70afd8416f83', -- abakorea@gmail.com
    '558978b0-5779-4fa7-8249-55c7840e30a4'  -- sady7@naver.com
);

COMMIT;
