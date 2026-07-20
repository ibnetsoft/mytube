-- =============================================================
-- 웹어드민 -> 전체 유저 공지사항 게시판
-- =============================================================
-- 쪽지(1:1)가 아니라 게시판(1:N) 구조 - 하나의 글을 모든 유저가 함께
-- 본다. is_pinned인 글은 유저 게시판 목록 최상단에 고정된다.
-- is_published=false인 글은 어드민 화면에만 보이는 임시저장(초안) -
-- 발행 전에는 유저 브릿지(desktop-announcements)가 절대 내려주지 않는다.

CREATE TABLE IF NOT EXISTS public.announcements (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title          TEXT NOT NULL,
    body           TEXT NOT NULL,
    is_pinned      BOOLEAN NOT NULL DEFAULT false,
    is_published   BOOLEAN NOT NULL DEFAULT true,
    pinned_at      TIMESTAMPTZ,           -- 고정된 시각 - 고정글 여러 개일 때 정렬 기준
    published_at   TIMESTAMPTZ,           -- 최초 발행 시각
    created_by     UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    updated_by     UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_announcements_board_order
    ON public.announcements(is_published, is_pinned DESC, pinned_at DESC, published_at DESC);

-- subscription_verifications/support_messages와 동일 관례: RLS만 켜고
-- 정책은 두지 않는다 - service_role 전용, 클라이언트는 항상
-- desktop-announcements 브릿지 또는 어드민 API(requireAdmin)를 경유.
ALTER TABLE public.announcements ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.announcements IS
    '웹어드민 -> 전체 유저 공지사항 게시판(1:N, 쪽지 아님). service_role 전용 접근.';
