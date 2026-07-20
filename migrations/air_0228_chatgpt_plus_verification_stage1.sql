-- =============================================================
-- Migration: AIR-0228 Stage 1 — ChatGPT Plus 구독 인증 뱃지, Additive Schema Foundation
-- Description:
--   docs/CHATGPT_PLUS_VERIFICATION_SPEC.md §3의 설계를 그대로 반영한 순수 추가(additive)
--   스키마 기반 작업. 기존 테이블/컬럼은 전혀 건드리지 않는다. 이 마이그레이션 시점까지는
--   application code(데스크톱 앱, auth-web)가 이 테이블들을 전혀 읽거나 쓰지 않는다
--   (SPEC §9 Stage 2/3에서 연결). 눈에 보이는 기능 변화 없이 안전하게 먼저 반영 가능.
--
--   Safe to run multiple times (모든 DDL이 idempotent: IF NOT EXISTS / OR REPLACE /
--   DROP ... IF EXISTS 후 CREATE).
-- =============================================================


-- ─────────────────────────────────────────────
-- 1. subscription_verifications — 제출 이력 (매 제출마다 새 row, 덮어쓰기 금지)
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

    -- 원본 파일 (Private Storage, Public URL/base64 저장 금지 — SPEC §4)
    storage_bucket            TEXT NOT NULL DEFAULT 'subscription-verifications',
    storage_path              TEXT NOT NULL,
    file_sha256               TEXT NOT NULL,
    file_mime_type            TEXT NOT NULL,
    file_size_bytes           INT NOT NULL,

    -- Gemini 추출 결과 (SPEC §3.1)
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

    -- AI 분석 원본 + 파생 판정
    ai_confidence              NUMERIC(5, 4),
    ai_visual_tampering_risk   TEXT CHECK (ai_visual_tampering_risk IN ('low', 'medium', 'high')),
    ai_suspicious_reasons      JSONB NOT NULL DEFAULT '[]'::jsonb,
    ai_recommended_action     TEXT,
    ai_raw_response            JSONB,
    rule_score                 NUMERIC(5, 2),
    duplicate_image_flag       BOOLEAN NOT NULL DEFAULT false,

    -- 리뷰/승인
    reviewed_by                UUID REFERENCES public.profiles(id),
    reviewed_at                 TIMESTAMPTZ,
    rejection_reason             TEXT,

    -- 유효기간
    expires_at                  TIMESTAMPTZ,
    revoked_at                   TIMESTAMPTZ,
    revoked_reason                TEXT,

    metadata                     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.subscription_verifications IS
    'AIR-0228 Stage 1 (new, additive). 구독 인증 제출 이력 - 같은 provider에 여러 번 제출 가능하므로 매 제출마다 새 row를 생성하고 이전 row는 보존한다(감사/사기탐지 목적, 덮어쓰기 금지). "현재 유효한 인증"은 user_badges의 ACTIVE row 1개로 대표. 아직 어떤 application code도 이 테이블을 읽거나 쓰지 않는다.';
COMMENT ON COLUMN public.subscription_verifications.masked_account_email IS
    '반드시 마스킹된 형태만 저장 - 원문 이메일은 저장하지 않는다 (SPEC/SECURITY §4 개인정보 최소화).';
COMMENT ON COLUMN public.subscription_verifications.account_email_hash IS
    '정규화(lowercase, trim)된 이메일의 sha256 - profiles.email과 대사(본인 확인)하거나 동일 이메일 중복 탐지에 사용.';
COMMENT ON COLUMN public.subscription_verifications.duplicate_image_flag IS
    '신규 row 저장 시 동일 file_sha256이 다른 user_id에도 있으면 true. true면 규칙 엔진이 점수와 무관하게 무조건 NEEDS_REVIEW로 보낸다.';

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

