-- =============================================================
-- Rollback: AIR-0228 Stage 1 — ChatGPT Plus 구독 인증 뱃지, Additive Schema Foundation
-- Reverses migrations/air_0228_chatgpt_plus_verification_stage1.sql exactly.
--
-- Safe by construction: every object this rollback drops was created by
-- the Stage-1 migration and, as of Stage 1, is not read or written by any
-- application code — so there is nothing to lose. If Stage 2+ has since
-- started writing to these tables or uploading files to the
-- subscription-verifications bucket, DO NOT run this rollback without
-- first checking for data (see the pre-flight queries at the bottom) —
-- this script does not archive anything, it drops it.
-- =============================================================


-- ─────────────────────────────────────────────
-- 4. Storage bucket (reverse of §4)
--    NOTE: this only removes the bucket ROW. If any object was ever
--    uploaded to it (should be none at Stage 1), delete those first via
--    the Supabase dashboard/Storage API - a bucket with objects in it
--    cannot be deleted by this statement alone.
-- ─────────────────────────────────────────────
DELETE FROM storage.buckets WHERE id = 'subscription-verifications';


-- ─────────────────────────────────────────────
-- 3. Drop subscription_verification_audit_logs (reverse of §3)
-- ─────────────────────────────────────────────
DROP TABLE IF EXISTS public.subscription_verification_audit_logs;


-- ─────────────────────────────────────────────
-- 2. Drop user_badges (reverse of §2)
-- ─────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_user_badges_updated_at ON public.user_badges;
DROP FUNCTION IF EXISTS public.set_user_badges_updated_at();
DROP TABLE IF EXISTS public.user_badges;


-- ─────────────────────────────────────────────
-- 1. Drop subscription_verifications (reverse of §1)
-- ─────────────────────────────────────────────
DROP TRIGGER IF EXISTS trg_subscription_verifications_updated_at ON public.subscription_verifications;
DROP FUNCTION IF EXISTS public.set_subscription_verifications_updated_at();
DROP TABLE IF EXISTS public.subscription_verifications;


-- =============================================================
-- Pre-flight checks — run these BEFORE executing the drops above if
-- Stage 2+ work may have already started:
--
--   SELECT count(*) FROM public.subscription_verifications;
--   SELECT count(*) FROM public.user_badges;
--   SELECT count(*) FROM public.subscription_verification_audit_logs;
--   SELECT count(*) FROM storage.objects WHERE bucket_id = 'subscription-verifications';
--
-- If any of these return > 0, stop and export/archive the rows (and any
-- uploaded files) first — this rollback does not preserve them.
-- =============================================================
