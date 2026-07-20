-- =============================================================
-- 유저 -> 웹어드민 문의(Support) 시스템
-- =============================================================
-- 데스크톱 앱 유저가 웹어드민으로 문의를 보내고, 어드민이 발신자를 확인한
-- 뒤 답장한다. AI(Gemini)가 문의 내용을 분석해 답장 초안을 미리 만들어
-- 두지만, 그 초안은 어드민에게만 보이고 사용자에게 자동 발송되지 않는다
-- - 어드민이 검토/수정 후 직접 발송해야 status가 ANSWERED로 바뀐다.
--
-- 비용 정책: AI 초안 생성은 global_settings.sys_api_gemini(기존 공용
-- Gemini 키, auth-web/app/api/admin/topics-queue/route.ts와 동일 패턴)를
-- 서버 측에서 사용한다 - 사용자의 token_balance/used_tokens와는 무관.

CREATE TABLE IF NOT EXISTS public.support_messages (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    subject           TEXT,
    body              TEXT NOT NULL,
    detected_language TEXT,                    -- AI가 감지한 문의 언어 (ko/en/th/vi 등)
    status            TEXT NOT NULL DEFAULT 'OPEN'
                          CHECK (status IN ('OPEN', 'AI_DRAFTED', 'ANSWERED', 'CLOSED')),
    ai_draft_reply    TEXT,                     -- AI 1차 초안 - 어드민에게만 노출
    ai_draft_model    TEXT,                     -- 초안 생성에 쓴 모델 기록
    admin_reply       TEXT,                     -- 실제 발송된 답장
    replied_by        UUID REFERENCES public.profiles(id),
    replied_at        TIMESTAMPTZ,
    read_by_user_at   TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_support_messages_user
    ON public.support_messages(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_messages_status
    ON public.support_messages(status, created_at DESC);

-- subscription_verifications와 동일한 관례: RLS만 켜고 정책은 두지 않는다.
-- 클라이언트는 이 테이블에 직접 접근하지 않고 항상 desktop-support 브릿지
-- (session_token HMAC 검증) 또는 어드민 API(requireAdmin)를 경유한다.
ALTER TABLE public.support_messages ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.support_messages IS
    '유저->웹어드민 문의 및 AI 초안/어드민 답장. service_role 전용 접근 - RLS 정책 없음.';