-- 사용자 본인 것만 조회 가능 (SPEC §5.1의 auth-web API가 서비스롤로 대신 조회하지만,
-- referral_withdrawals와 같은 방어적 관례로 본인용 정책도 둔다). 쓰기는 정책 없음 -
-- 제출은 서버(auth-web)가 검증 후 service_role로 insert하므로 클라이언트 직접 INSERT를 허용하지 않는다.
DROP POLICY IF EXISTS "Users can view own subscription verifications" ON public.subscription_verifications;
CREATE POLICY "Users can view own subscription verifications"
    ON public.subscription_verifications
    FOR SELECT
    USING (auth.uid() = user_id);


-- ─────────────────────────────────────────────
-- 2. user_badges — 범용 뱃지 테이블 (구독 인증 전용이 아니라 향후 다른 뱃지도 재사용)
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
    'AIR-0228 Stage 1 (new, additive). 범용 뱃지 테이블 - subscription_verifications 전용이 아니라 향후 다른 뱃지(이벤트 뱃지 등)도 이 테이블을 그대로 재사용할 수 있도록 설계. source_id는 source_type이 달라질 수 있어 FK를 걸지 않은 soft 참조. 아직 어떤 application code도 이 테이블을 읽거나 쓰지 않는다.';
COMMENT ON COLUMN public.user_badges.source_id IS
    'source_type=subscription_verification일 때 subscription_verifications.id를 가리키는 soft 참조(FK 미설정 - source_type이 다양해질 수 있음).';

-- 유저당 코드당 활성 뱃지 1개를 DB 레벨에서 보장 (부분 유니크 인덱스)
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
-- 3. subscription_verification_audit_logs — 감사 로그 (관리자/시스템 전용)
--    기존 referral_audit_logs는 entity_type CHECK가 ('commission','withdrawal')로
--    하드 제약되어 있어 재사용하지 않고 같은 패턴의 전용 테이블을 새로 둔다.
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
    'AIR-0228 Stage 1 (new, additive). actor_id는 시스템/배치 이벤트에서는 NULL. 관리자/시스템 전용 감사 추적 - referral_audit_logs와 같은 관례로 RLS만 켜고 정책은 두지 않는다(service_role만 접근). 아직 어떤 application code도 이 테이블을 쓰지 않는다.';

CREATE INDEX IF NOT EXISTS idx_subverif_audit_verification_id ON public.subscription_verification_audit_logs(verification_id);
CREATE INDEX IF NOT EXISTS idx_subverif_audit_action ON public.subscription_verification_audit_logs(action);

ALTER TABLE public.subscription_verification_audit_logs ENABLE ROW LEVEL SECURITY;
-- Intentionally no policies: referral_audit_logs와 동일한 관례 - service_role(RLS 우회)만
-- 읽고 쓴다. 이 저장소의 모든 관리자 API 라우트가 이미 이 방식으로 동작한다.


-- ─────────────────────────────────────────────
-- 4. Storage 버킷 — subscription-verifications (Private)
--    기존 videos(public) 버킷과 정반대. RLS(storage.objects)는 SPEC §4 설계대로
--    anon/authenticated용 정책을 만들지 않는다 - 클라이언트가 직접 Storage에
--    접근할 경로 자체가 없고(서버가 항상 대신 업로드/서명URL 발급), storage.objects는
--    Supabase가 기본적으로 RLS를 강제하므로 정책 부재 = service_role 전용이 곧 올바른 기본값.
-- ─────────────────────────────────────────────

INSERT INTO storage.buckets (id, name, public)
VALUES ('subscription-verifications', 'subscription-verifications', false)
ON CONFLICT (id) DO NOTHING;

-- =============================================================
-- End of AIR-0228 Stage 1 migration.
-- Explicitly NOT done here (by design — see docs/CHATGPT_PLUS_VERIFICATION_SPEC.md §9):
--   - No auth-web API routes (Stage 2).
--   - No desktop app settings UI / proxy endpoints (Stage 3).
--   - No web admin management screens (Stage 4).
--   - No expiry sweep batch job (Stage 5).
--   - No application code (desktop app, auth-web) reads or writes any
--     table/bucket added by this migration.
-- =============================================================
