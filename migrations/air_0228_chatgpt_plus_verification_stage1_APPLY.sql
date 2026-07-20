-- =============================================================
-- AIR-0228 Stage 1 — SINGLE-PASTE APPLY SCRIPT for Supabase SQL Editor
--
-- This is a convenience wrapper, not a replacement for the reviewed files:
--   - air_0228_chatgpt_plus_verification_stage1.sql          (the approved migration, unchanged)
--   - air_0228_chatgpt_plus_verification_stage1_rollback.sql (rollback, unchanged)
--   - air_0228_chatgpt_plus_verification_stage1_CHECKLIST.md (the approved procedure)
--
-- What this file does: BEGIN -> the exact migration statements -> the
-- checklist's §4 verification checks, rewritten as DO-block assertions ->
-- COMMIT. If ANY assertion fails, it RAISEs an exception, which aborts the
-- transaction. Postgres then treats the trailing COMMIT as a no-op ROLLBACK
-- automatically — you do not need to manually decide COMMIT vs ROLLBACK.
--
-- HOW TO RUN:
--   1. Supabase Dashboard -> this project -> SQL Editor -> New query.
--   2. Paste this entire file.
--   3. Click Run, once.
--   4. Read the output:
--      - "Success. No rows returned" + a NOTICE reading
--        "AIR-0228 Stage 1: all verification checks passed." => applied and committed.
--      - Any red error message (e.g. "Stage1 check FAILED: ...") => nothing
--        was committed, the whole migration was automatically rolled back.
--        Copy the exact error text back for diagnosis before retrying.
-- =============================================================

BEGIN;

-- ─────────────────────────────────────────────
-- 1. subscription_verifications — new table
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.subscription_verifications (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                   UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    provider                  TEXT NOT NULL
                                  CHECK (provider IN ('chatgpt_plus', 'chatgpt_pro', 'gemini_advanced', 'claude_pro')),
    badge_code                TEXT NOT NULL,
    status                    TEXT NOT NULL DEFAULT 'UPLOADED'
                                  CHECK (status IN ('UPLOADED', 'ANALYZING', 'NEEDS_REVIEW',
                                                     'APPROVED', 'REJECTED', 'EXPIRED', 'REVOKED')),
    storage_bucket            TEXT NOT NULL DEFAULT 'subscription-verifications',
    storage_path              TEXT NOT NULL,
    file_sha256               TEXT NOT NULL,
    file_mime_type            TEXT NOT NULL,
    file_size_bytes           INT NOT NULL,
    document_type             TEXT,
    subscription_status_raw   TEXT,
    purchase_channel          TEXT,
    masked_account_email      TEXT,
    account_email_hash        TEXT,
    payment_date              DATE,
    billing_period_start      DATE,
    billing_period_end        DATE,
    next_renewal_date         DATE,
    currency                  TEXT,
    amount                    NUMERIC(12, 2),
    required_fields_visible   BOOLEAN,
    ai_confidence              NUMERIC(5, 4),
    ai_visual_tampering_risk   TEXT CHECK (ai_visual_tampering_risk IN ('low', 'medium', 'high')),
    ai_suspicious_reasons      JSONB NOT NULL DEFAULT '[]'::jsonb,
    ai_recommended_action     TEXT,
    ai_raw_response            JSONB,
    rule_score                 NUMERIC(5, 2),
    duplicate_image_flag       BOOLEAN NOT NULL DEFAULT false,
    reviewed_by                UUID REFERENCES public.profiles(id),
    reviewed_at                 TIMESTAMPTZ,
    rejection_reason             TEXT,
    expires_at                  TIMESTAMPTZ,
    revoked_at                   TIMESTAMPTZ,
    revoked_reason                TEXT,
    metadata                     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.subscription_verifications IS
    'AIR-0228 Stage 1 (new, additive). 구독 인증 제출 이력 - 매 제출마다 새 row, 덮어쓰기 금지. 아직 어떤 application code도 이 테이블을 읽거나 쓰지 않는다.';
COMMENT ON COLUMN public.subscription_verifications.masked_account_email IS
    '반드시 마스킹된 형태만 저장 - 원문 이메일은 저장하지 않는다.';
COMMENT ON COLUMN public.subscription_verifications.account_email_hash IS
    '정규화된 이메일의 sha256 - profiles.email과 대사하거나 동일 이메일 중복 탐지에 사용.';
COMMENT ON COLUMN public.subscription_verifications.duplicate_image_flag IS
    '동일 file_sha256이 다른 user_id에도 있으면 true - 규칙 엔진이 무조건 NEEDS_REVIEW로 보낸다.';

CREATE INDEX IF NOT EXISTS idx_subscription_verifications_user_id ON public.subscription_verifications(user_id);
CREATE INDEX IF NOT EXISTS idx_subscription_verifications_status ON public.subscription_verifications(status);
CREATE INDEX IF NOT EXISTS idx_subscription_verifications_sha256 ON public.subscription_verifications(file_sha256);
CREATE INDEX IF NOT EXISTS idx_subscription_verifications_expires_at ON public.subscription_verifications(expires_at);

CREATE OR REPLACE FUNCTION public.set_subscription_verifications_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_subscription_verifications_updated_at ON public.subscription_verifications;
CREATE TRIGGER trg_subscription_verifications_updated_at
    BEFORE UPDATE ON public.subscription_verifications
    FOR EACH ROW
    EXECUTE FUNCTION public.set_subscription_verifications_updated_at();

ALTER TABLE public.subscription_verifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own subscription verifications" ON public.subscription_verifications;
CREATE POLICY "Users can view own subscription verifications"
    ON public.subscription_verifications
    FOR SELECT
    USING (auth.uid() = user_id);


-- ─────────────────────────────────────────────
-- 2. user_badges — new table
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.user_badges (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    badge_code   TEXT NOT NULL,
    source_type  TEXT NOT NULL DEFAULT 'subscription_verification',
    source_id    UUID,
    status       TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'EXPIRED', 'REVOKED')),
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.user_badges IS
    'AIR-0228 Stage 1 (new, additive). 범용 뱃지 테이블 - 향후 다른 뱃지도 재사용 가능하도록 설계. 아직 어떤 application code도 이 테이블을 읽거나 쓰지 않는다.';
