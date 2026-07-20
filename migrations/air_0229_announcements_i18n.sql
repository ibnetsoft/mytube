-- =============================================================
-- Migration: AIR-0229 — 공지사항 게시판 다국어 자동번역
-- Description:
--   auth-web/migration_announcements.sql(PR #104, "문의/공지 게시판")이 만든
--   public.announcements 테이블(id, title, body, is_pinned, is_published,
--   pinned_at, published_at, created_by, updated_by, created_at, updated_at)은
--   그대로 두고, 다국어 자동번역에 필요한 컬럼만 순수 추가(additive)한다.
--   기존 title/body를 한글 원문으로 쓰고, en/vi/th 3개 언어의 title_*/body_*를
--   Gemini/Claude(sys_api_translation_model 설정)로 자동 번역해 채운다.
--   데스크톱 앱(설정 > 공지사항 탭)이 현재 언어모드에 맞는 title/body를
--   desktop-announcements 브릿지를 통해 받아본다(없으면 한글로 폴백).
--
--   Safe to run multiple times (모든 DDL이 idempotent).
-- =============================================================

ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS title_en TEXT;
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS body_en TEXT;
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS title_vi TEXT;
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS body_vi TEXT;
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS title_th TEXT;
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS body_th TEXT;
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS translation_status TEXT NOT NULL DEFAULT 'pending';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'announcements_translation_status_check'
    ) THEN
        ALTER TABLE public.announcements
            ADD CONSTRAINT announcements_translation_status_check
            CHECK (translation_status IN ('pending', 'running', 'completed', 'failed'));
    END IF;
END $$;