COMMENT ON COLUMN public.user_badges.source_id IS
    'source_type=subscription_verification일 때 subscription_verifications.id를 가리키는 soft 참조(FK 미설정).';

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_badges_active_per_code
    ON public.user_badges(user_id, badge_code) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_user_badges_user_id ON public.user_badges(user_id);
CREATE INDEX IF NOT EXISTS idx_user_badges_expires_at ON public.user_badges(expires_at);

CREATE OR REPLACE FUNCTION public.set_user_badges_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_badges_updated_at ON public.user_badges;
CREATE TRIGGER trg_user_badges_updated_at
    BEFORE UPDATE ON public.user_badges
    FOR EACH ROW
    EXECUTE FUNCTION public.set_user_badges_updated_at();

ALTER TABLE public.user_badges ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own badges" ON public.user_badges;
CREATE POLICY "Users can view own badges"
    ON public.user_badges
    FOR SELECT
    USING (auth.uid() = user_id);


-- ─────────────────────────────────────────────
-- 3. subscription_verification_audit_logs — new table
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.subscription_verification_audit_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    verification_id  UUID NOT NULL REFERENCES public.subscription_verifications(id) ON DELETE CASCADE,
    action           TEXT NOT NULL CHECK (action IN (
                         'uploaded', 'analysis_started', 'auto_approved', 'sent_to_review',
                         'approved', 'rejected', 'revoked', 'reanalyzed', 'expired', 'expiry_date_edited'
                     )),
    actor_id         UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    reason           TEXT,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.subscription_verification_audit_logs IS
    'AIR-0228 Stage 1 (new, additive). 관리자/시스템 전용 감사 추적 - service_role만 접근(정책 없음). 아직 어떤 application code도 쓰지 않는다.';

CREATE INDEX IF NOT EXISTS idx_subverif_audit_verification_id ON public.subscription_verification_audit_logs(verification_id);
CREATE INDEX IF NOT EXISTS idx_subverif_audit_action ON public.subscription_verification_audit_logs(action);

ALTER TABLE public.subscription_verification_audit_logs ENABLE ROW LEVEL SECURITY;
-- Intentionally no policies: service-role only.


-- ─────────────────────────────────────────────
-- 4. Storage bucket
-- ─────────────────────────────────────────────

INSERT INTO storage.buckets (id, name, public)
VALUES ('subscription-verifications', 'subscription-verifications', false)
ON CONFLICT (id) DO NOTHING;


-- ─────────────────────────────────────────────
-- 5. Self-verification — checklist §4, as automatic assertions.
-- ─────────────────────────────────────────────

DO $$
DECLARE
    v_count INT;
BEGIN
    -- 5a. All 3 new tables exist
    IF to_regclass('public.subscription_verifications') IS NULL THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5a): subscription_verifications table missing';
    END IF;
    IF to_regclass('public.user_badges') IS NULL THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5a): user_badges table missing';
    END IF;
    IF to_regclass('public.subscription_verification_audit_logs') IS NULL THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5a): subscription_verification_audit_logs table missing';
    END IF;

    -- 5b. RLS enabled on all 3
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.subscription_verifications'::regclass) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5b): RLS not enabled on subscription_verifications';
    END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.user_badges'::regclass) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5b): RLS not enabled on user_badges';
    END IF;
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.subscription_verification_audit_logs'::regclass) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5b): RLS not enabled on subscription_verification_audit_logs';
    END IF;

    -- 5c. Policy counts match design (1 each on the two user-facing tables, 0 on audit_logs)
    SELECT count(*) INTO v_count FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'subscription_verifications';
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5c): expected 1 policy on subscription_verifications, found %', v_count;
    END IF;
    SELECT count(*) INTO v_count FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'user_badges';
    IF v_count <> 1 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5c): expected 1 policy on user_badges, found %', v_count;
    END IF;
    SELECT count(*) INTO v_count FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'subscription_verification_audit_logs';
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5c): expected 0 policies on subscription_verification_audit_logs, found %', v_count;
    END IF;

    -- 5d. Triggers exist and enabled
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'public.subscription_verifications'::regclass
          AND tgname = 'trg_subscription_verifications_updated_at'
          AND tgenabled <> 'D'
    ) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5d): trg_subscription_verifications_updated_at missing or disabled';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'public.user_badges'::regclass
          AND tgname = 'trg_user_badges_updated_at'
          AND tgenabled <> 'D'
    ) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5d): trg_user_badges_updated_at missing or disabled';
    END IF;

    -- 5e. All 9 indexes exist (4 + 3 + 2)
    SELECT count(*) INTO v_count FROM pg_indexes
    WHERE schemaname = 'public' AND indexname IN (
        'idx_subscription_verifications_user_id',
        'idx_subscription_verifications_status',
        'idx_subscription_verifications_sha256',
        'idx_subscription_verifications_expires_at',
        'uq_user_badges_active_per_code',
        'idx_user_badges_user_id',
        'idx_user_badges_expires_at',
        'idx_subverif_audit_verification_id',
        'idx_subverif_audit_action'
    );
    IF v_count <> 9 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5e): expected 9 indexes, found %', v_count;
    END IF;

    -- 5f. Storage bucket exists and is private
    IF NOT EXISTS (
        SELECT 1 FROM storage.buckets WHERE id = 'subscription-verifications' AND public = false
    ) THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5f): subscription-verifications bucket missing or public';
    END IF;

    -- 5g. New tables are genuinely empty
    SELECT count(*) INTO v_count FROM public.subscription_verifications;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5g): subscription_verifications should be empty, has % rows', v_count;
    END IF;
    SELECT count(*) INTO v_count FROM public.user_badges;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5g): user_badges should be empty, has % rows', v_count;
    END IF;
    SELECT count(*) INTO v_count FROM public.subscription_verification_audit_logs;
    IF v_count <> 0 THEN
        RAISE EXCEPTION 'Stage1 check FAILED (5g): subscription_verification_audit_logs should be empty, has % rows', v_count;
    END IF;

    RAISE NOTICE 'AIR-0228 Stage 1: all verification checks passed.';
END $$;

COMMIT;
